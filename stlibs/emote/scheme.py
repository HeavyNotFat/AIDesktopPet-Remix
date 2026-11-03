import json
import mimetypes
import os

from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtWebEngineCore import (
    QWebEngineProfile, QWebEngineUrlRequestJob, QWebEngineUrlScheme, QWebEngineUrlSchemeHandler,
)

from . import RUNTIME_ROOT, SOUNDS_ROOT, find_model
from .server import MIME_TYPES, _safe_join


SCHEME = b'adpemote'
HOST = 'app'
BASE_URL = f"adpemote://{HOST}/"

_registered = False


def register_scheme():
    """在创建 QApplication / WebEngineProfile 之前注册私有协议。"""
    global _registered

    if _registered:
        return
    scheme = QWebEngineUrlScheme(SCHEME)
    scheme.setSyntax(QWebEngineUrlScheme.Syntax.HostAndPort)
    scheme.setDefaultPort(80)
    scheme.setFlags(
        QWebEngineUrlScheme.Flag.SecureScheme
        | QWebEngineUrlScheme.Flag.LocalAccessAllowed
        | QWebEngineUrlScheme.Flag.FetchApiAllowed
        | QWebEngineUrlScheme.Flag.CorsEnabled
    )
    QWebEngineUrlScheme.registerScheme(scheme)
    _registered = True


def page_html(bootstrap: dict) -> bytes:
    with open(os.path.join(RUNTIME_ROOT, 'index.html'), 'r', encoding='utf-8') as handle:
        template = handle.read()
    payload = json.dumps(bootstrap, ensure_ascii=False).replace('</', '<\\/')
    return template.replace('/*__EMOTE_BOOTSTRAP__*/', f'window.EMOTE_CONFIG = {payload};').encode('utf-8')


class EmoteSchemeHandler(QWebEngineUrlSchemeHandler):
    def __init__(self, bootstrap=None, parent=None):
        super().__init__(parent)
        self.bootstrap = dict(bootstrap or {})

    def set_bootstrap(self, bootstrap):
        self.bootstrap = dict(bootstrap or {})

    def _reply(self, job, data: bytes, content_type: str):
        buffer = QBuffer(job)
        buffer.setData(data)
        buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        job.reply(content_type.encode('utf-8'), buffer)

    def _reply_file(self, job, path: str):
        try:
            path = os.path.abspath(path)
            if not os.path.isfile(path):
                job.fail(QWebEngineUrlRequestJob.Error.UrlNotFound)
                return
            with open(path, 'rb') as handle:
                data = handle.read()
            suffix = os.path.splitext(path)[1].lower()
            content_type = MIME_TYPES.get(suffix) or mimetypes.guess_type(path)[0] or 'application/octet-stream'
            self._reply(job, data, content_type)
        except OSError:
            job.fail(QWebEngineUrlRequestJob.Error.UrlNotFound)

    def requestStarted(self, job):
        path = job.requestUrl().path() or '/'
        if path in ('/', '/index.html'):
            try:
                self._reply(job, page_html(self.bootstrap), 'text/html; charset=utf-8')
            except OSError:
                job.fail(QWebEngineUrlRequestJob.Error.UrlNotFound)
            return
        if path.startswith('/runtime/'):
            self._reply_file(job, os.path.join(RUNTIME_ROOT, path[len('/runtime/'):]))
            return
        if path.startswith('/sounds/'):
            try:
                self._reply_file(job, _safe_join(SOUNDS_ROOT, path[len('/sounds/'):]))
            except ValueError:
                job.fail(QWebEngineUrlRequestJob.Error.UrlNotFound)
            return
        if path.startswith('/model/'):
            rest = path[len('/model/'):]
            name, _sep, relative = rest.partition('/')
            model = find_model(name)
            if model is None or not relative:
                job.fail(QWebEngineUrlRequestJob.Error.UrlNotFound)
                return
            try:
                self._reply_file(job, _safe_join(model.directory, relative))
            except ValueError:
                job.fail(QWebEngineUrlRequestJob.Error.UrlNotFound)
            return
        job.fail(QWebEngineUrlRequestJob.Error.UrlNotFound)


_handler = None


def install_handler(bootstrap: dict) -> EmoteSchemeHandler:
    """在默认 profile 上安装私有协议处理器；同一个进程只装一个。"""
    global _handler

    register_scheme()
    if _handler is None:
        _handler = EmoteSchemeHandler(bootstrap)
        QWebEngineProfile.defaultProfile().installUrlSchemeHandler(SCHEME, _handler)
    else:
        _handler.set_bootstrap(bootstrap)
    return _handler


__all__ = [
    'BASE_URL', 'EmoteSchemeHandler', 'HOST', 'SCHEME', 'install_handler', 'page_html',
    'register_scheme',
]