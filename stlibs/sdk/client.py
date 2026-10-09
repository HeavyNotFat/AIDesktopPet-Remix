from __future__ import annotations

import json
import threading
import time
import uuid

from . import base

DEFAULT_TIMEOUT = 5.0


class SDKClient(base.UDPBase):
    def __init__(self, server_host=base.DEFAULT_HOST, server_port=base.DEFAULT_PORT,
                 local_host="0.0.0.0", local_port=0, timeout=DEFAULT_TIMEOUT,
                 max_workers=16, token=None):
        super().__init__(local_host, local_port, max_workers=max_workers, token=token)
        self._server_addr = (server_host, server_port)
        self._timeout = float(timeout)
        self._pending: dict = {}
        self._lock = threading.Lock()
        self._handlers: dict = {}
        self._events: list = []
        self._closed = False

    def _on_data(self, data, addr):
        try:
            message = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return

        if message.get("type") == "event":
            self._dispatch_event(message)
            return

        request_id = message.get("id")
        with self._lock:
            entry = self._pending.pop(request_id, None)
        if entry is None:
            return
        event, box = entry
        box["response"] = message
        event.set()

    def _dispatch_event(self, message: dict):
        self._events.append(message)
        name = message.get("name")
        with self._lock:
            handlers = list(self._handlers.get(name, ())) + list(self._handlers.get("*", ()))
        for handler in handlers:
            try:
                handler(message.get("data"), message)
            except Exception as exc:  # noqa: BLE001 - 订阅者自己的异常不该影响收包
                print(f"[sdk] 事件处理失败（{name}）：{type(exc).__name__}: {exc}")

    def _call(self, method, *args, timeout=None, **kwargs):
        if self._closed:
            raise base.SDKError("客户端已经关了")
        if not self._running:
            self.start()

        request_id = uuid.uuid4().hex
        event = threading.Event()
        box = {}
        with self._lock:
            self._pending[request_id] = (event, box)

        payload = {"id": request_id, "method": method, "args": list(args), "kwargs": kwargs}
        if self.token:
            payload["token"] = self.token

        self._send(payload, self._server_addr)
        if not event.wait(timeout or self._timeout):
            with self._lock:
                self._pending.pop(request_id, None)
            raise base.SDKTimeoutError(f"等 {method} 的响应超时（{timeout or self._timeout}s）")

        response = box["response"]
        if "error" in response:
            raise base.SDKRemoteError(response["error"], response.get("code", "remote_error"))
        return response.get("result")

    def close(self):
        self._closed = True
        self.stop()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def subscribe(self, event="*"):
        """订阅事件（``'*'`` 表示全部）。"""
        return self._subscribe(event, "subscribe")

    def unsubscribe(self, event="*"):
        return self._subscribe(event, "unsubscribe")

    def _subscribe(self, event, action):
        if self._closed:
            raise base.SDKError("客户端已经关了")
        if not self._running:
            self.start()

        request_id = uuid.uuid4().hex
        latch = threading.Event()
        box = {}
        with self._lock:
            self._pending[request_id] = (latch, box)

        self._send({"id": request_id, "type": "subscribe", "event": event, "action": action},
                   self._server_addr)
        if not latch.wait(self._timeout):
            with self._lock:
                self._pending.pop(request_id, None)
            raise base.SDKTimeoutError(f"订阅 {event} 超时")
        return box["response"].get("result")

    def on(self, event, handler):
        """注册事件回调：``handler(data, message)``。"""
        with self._lock:
            self._handlers.setdefault(event, []).append(handler)
        return handler

    def off(self, event, handler=None):
        with self._lock:
            if handler is None:
                self._handlers.pop(event, None)
            else:
                handlers = self._handlers.get(event) or []
                self._handlers[event] = [item for item in handlers if item is not handler]

    def wait_event(self, name=None, timeout=5.0):
        """等一条事件，返回事件字典或 None。"""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for index, message in enumerate(self._events):
                if name is None or message.get("name") == name:
                    return self._events.pop(index)
            time.sleep(0.02)
        return None

    @property
    def events(self) -> list:
        return list(self._events)

    def ping(self, timeout=None):
        return self._call("ping", timeout=timeout)

    def version(self):
        return self._call("version")

    def list_methods(self):
        return self._call("list_methods")

    def get_status(self):
        return self._call("get_status")

    def emit_event(self, name, data=None):
        return self._call("emit_event", name, data)

    def server_status(self):
        """客户端视角的连接信息（不发请求）。"""
        return {"server": self._server_addr, "local": self.local_address,
                "running": self._running, "timeout": self._timeout}

    def notify(self, text, level="info", timeout=2600):
        return self._call("notify", text, level, timeout)

    def play_live2d_motion(self, motion: str, index: int = 0):
        return self._call("play_live2d_motion", motion, index)

    def play_live2d_expression(self, name: str):
        return self._call("play_live2d_expression", name)

    def get_live2d_motion(self) -> list:
        return self._call("get_live2d_motion")

    def get_live2d_expression(self) -> list:
        return self._call("get_live2d_expression")

    def get_appearance(self):
        return self._call("get_appearance")

    def set_appearance(self, size=None, opacity=None, rotate=None):
        return self._call("set_appearance", size, opacity, rotate)

    def send_to_chat(self, text, role="assistant"):
        return self._call("send_to_chat", text, role)

    def get_chat_history(self):
        return self._call("get_chat_history")

    def clear_chat(self):
        return self._call("clear_chat")

    def ask(self, question, model=None, timeout=180.0):
        return self._call("ask", question, model, timeout=timeout)

    def get_config(self, key=None):
        return self._call("get_config", key)

    def set_config(self, key, value):
        return self._call("set_config", key, value)

    def list_plugins(self):
        return self._call("list_plugins")

    def trigger_plugin_action(self, action):
        return self._call("trigger_plugin_action", action)

    def run_plugin_command(self, text):
        return self._call("run_plugin_command", text)

    def memory_stats(self):
        return self._call("memory_stats")

    def memory_recall(self, query, top_k=3):
        return self._call("memory_recall", query, top_k)

    def memory_clear(self, scope=None):
        return self._call("memory_clear", scope)


__all__ = ["DEFAULT_TIMEOUT", "SDKClient"]
