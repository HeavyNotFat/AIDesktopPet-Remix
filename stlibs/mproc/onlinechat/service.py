import threading
import time


class OnlineChatService:
    """在后台线程里起停网页聊天服务。"""

    def __init__(self, host: str | None = None, port: int | None = None):
        self.host = host
        self.port = port
        self._server = None
        self._thread = None
        self._error = ""

    @property
    def running(self) -> bool:
        return bool(self._thread is not None and self._thread.is_alive())

    @property
    def error(self) -> str:
        return self._error

    def start(self) -> bool:
        if self.running:
            return True

        from ... import ai_enabled

        if not ai_enabled():
            self._error = "AI 功能总开关已关闭"
            return False

        import uvicorn

        from . import app, config

        host = self.host or config.HOST
        port = int(self.port or config.PORT)
        server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="warning"))
        thread = threading.Thread(target=self._run, args=(server,), name="onlinechat", daemon=True)
        self._server = server
        self._thread = thread
        self._error = ""
        thread.start()

        for _ in range(30):
            if getattr(server, "started", False) or not thread.is_alive():
                break
            time.sleep(0.05)
        if not thread.is_alive():
            self._error = "网页聊天服务启动失败（端口可能被占用）"
            return False
        return True

    def _run(self, server):
        try:
            server.run()
        except Exception as exc:  # noqa: BLE001 - 服务挂了不能带崩桌面端
            self._error = f"{type(exc).__name__}: {exc}"

    def stop(self) -> None:
        server, thread = self._server, self._thread
        self._server = None
        self._thread = None
        if server is not None:
            server.should_exit = True
        if thread is not None and thread.is_alive():
            thread.join(timeout=4)

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()


def main():
    from . import main as run

    run()


__all__ = ["OnlineChatService", "main"]
