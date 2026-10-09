from __future__ import annotations

import ast
import re
from typing import Iterator

from ..core import Finding, Location, Severity

# 常见 Qt / 本项目的 API 名，只收界面专用名，通用名参与比较会误报。
KNOWN_API_NAMES: frozenset[str] = frozenset(
    """
    bottom top left right width height size rect geometry move resize show hide close update
    setGeometry setFixedSize setFixedWidth setFixedHeight setMinimumSize setMaximumSize
    setWindowTitle setObjectName setStyleSheet setLayout setParent setVisible setEnabled
    setChecked isChecked setValue value currentText currentIndex setCurrentIndex setCurrentText
    setText text setFont font setPixmap pixmap setPlaceholderText setWindowFlags setAttribute
    addWidget insertWidget removeWidget addItem addItems addTab removeTab setWidget
    addAction addSeparator addNavigation removeNavigation create_category setTitle
    userInputSignal add_user_msg add_assistant_msg updateBubbleWidth scroll_to_bottom
    """.split()
)

_TODO_RE = re.compile(r"#\s*(TODO|FIXME|XXX|HACK)\b", re.IGNORECASE)


def check_parse_error(ctx) -> Iterator[Finding]:
    for rel, message in sorted(ctx.sources.parse_errors.items()):
        yield Finding(
            check="hygiene/parse-error",
            severity=Severity.ERROR,
            message=message,
            location=Location(rel, 1),
            hint="修掉语法错误，否则该文件的所有检查都会被跳过",
        )


MODULE_DOCSTRING_EXEMPT = ("tools/manual/strip_doc_headers.py",)


def check_module_docstring(ctx) -> Iterator[Finding]:
    """拦「文件头部写了模块 docstring」：模块 body 第一条语句是字符串常量就算。"""
    for src in ctx.sources.files:
        if src.rel in MODULE_DOCSTRING_EXEMPT:
            continue
        body = src.tree.body
        if not body:
            continue
        first = body[0]
        if not (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)):
            continue
        yield Finding(
            check="hygiene/module-docstring",
            severity=Severity.ERROR,
            message="文件头部不允许模块 docstring（`\"\"\"...\"\"\"`）",
            location=Location(src.rel, first.lineno),
            hint="删掉它；模块级的说明写进 `#` 注释或 docs/STRUCTURE.md，类/函数说明写进各自的 docstring",
        )


def check_bare_except(ctx) -> Iterator[Finding]:
    for src, node in ctx.sources.iter_nodes(ast.ExceptHandler):
        if node.type is not None:
            continue
        yield Finding(
            check="hygiene/bare-except",
            severity=Severity.WARNING,
            message="裸 except 会连 KeyboardInterrupt/SystemExit 一起吞掉，排障时看不到真实原因",
            location=Location.of(node, src.rel),
            hint="改成 except Exception: 并在日志里留下异常信息",
        )


def check_attribute_typo(ctx) -> Iterator[Finding]:
    defined = _defined_names(ctx)
    allowed = ctx.settings.allow_tokens("hygiene/attr-typo")

    for src, node in ctx.sources.iter_nodes(ast.Call):
        if not isinstance(node.func, ast.Attribute):
            continue
        name = node.func.attr
        if name in defined or name in allowed or name in KNOWN_API_NAMES or len(name) < 5:
            continue
        # 只看首字母小写的名字，大写开头多是外部绑定库的命名。
        if not name[0].islower():
            continue
        for candidate in KNOWN_API_NAMES:
            if abs(len(candidate) - len(name)) > 1:
                continue
            if not _close(name, candidate):
                continue
            yield Finding(
                check="hygiene/attr-typo",
                severity=Severity.WARNING,
                message=f"调用了 {name}()，它和 {candidate}() 只差一个字符，且全项目没有别处定义 {name}",
                location=Location.of(node, src.rel, name),
                hint=f"确认是不是想写 {candidate}()；确实是自定义方法就加 allow 白名单",
            )
            break


def _defined_names(ctx) -> set[str]:
    defined: set[str] = set()
    for record in ctx.sources.classes:
        defined.add(record.name)
        defined |= set(record.methods)
        defined |= set(record.attributes)
    for (_, name) in ctx.sources.functions:
        defined.add(name)
    for src in ctx.sources.files:
        for node in ast.walk(src.tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                defined.add(node.name)
            elif isinstance(node, ast.arg):
                defined.add(node.arg)
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                defined.add(node.id)
            elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Store):
                defined.add(node.attr)
            elif isinstance(node, ast.keyword) and node.arg:
                defined.add(node.arg)
        for name in ctx.sources.assignments_by_module().get(src.module, {}):
            defined.add(name)
    return defined


def _close(left: str, right: str) -> bool:
    """编辑距离恰好为 1（只考虑替换/插入/删除）。"""
    if left == right:
        return False
    if abs(len(left) - len(right)) > 1:
        return False
    if len(left) == len(right):
        return sum(a != b for a, b in zip(left, right)) == 1
    short, long = (left, right) if len(left) < len(right) else (right, left)
    for index in range(len(long)):
        if long[:index] + long[index + 1 :] == short:
            return True
    return False


def check_todo(ctx) -> Iterator[Finding]:
    total = 0
    samples: list[Location] = []
    for src in ctx.sources.files:
        for lineno, line in enumerate(src.lines, 1):
            if _TODO_RE.search(line):
                total += 1
                if len(samples) < 5:
                    samples.append(Location(src.rel, lineno, line.strip()[:60]))
    if not total:
        return
    yield Finding(
        check="hygiene/todo",
        severity=Severity.INFO,
        message=f"代码里还有 {total} 处 TODO/FIXME（示例：{'; '.join(str(s) for s in samples)}）",
        location=samples[0],
        hint="排期处理，或在 issue 里登记",
    )
