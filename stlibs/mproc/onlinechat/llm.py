from __future__ import annotations

import inspect
import threading
import time
from collections import OrderedDict

from .config import MAX_SESSIONS, SESSION_TTL
from .registry import ModelTarget, registry

#: 模型返回空内容时的兜底文案（保持与原 ``llm.generate`` 一致）
EMPTY_REPLY = "（模型返回了空内容）"


class SessionClosedError(RuntimeError):
    """会话在请求开始前被回收（TTL / LRU / /api/reset 撞车）。"""

    def __init__(self, session_id: str):
        self.session_id = session_id
        super().__init__(f"会话 {session_id!r} 已回收，请重新发送")

#: 这些参数是「要不要通知桌面端 UI」的开关，必须显式关掉。
#: 其余参数里第一个被当成用户消息。
_CONTROL_PARAMS = frozenset({"should_emit", "emit"})

_DEFAULT_SESSION = "default"


def _build_llm(target: ModelTarget):
    """按 target 新建一个实例。**每次都新建**，不查任何缓存。"""
    from ...ai import cloud, local

    if target.is_cloud:
        return cloud.LLM(target.model, target.api_key, target.base_url)
    return local.LLM(target.model)


def _call_chat(llm, question: str):
    """以「不向 UI 发信号」的方式调用 ``llm.chat``。

    ``local.LLM.chat(user_input, should_emit=True)`` 与
    ``cloud.LLM.chat(query)`` 参数名不同，这里按签名匹配，
    并把所有控制开关显式关掉，避免实例把记忆推给桌面端界面。
    """
    parameters = inspect.signature(llm.chat).parameters
    message_params = [name for name in parameters if name not in _CONTROL_PARAMS]
    if not message_params:
        raise TypeError(f"{type(llm).__name__}.chat 没有可识别的消息参数：{list(parameters)}")

    kwargs = {name: False for name in parameters if name in _CONTROL_PARAMS}
    kwargs[message_params[0]] = question
    return llm.chat(**kwargs)


def _collect(llm, question: str) -> str:
    """把流式输出收集成整段文本，忽略 tool_call / audio 等事件。"""
    chunks: list[str] = []
    for event in _call_chat(llm, question):
        if isinstance(event, str):
            chunks.append(event)
    return "".join(chunks)


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

    def ask(self, question: str) -> str:
        # 同一个会话的请求串行执行：LLM 实例内部有可变记忆，并发调用会串上下文。
        with self.lock:
            # _acquire() 放锁到 ask() 拿锁之间有一个窗口：这期间别的线程可能
            # TTL/LRU/reset 把这个会话回收掉（self.llm 置 None）。
            # 这里给一个明确的异常，而不是让 None 冒到 inspect.signature 里。
            if self.llm is None:
                raise SessionClosedError(self.session_id)
            answer = _collect(self.llm, question)
            self.turns += 1
            self.last_used = time.monotonic()
        return answer or EMPTY_REPLY

    def close(self) -> None:
        """尽力释放实例持有的资源；实例接口不统一，所以只做鸭子类型调用。"""
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

        ``close()`` 会等在跑的请求结束，所以**只在锁外**回收：
        否则一个慢请求会把整个池子的锁占住。
        """
        now = time.monotonic()
        victims: list[WebChatSession] = []

        with self._lock:
            for key in [k for k, s in self._sessions.items() if self._expired(s, now)]:
                victims.append(self._sessions.pop(key))

            session = self._sessions.get(session_id)
            # 换模型必须重建实例：旧实例的 system prompt / 记忆 / 工具集都属于旧模型。
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
        """用 ``model`` 对应的**新实例**回答 ``question``。"""
        target = registry.resolve(model)
        session = self._acquire(self._normalize(session_id), target)
        return session.ask(question)

    def reset(self, session_id: str | None = None) -> int:
        """丢弃会话（记忆 + 实例）。``session_id=None`` 时清空全部。"""
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
                    {
                        **session.info(),
                        "age": round(now - session.created_at, 3),
                    }
                    for session in self._sessions.values()
                ],
            }

    def shutdown(self) -> None:
        self.reset(None)


#: 进程级默认池，路由直接用它
pool = WebChatPool()
