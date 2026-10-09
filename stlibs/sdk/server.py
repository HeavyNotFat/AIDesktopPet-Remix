from __future__ import annotations

import inspect
import json
import logging
import threading
import time

from . import base
from .methods import METHOD_HELP, HostMethods

logger = logging.getLogger("sdk")

# 旧名字 -> 规范名字
ALIASES = {
    "play_motion": "play_live2d_motion",
    "play_expression": "play_live2d_expression",
    "list_motions": "get_live2d_motion",
    "list_expressions": "get_live2d_expression",
    "chat": "ask",
    "status": "get_status",
    "plugins": "list_plugins",
}

EVENTS = (
    "pet_click",       # 桌宠被点了一下（鼠标释放）
    "chat_finished",   # 一轮聊天结束
    "plugin_loaded",   # 插件加载完成
    "theme_changed",   # 主题热切换
)


class SDKServer(base.UDPBase):
    """宿主侧的 UDP 服务端。"""
    def __init__(self, host=base.DEFAULT_HOST, port=base.DEFAULT_PORT, max_workers=16,
                 token=None, methods: HostMethods | None = None):
        super().__init__(host, port, max_workers=max_workers, token=token)
        self.started_at = time.time()
        self.methods = methods or HostMethods(server=self, started_at=self.started_at)
        self._subscribers: dict = {}
        self._sub_lock = threading.Lock()
        self._event_seq = 0
        self.calls = 0
        self.errors = 0

    def _on_data(self, data, addr):
        try:
            request = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return

        if not isinstance(request, dict):
            return

        if request.get("type") == "subscribe":
            self._on_subscribe(request, addr)
            return

        request_id = request.get("id")
        method = request.get("method")
        args = request.get("args") or []
        kwargs = request.get("kwargs") or {}

        if not isinstance(args, list) or not isinstance(kwargs, dict):
            self._fail(addr, request_id, "args 必须是数组、kwargs 必须是对象", "bad_request")
            return

        if self.token and request.get("token") != self.token:
            self._fail(addr, request_id, "token 不对（见 ADP_SDK_TOKEN）", "unauthorized")
            return

        self.calls += 1
        try:
            result = self.invoke(method, args, kwargs)
        except base.SDKMethodError as exc:
            self._fail(addr, request_id, str(exc), exc.code)
        except Exception as exc:  # noqa: BLE001 - 服务端绝不能被一次调用带崩
            logger.exception("SDK 方法 %s 执行失败", method)
            self._fail(addr, request_id, f"{type(exc).__name__}: {exc}", "internal_error")
        else:
            self._send({"id": request_id, "result": result}, addr)

    def invoke(self, method, args=None, kwargs=None):
        """校验并调用一个方法（测试与内部复用都走它）。"""
        name = ALIASES.get(str(method or ""), str(method or ""))
        handler = self._resolve(name)
        if handler is None:
            raise base.SDKMethodError(f"没有这个方法：{method}（用 list_methods 看全部）")

        args = list(args or [])
        kwargs = dict(kwargs or {})
        self._check_signature(name, handler, args, kwargs)
        return handler(*args, **kwargs)

    def _resolve(self, name: str):
        if name not in METHOD_HELP:
            return None

        # 绑到实例上再取：普通方法与 staticmethod 都能按位置调用
        handler = getattr(self.methods, name, None)
        return handler if callable(handler) else None

    @staticmethod
    def _check_signature(name: str, handler, args, kwargs):
        parameters = list(inspect.signature(handler).parameters.values())
        positional = [
            item for item in parameters
            if item.kind in (item.POSITIONAL_ONLY, item.POSITIONAL_OR_KEYWORD)
        ]
        required = [item for item in positional if item.default is inspect.Parameter.empty]
        accepts_extra = any(item.kind is item.VAR_KEYWORD for item in parameters)

        if len(args) > len(positional):
            raise base.SDKMethodError(
                f"{name} 最多接受 {len(positional)} 个位置参数，给了 {len(args)} 个"
            )
        if len(args) < len(required):
            names = ", ".join(item.name for item in required)
            raise base.SDKMethodError(f"{name} 缺少必填参数：{names}")

        known = {item.name for item in parameters}
        for key in kwargs:
            if key not in known and not accepts_extra:
                raise base.SDKMethodError(f"{name} 不认识参数 {key}")

        bound = {item.name for item in positional[: len(args)]}
        missing = [item.name for item in required if item.name not in bound and item.name not in kwargs]
        if missing:
            raise base.SDKMethodError(f"{name} 缺少必填参数：{', '.join(missing)}")

    def _fail(self, addr, request_id, message, code):
        self.errors += 1
        self._send({"id": request_id, "error": str(message), "code": str(code)}, addr)

    def _on_subscribe(self, request: dict, addr):
        name = str(request.get("event") or "*")
        action = str(request.get("action") or "subscribe")
        with self._sub_lock:
            names = set(self._subscribers.get(addr, set()))
            if action == "unsubscribe":
                names.discard(name)
            else:
                names.add(name)
            if names:
                self._subscribers[addr] = names
            else:
                self._subscribers.pop(addr, None)
            total = len(self._subscribers)

        self._send({"id": request.get("id"), "result": {"event": name, "action": action,
                                                        "subscribers": total}}, addr)

    def emit(self, name: str, data=None) -> int:
        """给订阅者推一条事件；返回实际发出去的份数。"""
        with self._sub_lock:
            targets = [
                addr for addr, names in self._subscribers.items()
                if "*" in names or name in names
            ]
            self._event_seq += 1
            seq = self._event_seq

        payload = {"type": "event", "name": name, "data": data, "seq": seq, "time": time.time()}
        sent = 0
        for addr in targets:
            if self._send(payload, addr):
                sent += 1
        return sent

    def subscribers(self) -> dict:
        with self._sub_lock:
            return {addr: sorted(names) for addr, names in self._subscribers.items()}

    def status(self) -> dict:
        return {
            "running": self._running,
            "address": self.local_address if self._running else None,
            "token": bool(self.token),
            "calls": self.calls,
            "errors": self.errors,
            "subscribers": len(self._subscribers),
            "methods": len(METHOD_HELP),
            "uptime": round(time.time() - self.started_at, 3),
        }


__all__ = ["ALIASES", "EVENTS", "METHOD_HELP", "HostMethods", "SDKServer"]
