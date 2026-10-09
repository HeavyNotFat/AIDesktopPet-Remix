from __future__ import annotations

from pathlib import Path
from typing import Iterator

from ..core import Finding, Location, Severity

# 文档统一放 docs/；只有这些名字允许留在原地
DOCS_DIR = "docs"
ROOT_ALLOWED = ("AGENTS.md",)
MARKDOWN_SUFFIXES = (".md", ".markdown")

# 这些文件的开头不许是注释
COMMENT_SUFFIXES = (".py", ".js", ".css", ".yml", ".yaml")
COMMENT_PREFIXES = ("#", "//", "/*")
# 唯一放行的点目录：工作流也是仓库代码，其余点目录（.venv/.tmp…）整棵跳过
SCAN_DOT_DIRS = (".github",)
# shebang 与工具指令不算"说明性注释"
DIRECTIVE_PREFIXES = (
    "#!", "# -*-", "# coding", "# encoding", "# noqa", "# type:",
    "# pragma:", "# ci:", "# fmt:", "# ruff:", "# pyright", "# mypy",
)
MAX_HEADER_LINES = 3


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _iter_files(ctx, suffixes) -> Iterator[tuple[Path, str]]:
    """按后缀找文件，被排除的目录整棵跳过。"""
    stack = [ctx.root]
    while stack:
        directory = stack.pop()
        try:
            children = sorted(directory.iterdir())
        except OSError:
            continue
        for child in children:
            rel = child.relative_to(ctx.root).as_posix()
            if rel.split("/", 1)[0] not in SCAN_DOT_DIRS and ctx.settings.is_excluded(rel):
                continue
            if child.is_dir():
                stack.append(child)
            elif child.suffix.lower() in suffixes:
                yield child, rel


def check_header_comment(ctx) -> Iterator[Finding]:
    """文件开头不许写注释（说明块 / 分割线 / 装饰性标题）。"""
    for path, rel in _iter_files(ctx, COMMENT_SUFFIXES):
        for index, line in enumerate(_read(path).splitlines()[:MAX_HEADER_LINES], 1):
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith(DIRECTIVE_PREFIXES):
                break
            if stripped.startswith(COMMENT_PREFIXES):
                yield Finding(
                    check="docs/header-comment",
                    severity=Severity.ERROR,
                    message="文件开头不许写注释（说明块 / 分割线 / 装饰性标题）",
                    location=Location(rel, index, stripped[:60]),
                    hint="删掉它；模块说明写进 docs/，代码说明写成它旁边的一句 `#` 注释",
                )
            break


def check_markdown_location(ctx) -> Iterator[Finding]:
    """项目文档统一放 docs/，各目录只留自己的 README.md。"""
    for path, rel in _iter_files(ctx, MARKDOWN_SUFFIXES):
        if path.name.lower() == "readme.md" or rel in ROOT_ALLOWED:
            continue
        if rel.startswith(f"{DOCS_DIR}/"):
            continue
        yield Finding(
            check="docs/markdown-location",
            severity=Severity.ERROR,
            message=f"{rel} 不在 docs/ 下（项目文档统一放 docs/，各目录只留 README.md）",
            location=Location(rel, 1),
            hint="移到 docs/，并在 docs/README.md 的目录表里登记一行",
        )


__all__ = ["check_header_comment", "check_markdown_location"]
