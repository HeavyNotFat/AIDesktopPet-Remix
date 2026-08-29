import json

from . import base
from .. import SharingData


class SDKServer(base.UDPBase):
    def __init__(self, host="127.0.0.1", port=9000, max_workers=16):
        base.UDPBase.__init__(self, host, port, max_workers=max_workers)

    def _on_data(self, data, addr):
        try:
            req = json.loads(data.decode("utf-8"))
        except Exception:
            return
        req_id = req.get("id")
        method = req.get("method")
        args = req.get("args", [])
        kwargs = req.get("kwargs", {})
        func = getattr(self, method)
        try:
            result = func(*args, **kwargs)
            self._send({"id": req_id, "result": result}, addr)
        except Exception as e:
            self._send({"id": req_id, "error": str(e)}, addr)

    @staticmethod
    def get_live2d_motion():
        return SharingData.motions if SharingData.motions else "No Motion Data"

    @staticmethod
    def get_live2d_expression():
        return SharingData.expressions if SharingData.expressions else "No Expression Data"

    @staticmethod
    def play_live2d_motion(name: str, index: int):
        SharingData.setting_window.live2d_mot_signal.emit([name, index])
        return "Operate Successfully"

    @staticmethod
    def play_live2d_expression(name: str):
        SharingData.setting_window.live2d_exp_signal.emit([name])
        return "Operate Successfully"
