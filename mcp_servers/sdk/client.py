import uuid
import threading
import json

from . import base


class SDKClient(base.UDPBase, base.SDK):
    def __init__(self, server_host, server_port, local_host="0.0.0.0", local_port=0,
                 timeout=5, max_workers=16):
        base.UDPBase.__init__(self, local_host, local_port, max_workers=max_workers)
        self._server_addr = (server_host, server_port)
        self._timeout = timeout
        self._pending = {}
        self._lock = threading.Lock()

    def _on_data(self, data, addr):
        try:
            resp = json.loads(data.decode("utf-8"))
        except Exception:
            return
        req_id = resp.get("id")
        with self._lock:
            entry = self._pending.pop(req_id, None)
        if entry is None:
            return
        event, box = entry
        box["response"] = resp
        event.set()

    def _call(self, method, *args, **kwargs):
        if not self._running:
            self.start()
        req_id = str(uuid.uuid4())
        event = threading.Event()
        box = {}
        with self._lock:
            self._pending[req_id] = (event, box)
        payload = {"id": req_id, "method": method, "args": list(args), "kwargs": kwargs}
        self._send(payload, self._server_addr)
        ok = event.wait(self._timeout)
        with self._lock:
            self._pending.pop(req_id, None)
        if not ok:
            raise base.SDKTimeoutError("timeout waiting for %s" % method)
        resp = box["response"]
        if "error" in resp:
            raise base.SDKRemoteError(resp["error"])
        return resp.get("result")

    def play_live2d_motion(self, motion: str, index: int):
        return self._call("play_live2d_motion", motion, index)

    def play_live2d_expression(self, name: str):
        return self._call("play_live2d_expression", name)

    def get_live2d_motion(self) -> list:
        return self._call("get_live2d_motion")

    def get_live2d_expression(self) -> list:
        return self._call("get_live2d_expression")
