import json
import socket
import threading
import time

import pytest

import stlibs
from stlibs.sdk import base
from stlibs.sdk.client import SDKClient
from stlibs.sdk.methods import METHOD_HELP, HostMethods
from stlibs.sdk.server import ALIASES, EVENTS, SDKServer


@pytest.fixture
def server():
    instance = SDKServer(port=0)
    instance.start()
    yield instance
    instance.stop()


@pytest.fixture
def client(server):
    with SDKClient("127.0.0.1", server.local_address[1], timeout=3.0) as instance:
        yield instance


def raw_call(server, payload, timeout=3.0):
    """绕过客户端直接发一个数据报，用来看服务端怎么回。"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    try:
        sock.sendto(json.dumps(payload, ensure_ascii=False).encode("utf-8"), server.local_address)
        data, _addr = sock.recvfrom(base.MAX_DATAGRAM)
        return json.loads(data.decode("utf-8"))
    finally:
        sock.close()


# 协议与校验
def test_ping_round_trip(server, client):
    result = client.ping()

    assert result["pong"] is True
    assert result["time"] > 0


def test_method_table_and_version(client):
    methods = {item["name"] for item in client.list_methods()}
    version = client.version()

    assert "ping" in methods
    assert "ask" in methods
    assert len(methods) == len(METHOD_HELP)
    assert version["protocol"] == 2


def test_unknown_method_reports_code(server):
    response = raw_call(server, {"id": "1", "method": "根本没有"})

    assert response["code"] == "method_error"
    assert "list_methods" in response["error"]


def test_missing_argument_is_rejected(server):
    response = raw_call(server, {"id": "2", "method": "play_live2d_motion"})

    assert response["code"] == "method_error"
    assert "缺少必填参数" in response["error"]


def test_unknown_kwarg_is_rejected(server):
    response = raw_call(server, {"id": "3", "method": "ping", "kwargs": {"什么": 1}})

    assert response["code"] == "method_error"
    assert "不认识参数" in response["error"]


def test_too_many_arguments_is_rejected(server):
    response = raw_call(server, {"id": "4", "method": "ping", "args": [1, 2, 3]})

    assert response["code"] == "method_error"
    assert "最多接受" in response["error"]


def test_bad_args_type_is_rejected(server):
    response = raw_call(server, {"id": "5", "method": "ping", "args": "不是数组"})

    assert response["code"] == "bad_request"


def test_alias_maps_to_canonical(server):
    assert ALIASES["chat"] == "ask"

    result = server.invoke("status")
    assert "theme" in result


def test_garbage_datagram_is_ignored(server):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.sendto("这不是 JSON".encode("utf-8"), server.local_address)
        sock.sendto(json.dumps([1, 2, 3]).encode("utf-8"), server.local_address)
    finally:
        sock.close()
    time.sleep(0.2)

    assert server.status()["errors"] == 0
    assert server.invoke("ping")["pong"] is True


def test_token_is_enforced():
    instance = SDKServer(port=0, token="s3cret")
    instance.start()
    try:
        response = raw_call(instance, {"id": "1", "method": "ping"})
        assert response["code"] == "unauthorized"

        okay = raw_call(instance, {"id": "2", "method": "ping", "token": "s3cret"})
        assert okay["result"]["pong"] is True

        with SDKClient("127.0.0.1", instance.local_address[1], token="s3cret") as client:
            assert client.ping()["pong"] is True
    finally:
        instance.stop()


def test_method_exception_becomes_error_response(server, monkeypatch):
    def boom():
        raise RuntimeError("方法自己炸了")

    monkeypatch.setattr(server.methods, "ping", boom, raising=False)
    response = raw_call(server, {"id": "1", "method": "ping"})

    assert response["code"] == "internal_error"
    assert "方法自己炸了" in response["error"]
    assert server.status()["running"] is True, "一次调用炸了不能把服务端带走"


def test_client_timeout_is_reported():
    with SDKClient("127.0.0.1", 1, timeout=0.3) as client:
        with pytest.raises(base.SDKTimeoutError):
            client.ping()


def test_pending_request_is_cleaned_after_timeout():
    """超时后待处理表不能越攒越多（否则客户端会漏内存/串响应）。"""
    with SDKClient("127.0.0.1", 1, timeout=0.2) as client:
        with pytest.raises(base.SDKTimeoutError):
            client.ping()

        assert client._pending == {}


# 方法实现
def test_status_reports_host_facts(client):
    status = client.get_status()

    assert status["theme"]
    assert status["methods"] >= 20
    assert "plugins" in status
    assert status["uptime"] >= 0


def test_get_appearance_and_config(client):
    appearance = client.get_appearance()
    config = client.get_config()
    one = client.get_config("theme")

    assert set(appearance) == {"size", "opacity", "rotate"}
    assert "memory" in config and "plugins" in config
    assert set(one) == {"theme"}


def test_get_config_rejects_unknown_key(client):
    with pytest.raises(base.SDKRemoteError) as excinfo:
        client.get_config("随便写的")

    assert excinfo.value.code == "method_error"
    assert "没有这个配置项" in str(excinfo.value)


def test_set_config_writes_and_persists(tmp_path, monkeypatch, client):
    monkeypatch.setattr(stlibs, "CONFIG_PATH", str(tmp_path / "configure.json"))
    # 别的用例会照着 Config 建界面，改完必须还原（否则 setValue("80") 直接 TypeError）
    monkeypatch.setattr(stlibs.Config, "opacity", stlibs.Config.opacity)

    result = client.set_config("opacity", "80")

    assert result == {"opacity": "80"}
    assert stlibs.Config.opacity == "80"
    saved = json.loads((tmp_path / "configure.json").read_text(encoding="utf-8"))
    assert saved["opacity"] == "80"


def test_set_config_rejects_disallowed_key(client):
    with pytest.raises(base.SDKRemoteError) as excinfo:
        client.set_config("models", {"坏": {}})

    assert excinfo.value.code == "method_error"
    assert "不允许外部改" in str(excinfo.value)


def test_plugin_methods_are_exposed(client):
    status = client.list_plugins()
    assert "plugins" in status

    result = client.run_plugin_command("/不存在的命令")
    assert result == {"handled": False, "result": ""}


def test_notify_without_ui_falls_back(monkeypatch, client):
    calls = []
    monkeypatch.setattr(stlibs, "notify", lambda text, level="info", timeout=2600: calls.append((text, level)))

    client.notify("来自 SDK", "success")

    assert calls == [("来自 SDK", "success")]


def test_send_to_chat_without_window(monkeypatch, client):
    sent = []
    monkeypatch.setattr("stlibs.plugin_manager", lambda: type("M", (), {
        "send_to_chat": staticmethod(lambda text, role: sent.append((text, role))),
    })())

    client.send_to_chat("你好", "user")

    assert sent == [("你好", "user")]


def test_chat_history_without_window(client):
    assert client.get_chat_history() == []


def test_memory_stats_shape(client):
    stats = client.memory_stats()

    assert "instances" in stats
    assert client.memory_recall("随便问点") == [] or isinstance(client.memory_recall("x"), list)


def test_live2d_lists_are_serialisable(client):
    motions = client.get_live2d_motion()
    expressions = client.get_live2d_expression()

    assert isinstance(motions, (list, str))
    assert isinstance(expressions, (list, str))


def test_play_methods_need_settings_window(client):
    with pytest.raises(base.SDKRemoteError) as excinfo:
        client.play_live2d_motion("摸摸头", 0)

    assert "设置窗口" in str(excinfo.value)


def test_ask_without_models(monkeypatch, client):
    monkeypatch.setattr("stlibs.get_model_lists", lambda: [])

    with pytest.raises(base.SDKRemoteError) as excinfo:
        client.ask("你好")

    assert "没有可用的本地模型" in str(excinfo.value)


def test_ask_rejects_empty_question(client):
    with pytest.raises(base.SDKRemoteError):
        client.ask("   ")


def test_host_methods_can_be_used_directly(monkeypatch):
    """不经过 socket 也能用（宿主内部/测试都方便）。"""
    assert HostMethods.ping()["pong"] is True
    assert "name" in HostMethods.list_methods()[0]


# 事件
def test_subscribe_and_receive_event(server, client):
    client.subscribe("demo")

    server.emit("demo", {"n": 1})
    message = client.wait_event("demo", timeout=2)

    assert message["data"] == {"n": 1}
    assert message["seq"] == 1


def test_subscriber_receives_through_server_emit(server, client):
    client.subscribe("*")
    count = server.emit("anything", "hi")

    assert count == 1
    subscribers = server.subscribers()
    assert list(subscribers.values()) == [["*"]], "订阅者按服务端看到的地址记"
    assert list(subscribers)[0][1] == client.local_address[1]


def test_unsubscribe_stops_delivery(server, client):
    client.subscribe("demo")
    client.unsubscribe("demo")

    assert server.emit("demo", {}) == 0
    assert client.wait_event("demo", timeout=0.3) is None


def test_event_handler_callback(client):
    received = []
    client.subscribe("demo")
    client.on("demo", lambda data, message: received.append(data))

    client.emit_event("demo", {"k": "v"})
    deadline = time.time() + 2
    while not received and time.time() < deadline:
        time.sleep(0.02)

    assert received == [{"k": "v"}]


def test_broken_handler_does_not_stop_others(client):
    received = []

    def broken(_data, _message):
        raise RuntimeError("订阅者自己炸了")

    client.subscribe("demo")
    client.on("demo", broken)
    client.on("demo", lambda data, _message: received.append(data))

    client.emit_event("demo", 1)
    deadline = time.time() + 2
    while not received and time.time() < deadline:
        time.sleep(0.02)

    assert received == [1]


def test_wildcard_handler(client):
    received = []
    client.subscribe("demo")
    client.on("*", lambda data, message: received.append(message["name"]))

    client.emit_event("demo", 1)
    deadline = time.time() + 2
    while not received and time.time() < deadline:
        time.sleep(0.02)

    assert received == ["demo"]


def test_emit_event_method_goes_through_rpc(server, client):
    client.subscribe("demo")
    result = client.emit_event("demo", {"x": 1})

    assert result == {"name": "demo", "subscribers": 1}
    assert client.wait_event("demo", timeout=2)["data"] == {"x": 1}


def test_event_constants_documented():
    assert "pet_click" in EVENTS
    assert "chat_finished" in EVENTS


def test_server_status_reports_counts(server, client):
    client.ping()
    client.subscribe("*")
    client.emit_event("demo", None)
    status = server.status()

    assert status["calls"] >= 2
    assert status["subscribers"] == 1
    assert status["token"] is False


def test_concurrent_calls_are_handled(server):
    """服务端是线程池：几个客户端同时打不该串包。"""
    results = {}
    errors = []

    def worker(index):
        try:
            with SDKClient("127.0.0.1", server.local_address[1], timeout=5) as client:
                results[index] = client.notify(f"第 {index} 号", "info")
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(index,)) for index in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(5)

    assert not errors
    assert len(results) == 6
