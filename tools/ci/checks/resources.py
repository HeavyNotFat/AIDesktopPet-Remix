"""资源路径与素材完整性。

桌宠的崩法很典型：打包成 exe 后 ``./resources/...`` 少了一层，图标/字体/模型
读不出来，界面上是一堆空白但控制台什么都没有。

* ``resource/missing``      代码里写死的 ``./resources/...`` 路径不存在
* ``resource/web-asset``    index.html / CSS 引用的静态文件不存在
* ``resource/character``    角色目录缺 ``model3.json`` 或版本标记文件
* ``resource/static-model`` resources/static.json 里的模型目录不存在
* ``resource/icon``         resources/icons 里的图标没有被任何代码引用
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Iterator

from ..core import Finding, Location, Severity

RESOURCE_PREFIX = "resources/"
#: 运行时才生成的目录，缺失是正常的
RUNTIME_DIRS = ("resources/rag/chroma_db", "resources/rag/lancedb_db", "resources/rag/vector")
_HREF_RE = re.compile(r'(?:href|src)\s*=\s*["\']([^"\'>]+)["\']')
_CSS_URL_RE = re.compile(r'url\(\s*["\']?([^"\')]+)["\']?\s*\)')


def _exists(ctx, rel: str) -> bool:
    return (ctx.root / rel).exists()


def check_missing(ctx) -> Iterator[Finding]:
    """只查「写死的路径字面量」，动态拼接的交给运行时。"""
    skipped = _non_path_strings(ctx.sources)
    for src, node in ctx.sources.iter_nodes(ast.Constant):
        if not isinstance(node.value, str) or id(node) in skipped:
            continue
        text = node.value.strip()
        if not text.startswith(("./resources/", "resources/", "../resources/")):
            continue
        rel = text[2:] if text.startswith("./") else text
        rel = rel.replace("\\", "/").lstrip("/")
        if not rel.startswith(RESOURCE_PREFIX):
            continue
        if any(rel.startswith(prefix) for prefix in RUNTIME_DIRS):
            continue
        if _exists(ctx, rel):
            continue
        yield Finding(
            check="resource/missing",
            severity=Severity.ERROR,
            message=f"代码引用了 {text!r}，但仓库里没有这个文件/目录",
            location=Location.of(node, src.rel),
            hint="检查路径拼写；打包时确认该资源被一起收集",
        )


def _non_path_strings(sources) -> set[int]:
    """不该当路径看的字符串：

    * f-string 的片段（``f"resources/{x}"`` 不是完整路径）；
    * 文档字符串（说明文字里出现 ``resources/...`` 很正常，而且不会被执行）。
    """
    skipped: set[int] = set()
    for _, node in sources.iter_nodes(ast.JoinedStr):
        for value in node.values:
            if isinstance(value, ast.Constant):
                skipped.add(id(value))
    for _, node in sources.iter_nodes((ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
        body = getattr(node, "body", None)
        if not body or not isinstance(body[0], ast.Expr):
            continue
        value = body[0].value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            skipped.add(id(value))
    return skipped


def check_web_asset(ctx) -> Iterator[Finding]:
    web_root = ctx.root / "resources/web"
    if not web_root.is_dir():
        return
    for html in sorted(web_root.rglob("*.html")):
        rel = html.relative_to(ctx.root).as_posix()
        text = html.read_text(encoding="utf-8", errors="replace")
        for match in _HREF_RE.finditer(text):
            target = match.group(1)
            if target.startswith(("http://", "https://", "#", "data:", "mailto:")):
                continue
            resolved = (html.parent / target.split("?")[0]).resolve()
            if resolved.exists():
                continue
            yield Finding(
                check="resource/web-asset",
                severity=Severity.ERROR,
                message=f"{rel} 引用了 {target!r}，但文件不存在",
                location=Location(rel, text[: match.start()].count("\n") + 1),
                hint="补齐静态文件或修正引用路径",
            )

    for css in sorted(web_root.rglob("*.css")):
        rel = css.relative_to(ctx.root).as_posix()
        text = css.read_text(encoding="utf-8", errors="replace")
        for match in _CSS_URL_RE.finditer(text):
            target = match.group(1).strip()
            if target.startswith(("http://", "https://", "data:")):
                continue
            resolved = (css.parent / target.split("?")[0]).resolve()
            if resolved.exists():
                continue
            yield Finding(
                check="resource/web-asset",
                severity=Severity.WARNING,
                message=f"{rel} 里 url({target}) 指向的文件不存在",
                location=Location(rel, text[: match.start()].count("\n") + 1),
                hint="补齐资源或删掉这条规则",
            )


def check_character(ctx) -> Iterator[Finding]:
    model_root = ctx.root / "resources/character/model"
    if model_root.is_dir():
        for directory in sorted(path for path in model_root.iterdir() if path.is_dir()):
            rel = directory.relative_to(ctx.root).as_posix()
            models = list(directory.glob("*.model3.json"))
            if not models:
                yield Finding(
                    check="resource/character",
                    severity=Severity.ERROR,
                    message=f"{rel} 里没有 *.model3.json，Live2D 无法加载",
                    location=Location(rel, 1),
                    hint="放入模型描述文件，或从 resources/character/model 里移除该目录",
                )
            if not (directory / "3").exists() and not (directory / "2").exists():
                yield Finding(
                    check="resource/character",
                    severity=Severity.WARNING,
                    message=f"{rel} 缺少版本标记文件（2 或 3），设置页会把它当成静态模型",
                    location=Location(rel, 1),
                    hint="Live2D Cubism 3/4 模型目录里应有名为 3 的标记文件",
                )
            # Cubism 2 的模型文件是 .moc，Cubism 3+ 才是 .moc3
            if not list(directory.glob("*.moc3")) and not list(directory.glob("*.moc")):
                yield Finding(
                    check="resource/character",
                    severity=Severity.ERROR,
                    message=f"{rel} 有 model3.json 但没有 *.moc3 / *.moc",
                    location=Location(models[0].relative_to(ctx.root).as_posix(), 1),
                    hint="补上模型二进制文件",
                )


def check_static_models(ctx) -> Iterator[Finding]:
    rel = "resources/static.json"
    path = ctx.root / rel
    if not path.is_file():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        yield Finding(
            check="resource/static-model",
            severity=Severity.ERROR,
            message=f"{rel} 不是合法 JSON：{exc}",
            location=Location(rel, exc.lineno or 1),
        )
        return

    for name, config in sorted(data.items()):
        directory = ctx.root / "resources/character/static" / name
        if not directory.is_dir():
            yield Finding(
                check="resource/static-model",
                severity=Severity.ERROR,
                message=f"{rel} 声明了静态模型 {name!r}，但 resources/character/static/{name} 不存在",
                location=Location(rel, 1, name),
                hint="补目录或删掉该条目",
            )
            continue
        for action, spec in (config or {}).items():
            if not isinstance(spec, dict):
                continue
            frames = [str(prefix) for prefix in spec.get("frames", [])]
            if not frames:
                continue
            available = {item.name for item in directory.rglob("*.png")}
            for prefix in frames:
                if any(name.startswith(prefix) for name in available):
                    continue
                yield Finding(
                    check="resource/static-model",
                    severity=Severity.ERROR,
                    message=f"{name}.{action} 的帧前缀 {prefix!r} 在 {directory.name}/{action} 下没有匹配的图片",
                    location=Location(rel, 1, f"{name}.{action}"),
                    hint="检查帧前缀与图片命名",
                )


def check_json_resources(ctx) -> Iterator[Finding]:
    """resources 目录下的 JSON 必须都能解析（打包后崩在这里最难查）。"""
    root_dir = ctx.root / "resources"
    if not root_dir.is_dir():
        return
    for path in sorted(root_dir.rglob("*.json")):
        rel = path.relative_to(ctx.root).as_posix()
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            yield Finding(
                check="resource/json-valid",
                severity=Severity.ERROR,
                message=f"{rel} 不是合法 JSON：{exc.msg}",
                location=Location(rel, exc.lineno or 1),
                hint="修掉 JSON 语法（多余逗号、单引号、BOM 都是常见原因）",
            )
        except UnicodeDecodeError:
            yield Finding(
                check="resource/json-valid",
                severity=Severity.ERROR,
                message=f"{rel} 不是 UTF-8 编码的 JSON",
                location=Location(rel, 1),
                hint="转成 UTF-8 保存",
            )


def check_icon_usage(ctx) -> Iterator[Finding]:
    """icons/ 下没有被任何代码引用的素材（聚合报告，避免刷屏）。"""
    icon_dir = ctx.root / "resources/icons"
    if not icon_dir.is_dir():
        return
    referenced = set()
    for _, node in ctx.sources.iter_nodes(ast.Constant):
        if isinstance(node.value, str) and "resources/icons/" in node.value:
            referenced.add(Path(node.value).name)

    unused = sorted(
        icon.name for icon in icon_dir.iterdir() if icon.is_file() and icon.name not in referenced
    )
    if not unused:
        return
    yield Finding(
        check="resource/icon",
        severity=Severity.INFO,
        message=f"resources/icons 下有 {len(unused)} 个素材没有被任何代码引用：{'、'.join(unused)}",
        location=Location("resources/icons", 1),
        hint="删掉无用素材，或把它们接进界面（减少打包体积）",
    )
