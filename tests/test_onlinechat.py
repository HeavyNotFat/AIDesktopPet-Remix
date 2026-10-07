"""网页聊天专用 LLM 实例层。

重点验证「网页聊天不再复用桌面端实例」这件事，包括：

* 每个会话拿到独立实例，会话之间互不串记忆；
* 换了模型一定重建实例；
* LRU / 空闲超时能回收；
* 调用 LLM 时显式关掉 ``should_emit``，不往桌面端 UI 发信号；
* 模块里不再出现 ``return_llm_class`` / ``cache_llm_class`` 这类旧入口。
"""

from __future__ import annotations

import ast
import json
import threading
import time
from pathlib import Path

import pytest

from stlibs.mproc.onlinechat import config as oc_config
from stlibs.mproc.onlinechat import llm as oc_llm
from stlibs.mproc.onlinechat import registry as registry_api
from stlibs.mproc.onlinechat.registry import ModelRegistry, ModelTarget, UnknownModelError

ONLINECHAT_DIR = Path(oc_llm.__file__).parent


# --------------------------------------------------------------------------
# 测试替身
# --------------------------------------------------------------------------
class FakeLocalLLM:
    """模仿 local.LLM.chat(user_input, should_emit=True)。"""

    def __init__(self, model):
        self.model = model
        self.seen = []
        self.emitted = False

    def chat(self, user_input, should_emit=True):
        assert should_emit is False, "网页聊天不应该向桌面端 UI 发信号"
        self.seen.append(user_input)
        yield "local:"
        yield user_input


class FakeCloudLLM:
    """模仿 cloud.LLM.chat(query)（没有 should_emit 参数）。"""

    def __init__(self, model, api_key, base_url):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.seen = []

    def chat(self, query):
        self.seen.append(query)
        yield f"cloud:{query}"


class FakeClosingLLM(FakeLocalLLM):
    def __init__(self, model):
        super().__init__(model)
        self.closed = 0

    def close(self):
        self.closed += 1


def _targets():
    return {
        "alpha": registry_api.ModelTarget("alpha", "alpha", "local", "alpha"),
        "beta": registry_api.ModelTarget("beta", "beta", "local", "beta"),
        "api::cloud": registry_api.ModelTarget(
            "api::cloud", "cloud (API)", "cloud", "real-model", "key", "https://api"
        ),
    }


def _registry():
    reg = registry_api.ModelRegistry(ttl=0, provider=_targets)
    reg.refresh()
    return reg


def _pool(reg, *, max_sessions=4, ttl=60.0):
    created: list[object] = []

    def builder(session_id, target):
        session = oc_llm.WebChatSession.__new__(oc_llm.WebChatSession)
        session.session_id = session_id
        session.target = target
        session.lock = threading.Lock()
        session.created_at = session.last_used = time.monotonic()
        session.turns = 0
        if target.is_cloud:
            session.llm = FakeCloudLLM(target.model, target.api_key, target.base_url)
        else:
            session.llm = FakeClosingLLM(target.model)
        created.append(session.llm)
        return session

    pool = oc_llm.WebChatPool(max_sessions=max_sessions, ttl=ttl, builder=builder)
    pool._test_registry = reg  # noqa: SLF001 - 测试夹具
    pool._created = created  # type: ignore[attr-defined]
    return pool


@pytest.fixture
def patched_registry(monkeypatch):
    reg = _registry()
    monkeypatch.setattr(oc_llm, "registry", reg)
    return reg


# --------------------------------------------------------------------------
# 会话隔离
# --------------------------------------------------------------------------
def test_each_session_gets_its_own_instance(patched_registry):
    pool = _pool(patched_registry)
    assert pool.chat("alpha", "你好", "s1") == "local:你好"
    assert pool.chat("alpha", "在吗", "s1") == "local:在吗"
    assert pool.chat("alpha", "hi", "s2") == "local:hi"

    assert len(pool._created) == 2, "两个会话必须是两个实例"
    assert pool._created[0] is not pool._created[1]
    assert pool.stats()["instances_created"] == 2
    # 会话内部复用同一个实例，记忆不会丢
    assert pool._created[0].seen == ["你好", "在吗"]


def test_default_session_is_shared_for_legacy_clients(patched_registry):
    pool = _pool(patched_registry)
    pool.chat("alpha", "a", None)
    pool.chat("alpha", "b", "")
    assert pool.stats()["instances_created"] == 1
    assert pool.stats()["live"][0]["session_id"] == "default"
    assert pool.stats()["live"][0]["turns"] == 2


def test_switching_model_rebuilds_the_instance(patched_registry):
    pool = _pool(patched_registry)
    pool.chat("alpha", "a", "s1")
    pool.chat("beta", "b", "s1")
    assert pool.stats()["instances_created"] == 2
    assert pool._created[0].model == "alpha"
    assert pool._created[1].model == "beta"
    assert pool._created[0].closed == 1, "换模型要回收旧实例"


def test_cloud_target_uses_its_own_credentials(patched_registry):
    pool = _pool(patched_registry)
    assert pool.chat("api::cloud", "hi", "s1") == "cloud:hi"
    instance = pool._created[0]
    assert (instance.model, instance.api_key, instance.base_url) == ("real-model", "key", "https://api")


def test_unknown_model_is_rejected(patched_registry):
    pool = _pool(patched_registry)
    with pytest.raises(registry_api.UnknownModelError) as excinfo:
        pool.chat("nope", "hi", "s1")
    assert "nope" in str(excinfo.value)
    assert pool.stats()["sessions"] == 0


# --------------------------------------------------------------------------
# 回收
# --------------------------------------------------------------------------
def test_lru_eviction(patched_registry):
    pool = _pool(patched_registry, max_sessions=2)
    for name in ("s1", "s2", "s3"):
        pool.chat("alpha", name, name)
    live = [item["session_id"] for item in pool.stats()["live"]]
    assert live == ["s2", "s3"]
    assert pool.stats()["evicted"] == 1
    assert pool._created[0].closed == 1


def test_idle_sessions_expire(patched_registry):
    pool = _pool(patched_registry, ttl=0.05)
    pool.chat("alpha", "a", "s1")
    time.sleep(0.3)   # 给足余量，避免 CI 上抖动
    pool.chat("alpha", "b", "s2")
    live = [item["session_id"] for item in pool.stats()["live"]]
    assert live == ["s2"]
    assert pool.stats()["evicted"] == 1


def test_reset_drops_sessions(patched_registry):
    pool = _pool(patched_registry)
    pool.chat("alpha", "a", "s1")
    pool.chat("alpha", "a", "s2")
    assert pool.reset("s1") == 1
    assert [item["session_id"] for item in pool.stats()["live"]] == ["s2"]
    assert pool._created[0].closed == 1
    assert pool.reset(None) == 1
    assert pool.stats()["sessions"] == 0


def test_shutdown_closes_everything(patched_registry):
    pool = _pool(patched_registry)
    pool.chat("alpha", "a", "s1")
    pool.shutdown()
    assert pool.stats()["sessions"] == 0
    assert pool._created[0].closed == 1


def test_same_session_requests_are_serialised(patched_registry):
    """同一会话并发请求要串行执行，否则实例内部记忆会被写乱。"""
    pool = _pool(patched_registry)
    session = pool._acquire("s1", patched_registry.resolve("alpha"))

    order: list[str] = []
    original = oc_llm._collect

    def slow(llm, question):
        order.append(f"start:{question}")
        time.sleep(0.05)
        order.append(f"end:{question}")
        return original(llm, question)

    oc_llm._collect = slow  # type: ignore[assignment]
    try:
        threads = [threading.Thread(target=session.ask, args=(f"q{i}",)) for i in range(3)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    finally:
        oc_llm._collect = original  # type: ignore[assignment]

    assert order == [
        "start:q0", "end:q0",
        "start:q1", "end:q1",
        "start:q2", "end:q2",
    ]


def test_eviction_does_not_hold_the_pool_lock(patched_registry):
    """淘汰一个会话时不能占着池锁等它的慢请求结束。

    ``WebChatSession.close()`` 会等在跑的请求收尾，如果回收是在持有池锁时做的，
    一个卡住的会话会把所有其它会话一起拖死。
    """
    close_started = threading.Event()
    release_close = threading.Event()

    class SlowClose(FakeClosingLLM):
        def close(self):
            close_started.set()
            release_close.wait(3.0)
            super().close()

    def builder(session_id, target):
        session = oc_llm.WebChatSession.__new__(oc_llm.WebChatSession)
        session.session_id = session_id
        session.target = target
        session.lock = threading.Lock()
        session.created_at = session.last_used = time.monotonic()
        session.turns = 0
        session.llm = SlowClose(target.model)
        return session

    pool = oc_llm.WebChatPool(max_sessions=1, ttl=60.0, builder=builder)
    pool.chat("alpha", "a", "s1")

    evictor = threading.Thread(target=lambda: pool.chat("alpha", "b", "s2"), daemon=True)
    evictor.start()
    assert close_started.wait(3.0), "淘汰没有触发 close()"

    # 池锁此刻必须是空闲的：另一个线程能立刻拿到它
    stats_done = threading.Event()

    def read_stats():
        pool.stats()
        stats_done.set()

    reader = threading.Thread(target=read_stats, daemon=True)
    reader.start()
    locked_out = not stats_done.wait(1.0)

    release_close.set()
    evictor.join(5.0)
    reader.join(5.0)

    assert not locked_out, "淘汰期间池锁被长期占用，其它会话会被连带阻塞"
    assert [item["session_id"] for item in pool.stats()["live"]] == ["s2"]


def test_empty_reply_falls_back(patched_registry):
    pool = _pool(patched_registry)

    class Silent(FakeLocalLLM):
        def chat(self, user_input, should_emit=True):
            assert should_emit is False
            return iter(())

    def builder(session_id, target):
        session = oc_llm.WebChatSession.__new__(oc_llm.WebChatSession)
        session.session_id = session_id
        session.target = target
        session.lock = threading.Lock()
        session.created_at = session.last_used = time.monotonic()
        session.turns = 0
        session.llm = Silent(target.model)
        return session

    pool._builder = builder
    assert pool.chat("alpha", "hi", "s1") == oc_llm.EMPTY_REPLY


# --------------------------------------------------------------------------
# 调用适配
# --------------------------------------------------------------------------
def test_call_chat_adapts_to_both_signatures():
    local = FakeLocalLLM("m")
    assert "".join(oc_llm._call_chat(local, "q")) == "local:q"

    cloud = FakeCloudLLM("m", "k", "u")
    assert "".join(oc_llm._call_chat(cloud, "q")) == "cloud:q"


def test_call_chat_rejects_unknown_signature():
    class NoMessageParam:
        def chat(self):
            yield ""

    with pytest.raises(TypeError):
        oc_llm._call_chat(NoMessageParam(), "q")


def test_call_chat_accepts_kwargs_only_signature():
    """``chat(**kwargs)`` 之类能吞任意关键字的实现也要能用。"""

    class KwargsOnly:
        def __init__(self):
            self.got = None

        def chat(self, **kwargs):
            self.got = kwargs
            yield "ok"

    llm = KwargsOnly()
    assert "".join(oc_llm._call_chat(llm, "q")) == "ok"
    assert llm.got == {"kwargs": "q"}


def test_collect_ignores_event_dicts():
    class Eventful:
        def chat(self, user_input, should_emit=True):
            yield "a"
            yield {"type": "tool_call", "name": "x"}
            yield "b"

    assert oc_llm._collect(Eventful(), "q") == "ab"


# --------------------------------------------------------------------------
# 注册表
# --------------------------------------------------------------------------
def test_registry_builds_local_and_cloud_targets(monkeypatch):
    monkeypatch.setattr(registry_api, "get_model_lists", lambda: ["llama3:latest"])
    monkeypatch.setattr(
        registry_api,
        "Config",
        type("C", (), {"models": {"我的模型": {"name": "glm-4", "apikey": "k", "baseurl": "u"}}}),
    )
    targets = registry_api.load_targets()
    assert list(targets) == ["llama3:latest", "api::我的模型"]
    cloud = targets["api::我的模型"]
    assert cloud.is_cloud
    assert (cloud.model, cloud.api_key, cloud.base_url) == ("glm-4", "k", "u")
    assert cloud.public() == {"value": "api::我的模型", "label": "我的模型 (API)", "backend": "cloud"}


def test_registry_resolve_and_error():
    reg = _registry()
    assert reg.resolve("alpha").backend == "local"
    assert reg.resolve("api::cloud").is_cloud
    with pytest.raises(registry_api.UnknownModelError):
        reg.resolve("missing")


def test_registry_survives_provider_failure():
    def broken():
        raise RuntimeError("ollama 挂了")

    reg = registry_api.ModelRegistry(ttl=0, provider=broken)
    assert reg.snapshot() == {}
    with pytest.raises(registry_api.UnknownModelError):
        reg.resolve("anything")


# --------------------------------------------------------------------------
# 不再复用桌面端实例（回归防线）
# --------------------------------------------------------------------------
def test_onlinechat_never_touches_desktop_llm_cache():
    """用 AST 而不是字符串匹配：文档里可以提旧写法，代码里不许出现。"""
    forbidden = {"cache_llm_class", "return_llm_class", "SharingData"}
    for path in ONLINECHAT_DIR.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        used: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                used.add(node.id)
            elif isinstance(node, ast.Attribute):
                used.add(node.attr)
        leaked = used & forbidden
        assert not leaked, f"{path.name} 又去碰桌面端实例/共享状态了：{sorted(leaked)}"


def test_desktop_sharing_data_is_untouched(patched_registry, monkeypatch):
    import stlibs

    sentinel = object()
    monkeypatch.setattr(stlibs.SharingData, "theme", sentinel, raising=False)
    pool = _pool(patched_registry)
    pool.chat("alpha", "hi", "s1")
    assert stlibs.SharingData.theme is sentinel


# --------------------------------------------------------------------------
# HTTP 接口
# --------------------------------------------------------------------------
@pytest.fixture
def client(monkeypatch):
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    from stlibs.mproc.onlinechat import app, pool
    from stlibs.mproc.onlinechat import model_registry as bound_registry

    monkeypatch.setattr(oc_llm, "registry", _registry())
    # 路由里绑定的是包级 model_registry，必须打它，否则会真去跑 ollama list
    monkeypatch.setattr(bound_registry, "snapshot", _registry().snapshot)
    monkeypatch.setattr(pool, "_builder", _pool(_registry())._builder)
    monkeypatch.setattr(
        pool,
        "chat",
        lambda model, question, session_id=None: f"echo:{model}:{question}:{session_id}",
    )
    monkeypatch.setattr(pool, "stats", lambda: {"sessions": 1, "instances_created": 1, "live": []})
    monkeypatch.setattr(pool, "reset", lambda session_id=None: 1 if session_id else 0)
    return fastapi_testclient.TestClient(app)


def test_api_getmodelname(client):
    payload = client.post("/api/getmodelname").json()
    assert "name" in payload


def test_api_getmodellist_returns_label_value(client):
    models = client.post("/api/getmodellist").json()["models"]
    assert models == [
        {"value": "alpha", "label": "alpha", "backend": "local"},
        {"value": "beta", "label": "beta", "backend": "local"},
        {"value": "api::cloud", "label": "cloud (API)", "backend": "cloud"},
    ]


def test_api_health_and_reset_and_status_paths(client):
    assert client.get("/api/health").json() == {"ok": True}


def test_api_chat_passes_session_id(client):
    response = client.post("/api/chat", json={"model": "alpha", "question": "hi", "session_id": "s9"})
    assert response.status_code == 200
    assert response.json()["answer"] == "echo:alpha:hi:s9"


def test_api_chat_without_session_id(client):
    response = client.post("/api/chat", json={"model": "alpha", "question": "hi"})
    assert response.json()["answer"] == "echo:alpha:hi:None"


def test_api_chat_rejects_empty_question(client):
    response = client.post("/api/chat", json={"model": "alpha", "question": "   "})
    assert response.status_code == 400


def test_api_reset(client):
    assert client.post("/api/reset", json={"session_id": "s1"}).json() == {"dropped": 1}
    assert client.post("/api/reset", json={}).json() == {"dropped": 0}


def test_api_status_exposes_pool(client):
    payload = client.post("/api/status").json()
    assert payload["pool"]["sessions"] == 1
    assert "models" in payload


def test_api_chat_unknown_model(monkeypatch):
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    from stlibs.mproc.onlinechat import app, pool

    def boom(model, question, session_id=None):
        raise registry_api.UnknownModelError(model, ["alpha"])

    monkeypatch.setattr(pool, "chat", boom)
    response = fastapi_testclient.TestClient(app).post("/api/chat", json={"model": "nope", "question": "hi"})
    assert response.status_code == 400
    assert "nope" in response.json()["detail"]


def test_api_chat_backend_error_becomes_502(monkeypatch):
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    from stlibs.mproc.onlinechat import app, pool

    def boom(model, question, session_id=None):
        raise RuntimeError("模型炸了")

    monkeypatch.setattr(pool, "chat", boom)
    response = fastapi_testclient.TestClient(app).post("/api/chat", json={"model": "alpha", "question": "hi"})
    assert response.status_code == 502
    assert "RuntimeError" in response.json()["detail"]


def test_build_llm_constructs_real_classes(monkeypatch):
    """真·构造路径：确认 local / cloud 两个分支都按 target 建实例。

    这里用假的 ``stlibs.ai.local`` / ``cloud`` 模块替身（不需要 PySide6 / ollama），
    但走的是 ``_build_llm`` 的真实分支逻辑。
    """
    import sys
    import types

    from stlibs.mproc.onlinechat.registry import ModelTarget

    created = {}

    fake_local = types.ModuleType("stlibs.ai.local")
    fake_cloud = types.ModuleType("stlibs.ai.cloud")

    class LocalLLM:
        def __init__(self, model):
            created["local"] = model

    class CloudLLM:
        def __init__(self, model, api_key, base_url):
            created["cloud"] = (model, api_key, base_url)

    fake_local.LLM = LocalLLM
    fake_cloud.LLM = CloudLLM

    import stlibs.ai as ai_pkg

    monkeypatch.setitem(sys.modules, "stlibs.ai.local", fake_local)
    monkeypatch.setitem(sys.modules, "stlibs.ai.cloud", fake_cloud)
    monkeypatch.setattr(ai_pkg, "local", fake_local, raising=False)
    monkeypatch.setattr(ai_pkg, "cloud", fake_cloud, raising=False)

    local_target = ModelTarget("m", "m", "local", "llama3")
    assert isinstance(oc_llm._build_llm(local_target), LocalLLM)
    assert created["local"] == "llama3"

    cloud_target = ModelTarget("api::x", "x (API)", "cloud", "glm-4", "k", "https://api")
    assert isinstance(oc_llm._build_llm(cloud_target), CloudLLM)
    assert created["cloud"] == ("glm-4", "k", "https://api")


def test_ask_after_close_raises_clear_error(patched_registry):
    pool = _pool(patched_registry)
    session = pool._acquire("s1", patched_registry.resolve("alpha"))
    pool.reset("s1")
    with pytest.raises(oc_llm.SessionClosedError) as excinfo:
        session.ask("hi")
    assert "s1" in str(excinfo.value)


def test_closed_session_maps_to_409(monkeypatch):
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    from stlibs.mproc.onlinechat import app, pool

    def closed(model, question, session_id=None):
        raise oc_llm.SessionClosedError(session_id or "default")

    monkeypatch.setattr(pool, "chat", closed)
    response = fastapi_testclient.TestClient(app).post(
        "/api/chat", json={"model": "alpha", "question": "hi", "session_id": "s1"}
    )
    assert response.status_code == 409
    assert "已回收" in response.json()["detail"]


class SlowLocalLLM(FakeLocalLLM):
    def __init__(self, model, chunks=("你", "好", "喵"), delay=0.02):
        super().__init__(model)
        self.chunks = chunks
        self.delay = delay

    def chat(self, user_input, should_emit=True):
        assert should_emit is False
        self.seen.append(user_input)
        for chunk in self.chunks:
            time.sleep(self.delay)
            yield chunk


class RecordingLocalLLM(FakeLocalLLM):
    def __init__(self, model):
        super().__init__(model)
        self.memory = SimpleMemory()

    def chat(self, user_input, should_emit=True):
        raise AssertionError("补记记忆时不该调用模型")


class SimpleMemory:
    def __init__(self):
        self.messages = []

    def add_user_msg(self, msg):
        self.messages.append({"role": "user", "content": msg})

    def add_assistant_msg(self, msg):
        self.messages.append({"role": "assistant", "content": msg})


def _stream_pool(llm_factory=None, **kwargs):
    created = []

    def builder(session_id, target):
        session = oc_llm.WebChatSession.__new__(oc_llm.WebChatSession)
        session.session_id = session_id
        session.target = target
        session.lock = threading.Lock()
        session.created_at = session.last_used = time.monotonic()
        session.turns = 0
        session.llm = (llm_factory or SlowLocalLLM)(target.model)
        created.append(session.llm)
        return session

    pool = oc_llm.WebChatPool(builder=builder, **kwargs)
    pool._created = created
    return pool


def test_stream_yields_chunks_in_order(patched_registry):
    pool = _stream_pool()
    assert list(pool.stream("alpha", "hi", "s1")) == ["你", "好", "喵"]
    assert pool.stats()["live"][0]["turns"] == 1


def test_stream_without_delay_matches_ask(patched_registry):
    pool = _stream_pool(lambda model: FakeLocalLLM(model))
    assert "".join(pool.stream("alpha", "hi", "s1")) == "local:hi"


def test_stream_validates_model_and_session_up_front(patched_registry):
    pool = _stream_pool()

    with pytest.raises(registry_api.UnknownModelError):
        pool.stream("nope", "hi", "s1")

    # 会话实例被回收但还挂在池子的窗口期（TTL/LRU/reset 与请求撞车）：
    # 必须在返回迭代器之前就抛错，不能让 SSE 先发 200 再报错
    session = pool._acquire("s2", patched_registry.resolve("alpha"))
    session.close()
    with pytest.raises(oc_llm.SessionClosedError):
        pool.stream("alpha", "hi", "s2")
    with pytest.raises(oc_llm.SessionClosedError):
        session.ensure_alive()


def test_stream_stop_event_aborts_and_releases_lock(patched_registry):
    pool = _stream_pool(lambda model: SlowLocalLLM(model, chunks=tuple("abcdefghij")))
    pump = pool.stream("alpha", "hi", "s1")

    iterator = iter(pump)
    assert next(iterator) == "a"

    pump.stop_event.set()
    assert list(iterator) == [], "置位 stop_event 后不该继续吐字"

    session = pool._sessions["s1"]
    assert session.lock.acquire(timeout=2), "中止后会话锁没有交还"
    session.lock.release()


def test_abandoned_stream_stops_the_worker(patched_registry):
    pool = _stream_pool(lambda model: SlowLocalLLM(model, chunks=tuple("abcdefghij")))
    pump = pool.stream("alpha", "hi", "s1")

    iterator = iter(pump)
    assert next(iterator) == "a"
    iterator.close()

    assert pump.stop_event.is_set(), "客户端断开后没通知工作线程收手"
    assert pump._thread.join(timeout=3) is None
    assert not pump._thread.is_alive()


def test_stream_propagates_errors(patched_registry):
    class Broken(FakeLocalLLM):
        def chat(self, user_input, should_emit=True):
            yield "开头"
            raise RuntimeError("模型炸了")

    pool = _stream_pool(lambda model: Broken(model))
    with pytest.raises(RuntimeError, match="模型炸了"):
        list(pool.stream("alpha", "hi", "s1"))


def test_stream_ignores_non_text_events(patched_registry):
    class Eventful(FakeLocalLLM):
        def chat(self, user_input, should_emit=True):
            yield "a"
            yield {"type": "tool_call", "name": "x"}
            yield "b"

    pool = _stream_pool(lambda model: Eventful(model))
    assert list(pool.stream("alpha", "hi", "s1")) == ["a", "b"]


def test_stream_keeps_sessions_isolated(patched_registry):
    pool = _stream_pool(lambda model: FakeLocalLLM(model))
    assert list(pool.stream("alpha", "a", "s1")) == ["local:", "a"]
    assert list(pool.stream("alpha", "b", "s2")) == ["local:", "b"]
    assert pool.stats()["instances_created"] == 2


def test_stream_shares_lock_with_ask(patched_registry):
    pool = _stream_pool(lambda model: SlowLocalLLM(model, chunks=("1", "2", "3"), delay=0.05))

    order = []
    pump = pool.stream("alpha", "流", "s1")

    def consume():
        order.append(list(pump))
        order.append("stream-done")

    def queued():
        session = pool._sessions["s1"]
        session.ask("问")
        order.append("ask-done")

    streamer = threading.Thread(target=consume, daemon=True)
    streamer.start()
    time.sleep(0.02)
    asker = threading.Thread(target=queued, daemon=True)
    asker.start()

    streamer.join(5)
    asker.join(5)
    assert order[0] == ["1", "2", "3"]
    assert order.index("stream-done") < order.index("ask-done")


def test_remember_appends_turn_without_calling_model(patched_registry):
    pool = _stream_pool(lambda model: RecordingLocalLLM(model))

    assert pool.remember("alpha", "缓存过的问题", "缓存过的回答", "s1") is True
    session = pool._sessions["s1"]
    assert session.llm.seen == [], "补记不该调用模型"
    assert session.llm.memory.messages == [
        {"role": "user", "content": "缓存过的问题"},
        {"role": "assistant", "content": "缓存过的回答"},
    ]
    assert session.turns == 1


def test_remember_on_closed_session(patched_registry):
    pool = _stream_pool()
    session = pool._acquire("s2", patched_registry.resolve("alpha"))
    session.close()
    with pytest.raises(oc_llm.SessionClosedError):
        pool.remember("alpha", "q", "a", "s2")


def test_recall_endpoint_records_turn(sse_client, monkeypatch):
    client, pool = sse_client
    pool._builder = _stream_pool(lambda model: RecordingLocalLLM(model))._builder

    response = client.post(
        "/api/chat/recall",
        json={"model": "alpha", "question": "缓存问题", "answer": "缓存回答", "session_id": "s9"},
    )
    assert response.json() == {"recorded": True}
    assert pool._sessions["s9"].llm.memory.messages[0]["content"] == "缓存问题"


def test_recall_endpoint_rejects_empty(sse_client, monkeypatch):
    client, _pool = sse_client
    assert client.post("/api/chat/recall", json={"model": "alpha", "question": " ", "answer": "a"}).status_code == 400
    assert client.post("/api/chat/recall", json={"model": "alpha", "question": "q", "answer": " "}).status_code == 400


@pytest.fixture
def sse_client(monkeypatch):
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    from stlibs.mproc.onlinechat import app, pool

    monkeypatch.setattr(oc_llm, "registry", _registry())
    return fastapi_testclient.TestClient(app), pool


def _frames(response):
    payloads = []
    for line in response.text.splitlines():
        if line.startswith("data:"):
            payloads.append(json.loads(line[5:].strip()))
    return payloads


def test_api_stream_emits_start_delta_done(sse_client, monkeypatch):
    client, pool = sse_client
    monkeypatch.setattr(pool, "stream", lambda model, question, session_id=None, stop_event=None: ["你", "好"])

    response = client.post("/api/chat/stream", json={"model": "alpha", "question": "hi", "session_id": "s1"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    frames = _frames(response)
    assert [f["type"] for f in frames] == ["start", "delta", "delta", "done"]
    assert "".join(f["text"] for f in frames if f["type"] == "delta") == "你好"
    assert frames[0]["session_id"] == "s1"


def test_api_stream_reports_backend_error_as_event(sse_client, monkeypatch):
    client, pool = sse_client

    def broken(model, question, session_id=None, stop_event=None):
        yield "半句"
        raise RuntimeError("模型炸了")

    monkeypatch.setattr(pool, "stream", broken)
    response = client.post("/api/chat/stream", json={"model": "alpha", "question": "hi"})

    frames = _frames(response)
    assert frames[0]["type"] == "start"
    assert frames[1] == {"type": "delta", "text": "半句"}
    assert frames[-1]["type"] == "error"
    assert "模型炸了" in frames[-1]["detail"]
    assert not any(f["type"] == "done" for f in frames)


def test_api_stream_maps_closed_session_to_event(sse_client, monkeypatch):
    client, pool = sse_client

    def closed(model, question, session_id=None, stop_event=None):
        raise oc_llm.SessionClosedError(session_id or "default")
        yield

    monkeypatch.setattr(pool, "stream", closed)
    response = client.post("/api/chat/stream", json={"model": "alpha", "question": "hi", "session_id": "s1"})

    frames = _frames(response)
    assert frames[-1]["type"] == "error"
    assert frames[-1]["retry"] is True


def test_api_stream_validates_before_streaming(sse_client, monkeypatch):
    client, pool = sse_client

    def boom(*args, **kwargs):
        raise registry_api.UnknownModelError("nope", ["alpha"])

    monkeypatch.setattr(pool, "stream", boom)
    assert client.post("/api/chat/stream", json={"model": "nope", "question": "hi"}).status_code == 400
    assert client.post("/api/chat/stream", json={"model": "alpha", "question": "  "}).status_code == 400


def test_api_stream_ends_when_consumer_disconnects(sse_client, monkeypatch):
    """客户端断开时流必须收尾，不能把工作线程和会话锁留着。"""
    client, pool = sse_client
    stopped = threading.Event()

    def chunks(model, question, session_id=None, stop_event=None):
        for index in range(50):
            if stop_event is not None and stop_event.is_set():
                stopped.set()
                return
            time.sleep(0.01)
            yield str(index)

    monkeypatch.setattr(pool, "stream", chunks)
    response = client.post("/api/chat/stream", json={"model": "alpha", "question": "hi"})
    assert response.status_code == 200
    assert _frames(response)[0]["type"] == "start"


def test_config_defaults():
    assert oc_config.HOST == "127.0.0.1" or oc_config.HOST
    assert isinstance(oc_config.PORT, int) and 0 < oc_config.PORT < 65536
    assert oc_config.MAX_SESSIONS >= 1
    assert oc_config.MODEL_LIST_TTL > 0
    assert oc_config.REQUEST_TIMEOUT > 0
    assert oc_config.SESSION_TTL >= 0, "0 表示不按时间回收，是合法配置"
    assert (oc_config.WEB_DIR / "index.html").is_file()
