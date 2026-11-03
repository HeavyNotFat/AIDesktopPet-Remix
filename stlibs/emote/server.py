import json
import mimetypes
import os
import re
import threading

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

from . import ROOT, RUNTIME_ROOT, SOUNDS_ROOT, find_model


MIME_TYPES = {
    ".js": "application/javascript; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".wasm": "application/wasm",
    ".psb": "application/octet-stream",
    ".zip": "application/zip",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
}

MODEL_PATH = re.compile(r"^/model/([^/]+)/(.+)$")


def _safe_join(root: str, relative: str) -> str:
    root = os.path.abspath(root)
    target = os.path.abspath(os.path.join(root, relative))
    if os.path.commonpath([root, target]) != root:
        raise ValueError("path escapes root")
    return target


def _read_range(path: str, start: int, length: int) -> bytes:
    with open(path, "rb") as handle:
        handle.seek(start)
        return handle.read(length)


class _Handler(BaseHTTPRequestHandler):
    server_version = "ADPEmote/1.0"

    def log_message(self, *_args):
        return

    @property
    def emote_server(self):
        return self.server

    def do_HEAD(self):
        self._serve(head=True)

    def do_GET(self):
        self._serve(head=False)

    def _serve(self, head: bool):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if path in ("/", "/index.html"):
            self._serve_html(head)
            return
        if path == "/favicon.ico":
            self._empty(head)
            return
        if path.startswith("/runtime/"):
            self._serve_file(os.path.join(RUNTIME_ROOT, path[len("/runtime/"):]), head)
            return
        if path.startswith("/sounds/"):
            self._serve_file(_safe_join(SOUNDS_ROOT, path[len("/sounds/"):]), head)
            return

        match = MODEL_PATH.match(path)
        if match:
            model_name, relative = match.group(1), match.group(2)
            model = find_model(model_name)
            if model is None:
                self._empty(head, HTTPStatus.NOT_FOUND)
                return
            try:
                target = _safe_join(model.directory, relative)
            except ValueError:
                self._empty(head, HTTPStatus.FORBIDDEN)
                return
            self._serve_file(target, head)
            return

        self._empty(head, HTTPStatus.NOT_FOUND)

    def _serve_html(self, head: bool):
        try:
            with open(os.path.join(RUNTIME_ROOT, "index.html"), "r", encoding="utf-8") as handle:
                template = handle.read()
        except OSError:
            self._empty(head, HTTPStatus.NOT_FOUND)
            return

        bootstrap = getattr(self.emote_server, "bootstrap", {}) or {}
        payload = json.dumps(bootstrap, ensure_ascii=False).replace("</", "<\\/")
        html = template.replace("/*__EMOTE_BOOTSTRAP__*/", f"window.EMOTE_CONFIG = {payload};")
        body = html.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if not head:
            self.wfile.write(body)

    def _serve_file(self, path: str, head: bool):
        try:
            path = os.path.abspath(path)
            if not os.path.isfile(path):
                self._empty(head, HTTPStatus.NOT_FOUND)
                return
            size = os.path.getsize(path)
            suffix = os.path.splitext(path)[1].lower()
            content_type = MIME_TYPES.get(suffix) or mimetypes.guess_type(path)[0] or "application/octet-stream"
            start, end = 0, size - 1
            status = HTTPStatus.OK
            range_header = self.headers.get("Range")
            if range_header and range_header.startswith("bytes="):
                try:
                    raw_start, raw_end = range_header[len("bytes="):].split("-", 1)
                    start = int(raw_start) if raw_start else 0
                    end = int(raw_end) if raw_end else size - 1
                except (ValueError, TypeError):
                    start, end = 0, size - 1
                start = max(0, min(start, size - 1))
                end = max(start, min(end, size - 1))
                status = HTTPStatus.PARTIAL_CONTENT

            length = end - start + 1
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(length))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-cache")
            if status == HTTPStatus.PARTIAL_CONTENT:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            if not head:
                self.wfile.write(_read_range(path, start, length))
        except (OSError, ValueError):
            self._empty(head, HTTPStatus.NOT_FOUND)

    def _empty(self, head: bool, status=HTTPStatus.NO_CONTENT):
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()


class EmoteAssetServer:
    """给 QtWebEngine 提供 Emote 运行时与模型文件。"""

    def __init__(self, bootstrap: dict | None = None, host: str = "127.0.0.1", port: int = 0):
        self.host = host
        self.port = int(port)
        self.bootstrap = dict(bootstrap or {})
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._server is not None

    @property
    def base_url(self) -> str:
        port = self._server.server_address[1] if self._server is not None else self.port
        return f"http://{self.host}:{port}"

    def start(self) -> "EmoteAssetServer":
        if self._server is not None:
            return self
        os.makedirs(ROOT, exist_ok=True)
        os.makedirs(RUNTIME_ROOT, exist_ok=True)
        os.makedirs(SOUNDS_ROOT, exist_ok=True)
        server = ThreadingHTTPServer((self.host, self.port), _Handler)
        server.daemon_threads = True
        server.bootstrap = self.bootstrap
        self._server = server
        self._thread = threading.Thread(target=server.serve_forever, name="emote-assets", daemon=True)
        self._thread.start()
        return self

    def set_bootstrap(self, bootstrap: dict):
        self.bootstrap = dict(bootstrap or {})
        if self._server is not None:
            self._server.bootstrap = self.bootstrap

    def stop(self):
        server, thread = self._server, self._thread
        self._server = None
        self._thread = None
        if server is not None:
            server.shutdown()
            server.server_close()
        if thread is not None and thread.is_alive():
            thread.join(timeout=2)

    def __enter__(self):
        return self.start()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()


__all__ = ["EmoteAssetServer", "MIME_TYPES"]
