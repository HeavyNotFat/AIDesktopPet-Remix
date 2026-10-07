from __future__ import annotations

import inspect
import queue
import threading
import time
from collections import OrderedDict

from .config import MAX_SESSIONS, SESSION_TTL
from .registry import ModelTarget, registry

EMPTY_REPLY = "（模型返回了空内容）"

_CONTROL_PARAMS = frozenset({"should_emit", "emit"})

_DEFAULT_SESSION = "default"

_DONE = object()


class SessionClosedError(RuntimeError):
    """会话在请求开始前被回收（TTL / LRU / /api/reset 撞车）。"""

    def __init__(self, session_id: str):
        self.session_id = session_id
        super().__init__(f"会话 {session_id!r} 已回收，请重新发送")


def _build_llm(target: ModelTarget):
    from ...ai import cloud, local

    if target.is_cloud:
        return cloud.LLM(target.model, target.api_key, target.base_url)
    return local.LLM(target.model)


def _call_chat(llm, question: str):
    """按签名适配 ``local.LLM.chat(user_input, should_emit)`` 与 ``cloud.LLM.chat(query)``。

    控制开关一律显式关掉，避免实例把记忆推给桌面端 Qt 界面。
    """
    parameters = inspect.signature(llm.chat).parameters
    message_params = [name for name in parameters if name not in _CONTROL_PARAMS]
    if not message_params:
        raise TypeError(f"{type(llm).__name__}.chat 没有可识别的消息参数：{list(parameters)}")

    kwargs = {name: False for name in parameters if name in _CONTROL_PARAMS}
    kwargs[message_params[0]] = question
    return llm.chat(**kwargs)


def _collect(llm, question: str) -> str:
    chunks: list[str] = []
    for event in _call_chat(llm, question):
        if isinstance(event, str):
            chunks.append(event)
    return "".join(chunks)


class StreamPump:
    """在专用线程里跑生成器，把片段通过队列交给 HTTP 响应。

    会话锁必须在同一个线程里获取和释放，而 Starlette 迭代同步生成器时
    会用线程池（每次 next() 可能落在不同线程），所以中间必须垫一层队列。
    """

    def __init__(self, chunks, stop_event: threading.Event):
        self.chunks = chunks
        self.stop_event = stop_event
        self.error: BaseException | None = None
        self._queue: queue.Queue = queue.Queue()
        self._thread = threading.Thread(target=self._run, name="webchat-stream", daemon=True)

    def _run(self):
        try:
            for chunk in self.chunks:
                if self.stop_event.is_set():
                    break
                self._queue.put(chunk)
        except BaseException as exc:  # noqa: BLE001 - 异常要带回消费端，不能吞
            self.error = exc
        finally:
            self._queue.put(_DONE)

    def __iter__(self):
        self._thread.start()
        try:
            while True:
                item = self._queue.get()
                if item is _DONE:
                    break
                yield item
        finally:
            # 客户端断开时 Starlette 会关掉这个生成器，得让工作线程收手并交出会话锁
            self.stop_event.set()
            self._thread.join(timeout=5)

        if self.error is not None:
            raise self.error


class WebChatSession:
    """一个网页会话 = 一个独立 LLM 实例 + 一把串行锁。"""

    __slots__ = ("session_id", "target", "llm", "lock", "created_at", "last_used", "turns")

    def __init__(self, session_id: str, target: ModelTarget):
        self.session_id = session_id
        self.target = target
        self.llm = _build_llm(target)
        self.lock = threading.Lock()
        self.created_at = time.monotonic()
        self.last_used = self.created_at
        self.turns = 0

    def ensure_alive(self):
        with self.lock:
            if self.llm is None:
                raise SessionClosedError(self.session_id)

    def ask(self, question: str) -> str:
        # 同一个会话的请求串行执行：LLM 实例内部有可变记忆，并发调用会串上下文。
        with self.lock:
            if self.llm is None:
                raise SessionClosedError(self.session_id)
            answer = _collect(self.llm, question)
            self.turns += 1
            self.last_used = time.monotonic()
        return answer or EMPTY_REPLY

    def stream(self, question: str, stop_event: threading.Event | None = None):
        """逐片段产出回答；生成期间一直持有会话锁。"""
        stop_event = stop_event or threading.Event()

        with self.lock:
            if self.llm is None:
                raise SessionClosedError(self.session_id)
            try:
                for event in _call_chat(self.llm, question):
                    if stop_event.is_set():
                        # 中途放弃时生成器会被关闭，LLM 自己不会把半截回答写进短期记忆
                        break
                    if isinstance(event, str) and event:
                        yield event
            finally:
                self.turns += 1
                self.last_used = time.monotonic()

    def remember(self, question: str, answer: str) -> bool:
        """把一轮没有走模型的问答补进记忆。

        前端命中本地缓存时会跳过模型调用，这里把那一轮补回去，
        否则会话上下文会缺一块，"那它呢？"这类追问就接不上了。
        """
        with self.lock:
            if self.llm is None:
                raise SessionClosedError(self.session_id)

            memory = getattr(self.llm, "memory", None)
            if memory is None:
                return False

            memory.add_user_msg(question)
            memory.add_assistant_msg(answer)

            lt_memory = getattr(self.llm, "lt_memory", None)
            if lt_memory is not None:
                lt_memory.remember_turn(question, answer)

            self.turns += 1
            self.last_used = time.monotonic()
            return True

    def close(self):
        with self.lock:
            llm, self.llm = self.llm, None

        for name in ("close", "shutdown"):
            method = getattr(llm, name, None)
            if not callable(method):
                continue
            try:
                method()
            except Exception:  # noqa: BLE001 - 回收失败不该影响请求
                pass

    def info(self) -> dict:
        return {
            "session_id": self.session_id,
            "model": self.target.value,
            "backend": self.target.backend,
            "turns": self.turns,
            "idle": round(time.monotonic() - self.last_used, 3),
        }


class WebChatPool:
    """会话 → 独立 LLM 实例 的池子。"""

    def __init__(
        self,
        *,
        max_sessions: int = MAX_SESSIONS,
        ttl: float = SESSION_TTL,
        builder=None,
    ):
        self.max_sessions = max(1, int(max_sessions))
        self.ttl = max(0.0, float(ttl))
        self._builder = builder or self._default_builder

        self._lock = threading.RLock()
        self._sessions: "OrderedDict[str, WebChatSession]" = OrderedDict()
        self._instances_created = 0
        self._evicted = 0

    @staticmethod
    def _default_builder(session_id: str, target: ModelTarget) -> WebChatSession:
        return WebChatSession(session_id, target)

    @staticmethod
    def _normalize(session_id: str | None) -> str:
        session_id = (session_id or "").strip()
        return session_id or _DEFAULT_SESSION

    def _expired(self, session: WebChatSession, now: float) -> bool:
        return self.ttl > 0 and (now - session.last_used) > self.ttl

    def _acquire(self, session_id: str, target: ModelTarget) -> WebChatSession:
        """取（必要时建）会话。

        ``close()`` 会等在跑的请求结束，所以只在锁外回收：
        否则一个慢请求会把整个池子的锁占住。
        """
        now = time.monotonic()
        victims: list[WebChatSession] = []

        with self._lock:
            for key in [k for k, s in self._sessions.items() if self._expired(s, now)]:
                victims.append(self._sessions.pop(key))

            session = self._sessions.get(session_id)
            if session is not None and session.target.value != target.value:
                victims.append(self._sessions.pop(session_id))
                session = None

            if session is None:
                session = self._builder(session_id, target)
                self._sessions[session_id] = session
                self._instances_created += 1

                while len(self._sessions) > self.max_sessions:
                    _, victim = self._sessions.popitem(last=False)
                    victims.append(victim)
            else:
                session.last_used = now
                self._sessions.move_to_end(session_id)

        self._evicted += len(victims)
        for victim in victims:
            victim.close()
        return session

    def chat(self, model: str, question: str, session_id: str | None = None) -> str:
        target = registry.resolve(model)
        session = self._acquire(self._normalize(session_id), target)
        return session.ask(question)

    def remember(self, model: str, question: str, answer: str, session_id: str | None = None) -> bool:
        target = registry.resolve(model)
        session = self._acquire(self._normalize(session_id), target)
        return session.remember(question, answer)

    def stream(
        self,
        model: str,
        question: str,
        session_id: str | None = None,
        stop_event: threading.Event | None = None,
    ) -> StreamPump:
        """返回边生成边吐字的迭代器；模型/会话有问题会在返回前就抛出来。"""
        target = registry.resolve(model)
        session = self._acquire(self._normalize(session_id), target)
        session.ensure_alive()

        stop_event = stop_event or threading.Event()
        return StreamPump(session.stream(question, stop_event), stop_event)

    def reset(self, session_id: str | None = None) -> int:
        with self._lock:
            if session_id is None:
                victims = list(self._sessions.values())
                self._sessions.clear()
            else:
                key = self._normalize(session_id)
                session = self._sessions.pop(key, None)
                victims = [session] if session is not None else []

        for session in victims:
            session.close()
        self._evicted += len(victims)
        return len(victims)

    def stats(self) -> dict:
        now = time.monotonic()
        with self._lock:
            return {
                "sessions": len(self._sessions),
                "max_sessions": self.max_sessions,
                "ttl": self.ttl,
                "instances_created": self._instances_created,
                "evicted": self._evicted,
                "live": [
                    {**session.info(), "age": round(now - session.created_at, 3)}
                    for session in self._sessions.values()
                ],
            }

    def shutdown(self):
        self.reset(None)


pool = WebChatPool()
