"""导入图与依赖健康度。

* ``import/cycle``        项目内模块在**模块级**互相 import 成环
* ``import/requirements`` 用到的第三方库没写进 requirements.txt
* ``import/unused-req``   requirements.txt 里躺着的依赖没人用

函数体内的延迟导入（``def x(): from . import y``）是合法的破环手段，
所以环检测只看顶层 import。
"""

from __future__ import annotations

import ast
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Iterator

from ..core import Finding, Location, Severity

REQUIREMENTS = "requirements.txt"

#: import 名 → 发行包名（requirements.txt 里写的是后者）
DISTRIBUTION_ALIASES: dict[str, str] = {
    "PIL": "Pillow",
    "OpenGL": "PyOpenGL",
    "live2d": "live2d-py",
    "yaml": "PyYAML",
    "win32com": "pypiwin32",
    "win32api": "pypiwin32",
    "pythoncom": "pypiwin32",
    "cv2": "opencv-python",
    "sklearn": "scikit-learn",
    "dotenv": "python-dotenv",
    "qfluentwidgets": "PySide6-Fluent-Widgets",
}

#: 只在本机开发脚本/测试里出现的库，不算运行时依赖
DEV_ONLY_FILES = ("tests/", "tools/")


def _known_modules() -> set[str]:
    return set(sys.stdlib_module_names)


def check_import_cycle(ctx) -> Iterator[Finding]:
    graph: dict[str, set[str]] = defaultdict(set)
    for src in ctx.sources.files:
        for ref in ctx.sources.top_level_imports(src):
            target = ref.module
            if not target:
                continue
            if ref.name:
                # from X import Y：Y 也可能是子模块
                candidate = f"{target}.{ref.name}"
                if candidate in ctx.sources.modules:
                    target = candidate
            if target in ctx.sources.modules and target != src.module:
                graph[src.module].add(target)

    for cycle in sorted(_find_cycles(graph), key=len):
        src = ctx.sources.modules.get(cycle[0])
        if src is None:
            continue
        yield Finding(
            check="import/cycle",
            severity=Severity.WARNING,
            message=f"检测到模块级循环导入：{' → '.join(cycle)}",
            location=Location(src.rel, 1, cycle[0]),
            hint="把公共部分下沉到第三个模块，或把其中一处改成函数内延迟导入",
        )


def _find_cycles(graph: dict[str, set[str]]) -> list[list[str]]:
    """Tarjan 强连通分量：大小 >1 的即为环。"""
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    result: list[list[str]] = []
    counter = [0]

    def strongconnect(node: str) -> None:
        index[node] = low[node] = counter[0]
        counter[0] += 1
        stack.append(node)
        on_stack.add(node)

        for neighbour in sorted(graph.get(node, ())):
            if neighbour not in index:
                strongconnect(neighbour)
                low[node] = min(low[node], low[neighbour])
            elif neighbour in on_stack:
                low[node] = min(low[node], index[neighbour])

        if low[node] == index[node]:
            component: list[str] = []
            while True:
                current = stack.pop()
                on_stack.discard(current)
                component.append(current)
                if current == node:
                    break
            if len(component) > 1:
                result.append(component)

    sys.setrecursionlimit(max(sys.getrecursionlimit(), 10000))
    for node in sorted(graph):
        if node not in index:
            strongconnect(node)
    return result


def check_requirements(ctx) -> Iterator[Finding]:
    declared = _declared_requirements(ctx.root / REQUIREMENTS)
    if not declared:
        return

    for name, location in sorted(_imported_third_party(ctx).items()):
        distribution = DISTRIBUTION_ALIASES.get(name, name)
        if _normalize(distribution) in declared:
            continue
        yield Finding(
            check="import/requirements",
            severity=Severity.WARNING,
            message=f"{location.symbol or name} 用到了 {name}，但 {REQUIREMENTS} 里没有声明",
            location=location,
            hint=f"把 {distribution} 加进 {REQUIREMENTS}，否则干净环境跑不起来",
        )


def check_unused_requirements(ctx) -> Iterator[Finding]:
    declared = _declared_requirements(ctx.root / REQUIREMENTS)
    if not declared:
        return
    imported = _imported_third_party(ctx)
    used = {_normalize(DISTRIBUTION_ALIASES.get(name, name)) for name in imported}

    for requirement, lineno in sorted(declared.items(), key=lambda item: item[1]):
        if requirement in used:
            continue
        yield Finding(
            check="import/unused-req",
            severity=Severity.INFO,
            message=f"{REQUIREMENTS} 声明了 {requirement}，但代码里没有 import",
            location=Location(REQUIREMENTS, lineno, requirement),
            hint="确认是否仍需要（打包时会白占体积）",
        )


def _imported_third_party(ctx) -> dict[str, Location]:
    """项目代码里 import 的第三方顶层模块。"""
    imported: dict[str, Location] = {}
    project_top = _project_top_level(ctx)
    stdlib = _known_modules()
    for src in ctx.sources.files:
        if src.rel.startswith(DEV_ONLY_FILES):
            continue
        for node in ast.walk(src.tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module.split(".")[0]]
            for name in names:
                if name in stdlib or name in project_top:
                    continue
                if _is_local_sibling(ctx.sources, src, name):
                    continue
                imported.setdefault(name, Location.of(node, src.rel))
    return imported


def _project_top_level(ctx) -> set[str]:
    """项目自己的顶层包/模块名（从索引推导，避免硬编码漏项）。"""
    names = {module.split(".")[0] for module in ctx.sources.modules}
    names.update({"core", "main"})
    return names


def _is_local_sibling(sources, src, name: str) -> bool:
    """``name`` 是不是导入方**同目录**下的模块/包。

    覆盖"脚本式运行"：``python mcp_servers/live2d_motion.py`` 时 sys.path[0]
    是 ``mcp_servers/``，所以 ``from sdk import client`` 指的是
    ``mcp_servers/sdk``，不是第三方 sdk。
    """
    directory = src.rel.rpartition("/")[0]
    candidates = [f"{name}/__init__.py", f"{name}.py"]
    if directory:
        candidates = [f"{directory}/{item}" for item in candidates]
    return any(sources.source(candidate) is not None for candidate in candidates)


def _declared_requirements(path: Path) -> dict[str, int]:
    if not path.is_file():
        return {}
    declared: dict[str, int] = {}
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name = re.split(r"[<>=!\[;]", line, maxsplit=1)[0].strip()
        if name:
            declared[_normalize(name)] = lineno
    return declared


def _normalize(name: str) -> str:
    return name.lower().replace("_", "-")
