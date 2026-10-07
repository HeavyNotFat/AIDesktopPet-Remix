from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Iterator

from ..core import Finding, Location, Severity

WEB_DIR = "resources/web"
PY_API_MODULE = "stlibs/mproc/onlinechat/__init__.py"
JS_CONFIG = "resources/web/onlinechat/js/config.js"
JS_HTML = "resources/web/onlinechat/index.html"

_ROUTE_RE = re.compile(r"@api\.(get|post|put|delete)\(\s*['\"]([^'\"]+)['\"]")
_CALL_POST_RE = re.compile(r"\b(?:post|fetchJSON|request)\(\s*['\"]([^'\"]+)['\"]")
_PREFIX_RE = re.compile(r"APIRouter\(\s*prefix\s*=\s*['\"]([^'\"]+)['\"]")
_EXPORT_RE = re.compile(r"QW\.(\w+)\s*=\s*\{([^}]*)\}")
_SHORTHAND_DESTRUCTURE_RE = re.compile(r"(?:const|let|var)\s*\{([^}]*)\}\s*=\s*QW\.(\w+)")
_MEMBER_USE_RE = re.compile(r"\bQW\.(\w+)\.(\w+)")
_DOM_ID_RE = re.compile(r"""(?:getElementById|\$)\(\s*['"]([^'"]+)['"]""")
_HTML_ID_RE = re.compile(r"""\bid\s*=\s*["']([^"']+)["']""")
_SCRIPT_SRC_RE = re.compile(r"""<script[^>]+src\s*=\s*["']([^"']+)["']""")
_PORT_RE = re.compile(r"https?://[^/'\"]*:(\d+)")
_PY_PORT_RE = re.compile(r"PORT\s*=\s*int\(os\.getenv\([^,]+,\s*['\"](\d+)['\"]\)")


def _js_files(ctx) -> list[Path]:
    root = ctx.root / WEB_DIR
    if not root.is_dir():
        return []
    return sorted(path for path in root.rglob("*.js") if path.is_file())


def _rel(ctx, path: Path) -> str:
    return path.relative_to(ctx.root).as_posix()


def _routes(ctx) -> tuple[str, set[str]]:
    src = ctx.sources.source(PY_API_MODULE)
    if src is None:
        return "/api", set()
    prefix_match = _PREFIX_RE.search(src.text)
    prefix = prefix_match.group(1) if prefix_match else ""
    routes = {f"{prefix}{path}" for _, path in _ROUTE_RE.findall(src.text)}
    return prefix, routes


def check_api_route(ctx) -> Iterator[Finding]:
    _, routes = _routes(ctx)
    if not routes:
        yield Finding(
            check="web/api-route",
            severity=Severity.ERROR,
            message=f"在 {PY_API_MODULE} 里没有解析到任何 @api 路由，无法校验前端调用",
            location=Location(PY_API_MODULE, 1),
            hint="确认路由仍然用 @api.post('/xxx') 形式声明",
        )
        return

    for path in _js_files(ctx):
        rel = _rel(ctx, path)
        text = path.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), 1):
            for called in _CALL_POST_RE.findall(line):
                if not called.startswith("/"):
                    continue
                full = f"/api{called}"
                if full in routes:
                    continue
                yield Finding(
                    check="web/api-route",
                    severity=Severity.ERROR,
                    message=f"{rel} 调用了 {called}，但后端没有这个接口（可用：{'、'.join(sorted(routes))}）",
                    location=Location(rel, lineno),
                    hint="在 onlinechat/__init__.py 里补路由，或修正前端路径",
                )


def check_api_port(ctx) -> Iterator[Finding]:
    config = ctx.root / JS_CONFIG
    backend_config = ctx.root / PY_API_MODULE
    backend_config = backend_config.parent / "config.py"
    if not config.is_file() or not backend_config.is_file():
        return
    js_port = _PORT_RE.search(config.read_text(encoding="utf-8", errors="replace"))
    py_port = _PY_PORT_RE.search(backend_config.read_text(encoding="utf-8"))
    if not js_port or not py_port:
        return
    if js_port.group(1) == py_port.group(1):
        return
    yield Finding(
        check="web/api-port",
        severity=Severity.ERROR,
        message=(
            f"前端 API 端口是 {js_port.group(1)}，后端默认端口是 {py_port.group(1)}，"
            "网页会连不上（除非用环境变量覆盖）"
        ),
        location=Location(JS_CONFIG, 1),
        hint="两端保持一致",
    )


def _exports(ctx) -> tuple[dict[str, set[str]], dict[str, str]]:
    """``{命名空间: {成员}}`` 与 ``{命名空间: 文件}``。"""
    exports: dict[str, set[str]] = {}
    sources: dict[str, str] = {}
    for path in _js_files(ctx):
        rel = _rel(ctx, path)
        text = path.read_text(encoding="utf-8", errors="replace")
        for name, body in _EXPORT_RE.findall(text):
            members = exports.setdefault(name, set())
            members |= _object_keys(body)
            sources.setdefault(name, rel)
    return exports, sources


def _object_keys(body: str) -> set[str]:
    keys = set(re.findall(r"([A-Za-z_$][\w$]*)\s*:", body))
    keys |= set(re.findall(r"(?:^|[,{\s])([A-Za-z_$][\w$]*)\s*(?=[,}]|$)", body))
    # 取值器/设值器也是导出：{ get pending() {...} } 一样能被 QW.x.pending 取到
    keys |= set(re.findall(r"\b(?:get|set)\s+([A-Za-z_$][\w$]*)\s*\(", body))
    return {key for key in keys if key}


def check_config_key(ctx) -> Iterator[Finding]:
    exports, _ = _exports(ctx)
    config_keys = exports.get("config", set())
    if not config_keys:
        return

    for path in _js_files(ctx):
        rel = _rel(ctx, path)
        text = path.read_text(encoding="utf-8", errors="replace")
        used: dict[str, int] = {}
        for lineno, line in enumerate(text.splitlines(), 1):
            for match in _SHORTHAND_DESTRUCTURE_RE.finditer(line):
                if match.group(2) != "config":
                    continue
                for key in re.split(r"[,\s]+", match.group(1)):
                    key = key.split(":")[0].strip()
                    if key:
                        used.setdefault(key, lineno)
            for match in re.finditer(r"QW\.config\.(\w+)", line):
                used.setdefault(match.group(1), lineno)
        for key, lineno in sorted(used.items(), key=lambda item: item[1]):
            if key in config_keys:
                continue
            yield Finding(
                check="web/config-key",
                severity=Severity.ERROR,
                message=(
                    f"{rel} 取用 QW.config.{key}，但 config.js 里没有定义，运行期是 undefined"
                    "（例如 localStorage 会退化成读写 \"undefined\" 这个键）"
                ),
                location=Location(rel, lineno, f"QW.config.{key}"),
                hint=f"在 {JS_CONFIG} 里补上 {key}",
            )


def check_dom_id(ctx) -> Iterator[Finding]:
    html = ctx.root / JS_HTML
    if not html.is_file():
        return
    text = html.read_text(encoding="utf-8", errors="replace")
    html_ids = set(_HTML_ID_RE.findall(text))
    if not html_ids:
        return

    for path in _js_files(ctx):
        rel = _rel(ctx, path)
        js = path.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(js.splitlines(), 1):
            for dom_id in _DOM_ID_RE.findall(line):
                if dom_id in html_ids:
                    continue
                yield Finding(
                    check="web/dom-id",
                    severity=Severity.ERROR,
                    message=f"{rel} 取 DOM 元素 #{dom_id}，但 {JS_HTML} 里没有这个 id",
                    location=Location(rel, lineno, dom_id),
                    hint="补上元素或修正 id",
                )


def check_namespace(ctx) -> Iterator[Finding]:
    exports, sources = _exports(ctx)
    if not exports:
        return

    reported: set[tuple[str, str]] = set()
    for path in _js_files(ctx):
        rel = _rel(ctx, path)
        text = path.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), 1):
            for namespace, member in _MEMBER_USE_RE.findall(line):
                if namespace not in exports:
                    continue
                if member in exports[namespace]:
                    continue
                marker = (namespace, member)
                if marker in reported:
                    continue
                reported.add(marker)
                yield Finding(
                    check="web/namespace",
                    severity=Severity.ERROR,
                    message=(
                        f"{rel} 调用了 QW.{namespace}.{member}，但 {sources.get(namespace)} "
                        f"只导出了 {'、'.join(sorted(exports[namespace])) or '（空）'}"
                    ),
                    location=Location(rel, lineno, f"QW.{namespace}.{member}"),
                    hint="补上导出，或修正调用名",
                )


def check_script_loaded(ctx) -> Iterator[Finding]:
    html = ctx.root / JS_HTML
    if not html.is_file():
        return
    text = html.read_text(encoding="utf-8", errors="replace")
    loaded = {Path(src.split("?")[0]).name for src in _SCRIPT_SRC_RE.findall(text)}

    for path in _js_files(ctx):
        if path.name in loaded:
            continue
        yield Finding(
            check="web/script-loaded",
            severity=Severity.WARNING,
            message=f"{_rel(ctx, path)} 没有被 {JS_HTML} 引入，代码不会执行",
            location=Location(_rel(ctx, path), 1),
            hint="在 index.html 里加 <script src=…>，或删除该文件",
        )
