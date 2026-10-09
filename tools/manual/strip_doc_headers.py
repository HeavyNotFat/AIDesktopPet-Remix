"""安全清理注释：只删「分割线注释」和「文件头部说明」，不碰代码。

用法::

    python tools/manual/strip_doc_headers.py            # 预览
    python tools/manual/strip_doc_headers.py --apply    # 写盘
    python tools/manual/strip_doc_headers.py --apply --include-class-docstrings
"""

from __future__ import annotations

import argparse
import ast
import pathlib
import re
import sys

SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules", ".idea", "build", "dist",
             ".ci-tmp", ".tmp", ".pytest_cache", ".ruff_cache", ".mypy_cache",
             ".PluginDevOld"}  # 旧 PyQt5 工程，不属于本仓库产物

# 自己这个脚本的 docstring 就是用法说明，别清理它
SKIP_FILES = {pathlib.Path(__file__).resolve()}

# 分割线：整行都是 # 加一串 - = _（后面可以跟标题）
DIVIDER = re.compile(r"^\s*(#|//)\s*[-=_*]{3,}\s*\S*\s*$")
DIVIDER_BARE = re.compile(r"^\s*(#|//)\s*[-=_*]{3,}\s*$")


def python_edits(source: str, include_class_docstrings: bool) -> list:
    """返回 [(起始行, 结束行)]（1 基，含两端）。"""
    spans = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return spans

    holders = [ast.Module]
    if include_class_docstrings:
        holders.append(ast.ClassDef)

    for node in ast.walk(tree):
        if not isinstance(node, tuple(holders)):
            continue
        body = getattr(node, "body", [])
        if not body:
            continue
        first = body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) \
                and isinstance(first.value.value, str):
            spans.append((first.lineno, first.end_lineno or first.lineno))

    for index, line in enumerate(source.splitlines()):
        if DIVIDER.match(line) or DIVIDER_BARE.match(line):
            spans.append((index + 1, index + 1))

    return spans


def text_edits(source: str) -> list:
    spans = []
    for index, line in enumerate(source.splitlines()):
        if DIVIDER.match(line) or DIVIDER_BARE.match(line):
            spans.append((index + 1, index + 1))
    return spans


def strip(path: pathlib.Path, include_class_docstrings: bool) -> int:
    source = path.read_text(encoding="utf-8")
    spans = python_edits(source, include_class_docstrings) if path.suffix == ".py" else text_edits(source)
    if not spans:
        return 0

    drop = set()
    for start, end in spans:
        drop.update(range(start, end + 1))

    kept = [line for index, line in enumerate(source.splitlines()) if (index + 1) not in drop]
    result = "\n".join(kept)
    if source.endswith("\n"):
        result += "\n"

    if path.suffix == ".py":
        ast.parse(result, str(path))  # 删完必须还是合法 Python
    path.write_text(result, encoding="utf-8")
    return len(drop)


def main():
    parser = argparse.ArgumentParser(description="清掉分割线注释与文件头部说明")
    parser.add_argument("--apply", action="store_true", help="真的写盘（默认只预览）")
    parser.add_argument("--include-class-docstrings", action="store_true", help="连类 docstring 一起删")
    parser.add_argument("--suffix", default=".py,.js,.css", help="处理哪些后缀（逗号分隔）")
    parser.add_argument("--root", default=".", help="从哪个目录开始")
    args = parser.parse_args()

    suffixes = tuple(item.strip() for item in args.suffix.split(",") if item.strip())
    root = pathlib.Path(args.root).resolve()
    total = 0
    touched = 0

    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in suffixes:
            continue
        if set(path.parts) & SKIP_DIRS or path.resolve() in SKIP_FILES:
            continue

        source = path.read_text(encoding="utf-8")
        spans = python_edits(source, args.include_class_docstrings) if path.suffix == ".py" else text_edits(source)
        if not spans:
            continue

        count = sum(end - start + 1 for start, end in spans)
        total += count
        touched += 1
        print(f"   -{count:3} 行  {path.relative_to(root).as_posix()}")
        if args.apply:
            strip(path, args.include_class_docstrings)

    print(f"\n{'已清理' if args.apply else '待清理'} {total} 行 / {touched} 个文件")
    return 0


if __name__ == "__main__":
    sys.exit(main())
