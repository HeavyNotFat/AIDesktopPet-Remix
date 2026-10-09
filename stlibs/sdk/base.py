import abc
import concurrent.futures
import json
import os
import socket
import threading
import time

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9000
MAX_DATAGRAM = 1 << 16
PROTOCOL_VERSION = 2


class SDKError(Exception):
    """SDK 相关错误的基类。"""
    code = "sdk_error"


class SDKTimeoutError(SDKError):
    code = "timeout"


class SDKRemoteError(SDKError):
    """对端返回了错误。``code`` 是机器可读的原因。"""
    code = "remote_error"

    def __init__(self, message, code="remote_error"):
        super().__init__(message)
        self.code = code


class SDKMethodError(SDKError):
    """方法内部拒绝了这个请求（参数不对、界面没起来）。"""
    code = "method_error"


class UDPBase(abc.ABC):
    def __init__(self, host, port, buffer_size=MAX_DATAGRAM, max_workers=16, token=None):
        self._host = host
        self._port = port
        self._buffer_size = buffer_size
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._running = False
        self._recv_thread = None
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
        self.token = token if token is not None else os.getenv("ADP_SDK_TOKEN") or None

    @property
    def local_address(self):
        return self._sock.getsockname()

    @property
    def running(self) -> bool:
        return self._running

    def start(self):
        if self._running:
            return self

        self._sock.bind((self._host, self._port))
        self._sock.settimeout(0.5)
        self._running = True
        self._recv_thread = threading.Thread(target=self._recv_loop, daemon=True, name="sdk-recv")
        self._recv_thread.start()
        return self

    def stop(self):
        self._running = False
        if self._recv_thread is not None:
            self._recv_thread.join(timeout=2)
        try:
            self._sock.close()
        except OSError:
            pass
        self._executor.shutdown(wait=False)

    def __enter__(self):
        return self.start()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()

    def _recv_loop(self):
        while self._running:
            try:
                data, addr = self._sock.recvfrom(self._buffer_size)
            except socket.timeout:
                continue
            except OSError:
                break
            self._executor.submit(self._on_data, data, addr)

    @abc.abstractmethod
    def _on_data(self, data, addr):
        raise NotImplementedError

    def _send(self, obj, addr):
        try:
            self._sock.sendto(json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8"), addr)
        except OSError:
            return False
        return True


__all__ = [
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "MAX_DATAGRAM",
    "PROTOCOL_VERSION",
    "SDKError",
    "SDKMethodError",
    "SDKRemoteError",
    "SDKTimeoutError",
    "UDPBase",
    "time",
]
