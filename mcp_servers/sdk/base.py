import abc
import socket
import json
import threading
import concurrent.futures


class SDK(abc.ABC):
    @abc.abstractmethod
    def play_live2d_motion(self, motion: str, index: int):
        pass

    @abc.abstractmethod
    def play_live2d_expression(self, name: str):
        pass

    @abc.abstractmethod
    def get_live2d_motion(self) -> list:
        pass

    @abc.abstractmethod
    def get_live2d_expression(self) -> list:
        pass


class SDKTimeoutError(Exception):
    pass


class SDKRemoteError(Exception):
    pass


class UDPBase:
    def __init__(self, host, port, buffer_size=65536, max_workers=16):
        self._host = host
        self._port = port
        self._buffer_size = buffer_size
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._running = False
        self._recv_thread = None
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)

    @property
    def local_address(self):
        return self._sock.getsockname()

    def start(self):
        if self._running:
            return self
        self._sock.bind((self._host, self._port))
        self._sock.settimeout(0.5)
        self._running = True
        self._recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
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
        self.start()
        return self

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

    def _on_data(self, data, addr):
        raise NotImplementedError

    def _send(self, obj, addr):
        payload = json.dumps(obj).encode("utf-8")
        self._sock.sendto(payload, addr)
