"""源码索引：扫描 / 解析 / 建符号表 / 解析 import。

所有检查都从这里拿数据，好处是：

* AST 只解析一次（缓存），几十个检查也很快；
* 语法错误的文件不会让整个 CI 崩掉，而是作为一条 ERROR 报出来；
* 相对 import（``from ...base import X``）能解析成真正的模块，
  抽象类继承链才追得下去。
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator, Sequence

from .settings import Settings

PY_EXT = ".py"


@dataclass(frozen=True, slots=True)
class SourceFile:
    path: Path          # 绝对路径
    rel: str            # 仓库相对路径（posix）
    module: str         # 点号模块名；不可导入时为相对路径
    package: str        # 相对 import 的基准包名
    is_package: bool
    text: str
    lines: tuple[str, ...]
    tree: ast.Module

    def line(self, number: int) -> str:
        if 1 <= number <= len(self.lines):
            return self.lines[number - 1]
        return ""


@dataclass(slots=True)
class ClassRecord:
    """类定义索引条目。"""

    name: str
    file: SourceFile
    node: ast.ClassDef
    bases: tuple[str, ...]
    keywords: dict[str, str]
    methods: dict[str, ast.FunctionDef]
    attributes: dict[str, ast.AST]
    decorators: tuple[str, ...]

    @property
    def qualname(self) -> str:
        return f"{self.file.module}.{self.name}"

    @property
    def metaclass(self) -> str | None:
        return self.keywords.get("metaclass")

    @property
    def location(self):
        from .core import Location

        return Location.of(self.node, self.file.rel, self.name)


@dataclass(slots=True)
class ImportRef:
    """一条 import 语句解析后的结果。"""

    module: str | None          # 被导入的模块全限定名（相对 import 已展开）
    name: str | None            # from X import name 里的 name
    local: str                  # 在本模块里绑定的名字
    level: int
    node: ast.AST


class ImportTable:
    """单个模块的 import 别名表。"""

    def __init__(self, refs: Iterable[ImportRef]):
        self.refs = list(refs)
        self.aliases: dict[str, ImportRef] = {}
        for ref in self.refs:
            self.aliases.setdefault(ref.local, ref)

    def resolved(self, name: str) -> str | None:
        """把本模块里的名字解析成全限定名。"""
        ref = self.aliases.get(name)
        if ref is None:
            return None
        if ref.name:
            return f"{ref.module}.{ref.name}" if ref.module else ref.name
        return ref.module


def build_import_table(tree: ast.Module, package: str, is_package: bool) -> ImportTable:
    refs: list[ImportRef] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                refs.append(
                    ImportRef(
                        module=alias.name,
                        name=None,
                        local=(alias.asname or alias.name).split(".")[0],
                        level=0,
                        node=node,
                    )
                )
        elif isinstance(node, ast.ImportFrom):
            base = _resolve_relative(node.level, node.module, package, is_package)
            for alias in node.names:
                if alias.name == "*":
                    continue
                refs.append(
                    ImportRef(
                        module=base,
                        name=alias.name,
                        local=alias.asname or alias.name,
                        level=node.level,
                        node=node,
                    )
                )
    return ImportTable(refs)


def _resolve_relative(level: int, module: str | None, package: str, is_package: bool) -> str | None:
    """把 ``from ..base import X`` 展开成 ``stlibs.themes.base``。

    ``package`` 已经是"本模块所在的包"（``__init__.py`` 就是它自己），
    所以 level=1 直接用 package，level=2 再往上剥一层。
    """
    if level == 0:
        return module

    parts = package.split(".") if package else []
    up = level - 1
    if up:
        parts = parts[: len(parts) - up] if up <= len(parts) else []
    if module:
        parts = [*parts, *module.split(".")]
    return ".".join(part for part in parts if part)


class SourceIndex:
    """整个仓库的 Python 源码索引。"""

    def __init__(self, root: Path, settings: Settings):
        self.root = root
        self.settings = settings
        self.files: tuple[SourceFile, ...] = ()
        self.parse_errors: dict[str, str] = {}
        self.modules: dict[str, SourceFile] = {}
        self._tables: dict[str, ImportTable] = {}
        self._classes: list[ClassRecord] = []
        self._functions: dict[tuple[str, str], ast.AST] = {}
        self._assignments: dict[str, dict[str, ast.AST]] = {}
        self._node_files: dict[int, SourceFile] = {}
        #: 名字 → 索引，避免每个 finding 都线性扫一遍（原来是平方级）
        self._by_rel: dict[str, SourceFile] = {}
        self._classes_by_qualname: dict[str, ClassRecord] = {}
        self._classes_by_module_name: dict[tuple[str, str], ClassRecord] = {}
        self._build()

    # -- 构建 -------------------------------------------------------------
    def _build(self) -> None:
        files: list[SourceFile] = []
        for path in self._iter_paths():
            rel = path.relative_to(self.root).as_posix()
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError) as exc:
                self.parse_errors[rel] = f"读取失败：{exc}"
                continue
            try:
                tree = ast.parse(text, filename=rel)
            except SyntaxError as exc:
                self.parse_errors[rel] = f"语法错误：{exc.msg}（第 {exc.lineno} 行）"
                continue

            module, package, is_package = module_name_for(rel)
            files.append(
                SourceFile(
                    path=path,
                    rel=rel,
                    module=module,
                    package=package,
                    is_package=is_package,
                    text=text,
                    lines=tuple(text.splitlines()),
                    tree=tree,
                )
            )

        self.files = tuple(files)
        for src in self.files:
            self.modules.setdefault(src.module, src)
            self._by_rel.setdefault(src.rel, src)
        self._index_symbols()

    def _iter_paths(self) -> Iterator[Path]:
        """自己走目录：``rglob`` 会连 .venv 一起遍历，太慢。"""
        import os

        for dirpath, dirnames, filenames in os.walk(self.root):
            rel_dir = Path(dirpath).relative_to(self.root).as_posix()
            rel_dir = "" if rel_dir == "." else rel_dir

            dirnames[:] = [
                name
                for name in dirnames
                if not self.settings.is_excluded(f"{rel_dir}/{name}/x.py".lstrip("/"))
            ]
            for name in sorted(filenames):
                if not name.endswith(PY_EXT):
                    continue
                rel = f"{rel_dir}/{name}".lstrip("/")
                if self.settings.is_excluded(rel):
                    continue
                yield Path(dirpath) / name

    def _index_symbols(self) -> None:
        for src in self.files:
            table = build_import_table(src.tree, src.package, src.is_package)
            self._tables[src.module] = table
            self._assignments[src.module] = {}

            for node in ast.walk(src.tree):
                # 节点都是活对象（tree 一直持有），用 id 建反查表是安全的
                self._node_files[id(node)] = src

            for node in src.tree.body:
                if isinstance(node, ast.ClassDef):
                    record = self._class_record(node, src)
                    self._classes.append(record)
                    self._classes_by_qualname.setdefault(record.qualname, record)
                    self._classes_by_module_name.setdefault((src.module, record.name), record)
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    self._functions[(src.module, node.name)] = node
                elif isinstance(node, ast.Assign):
                    for target in node.targets:
                        for name in _target_names(target):
                            self._assignments[src.module][name] = node.value
                elif isinstance(node, ast.AnnAssign):
                    for name in _target_names(node.target):
                        if node.value is not None:
                            self._assignments[src.module][name] = node.value
                elif isinstance(node, (ast.Import, ast.ImportFrom)):
                    for ref in _refs_of_node(node, src):
                        self._assignments[src.module].setdefault(ref.local, node)

    @staticmethod
    def _class_record(node: ast.ClassDef, src: SourceFile) -> ClassRecord:
        methods: dict[str, ast.FunctionDef] = {}
        attributes: dict[str, ast.AST] = {}
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                methods[item.name] = item
            elif isinstance(item, ast.Assign):
                for target in item.targets:
                    for name in _target_names(target):
                        attributes[name] = item.value
            elif isinstance(item, ast.AnnAssign):
                for name in _target_names(item.target):
                    attributes[name] = item
        return ClassRecord(
            name=node.name,
            file=src,
            node=node,
            bases=tuple(_expr_name(base) for base in node.bases),
            keywords={kw.arg: _expr_name(kw.value) for kw in node.keywords if kw.arg},
            methods=methods,
            attributes=attributes,
            decorators=tuple(_expr_name(dec) for dec in node.decorator_list),
        )

    # -- 查询 -------------------------------------------------------------
    def line(self, rel: str, number: int) -> str:
        src = self._by_rel.get(rel)
        return src.line(number) if src is not None else ""

    def source(self, rel: str) -> SourceFile | None:
        return self._by_rel.get(rel)

    def file_of(self, node: ast.AST) -> SourceFile | None:
        """节点 → 所属文件（O(1)）。"""
        return self._node_files.get(id(node))

    def table(self, src: SourceFile) -> ImportTable:
        return self._tables.get(src.module, ImportTable(()))

    def top_level_imports(self, src: SourceFile) -> list[ImportRef]:
        """只看模块顶层的 import（函数内的延迟导入不算，它是破环手段）。"""
        refs: list[ImportRef] = []
        for node in src.tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                refs.extend(_refs_of_node(node, src))
        return refs

    @property
    def classes(self) -> tuple[ClassRecord, ...]:
        return tuple(self._classes)

    def class_by_qualname(self, qualname: str) -> ClassRecord | None:
        return self._classes_by_qualname.get(qualname)

    def class_in_module(self, module: str, name: str) -> ClassRecord | None:
        return self._classes_by_module_name.get((module, name))

    def class_index(self) -> tuple[dict[str, ClassRecord], dict[tuple[str, str], ClassRecord]]:
        """给需要自己遍历类的检查复用同一份索引。"""
        return dict(self._classes_by_qualname), dict(self._classes_by_module_name)

    def resolve_class(self, src: SourceFile, name: str) -> ClassRecord | None:
        """把模块里的一个类名（可能是 import 进来的）解析成索引条目。"""
        local = self.class_in_module(src.module, name)
        if local is not None:
            return local

        table = self.table(src)
        target = table.resolved(name)
        if not target:
            return None

        module, _, attr = target.rpartition(".")
        found = self.class_in_module(module, attr)
        if found is not None:
            return found
        # ``from stlibs.themes import hacker`` 这种拿到的是包，再看包内 __init__
        return self.class_in_module(target, attr) if attr else None

    def module_of(self, src: SourceFile, name: str) -> SourceFile | None:
        """解析模块名（如 ``.llm`` → ``stlibs.mproc.onlinechat.llm``）。"""
        table = self.table(src)
        target = table.resolved(name)
        if target and target in self.modules:
            return self.modules[target]
        if name in self.modules:
            return self.modules[name]
        return None

    def module_members(self, module: str) -> set[str]:
        """模块顶层提供的名字（类/函数/赋值/导入）。"""
        src = self.modules.get(module)
        if src is None:
            return set()
        members: set[str] = set(self._assignments.get(module, {}))
        for node in src.tree.body:
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                members.add(node.name)
        return members

    def assignment(self, module: str, name: str) -> ast.AST | None:
        return self._assignments.get(module, {}).get(name)

    def assignments_by_module(self) -> dict[str, dict[str, ast.AST]]:
        return {module: dict(values) for module, values in self._assignments.items()}

    def function(self, module: str, name: str) -> ast.AST | None:
        return self._functions.get((module, name))

    @property
    def functions(self) -> dict[tuple[str, str], ast.AST]:
        return dict(self._functions)

    # -- 遍历工具 ---------------------------------------------------------
    def ast_of(self, rel: str) -> ast.Module | None:
        src = self.source(rel)
        return src.tree if src else None

    def iter_nodes(self, types, only: Sequence[str] | None = None) -> Iterator[tuple[SourceFile, ast.AST]]:
        for src in self.files:
            if only and src.rel not in only:
                continue
            for node in ast.walk(src.tree):
                if isinstance(node, types):
                    yield src, node


def module_name_for(rel: str) -> tuple[str, str, bool]:
    """``stlibs/themes/__init__.py`` → ``('stlibs.themes', 'stlibs.themes', True)``。"""
    pure = rel[:-3] if rel.endswith(PY_EXT) else rel
    parts = pure.split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]
        package = ".".join(parts)
        return package, package, True
    package = ".".join(parts[:-1])
    return ".".join(parts), package, False


def _target_names(target: ast.AST) -> list[str]:
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, (ast.Tuple, ast.List)):
        names: list[str] = []
        for element in target.elts:
            names.extend(_target_names(element))
        return names
    return []


def _refs_of_node(node: ast.AST, src: SourceFile) -> list[ImportRef]:
    table = build_import_table(ast.Module(body=[node], type_ignores=[]), src.package, src.is_package)
    return table.refs


def _expr_name(node: ast.AST | None) -> str:
    if node is None:
        return ""
    try:
        return ast.unparse(node)
    except Exception:  # noqa: BLE001 - unparse 失败时退化成类名
        return type(node).__name__


def call_name(node: ast.Call) -> str:
    """``foo.bar(x)`` → ``foo.bar``。"""
    return _expr_name(node.func)


def call_qualname(node: ast.Call) -> tuple[str, str]:
    """``obj.method(x)`` → ``('obj', 'method')``；``f(x)`` → ``('', 'f')``。"""
    func = node.func
    if isinstance(func, ast.Attribute):
        return _expr_name(func.value), func.attr
    if isinstance(func, ast.Name):
        return "", func.id
    return "", _expr_name(func)


@dataclass(slots=True)
class BranchStatement:
    """带「分支路径」的语句。

    同一个函数里，``if``/``else`` 两个分支各自出现一次 ``setStyleSheet``
    是正常的；只有**同一分支路径**里重复才算冲突。
    """

    path: tuple[str, ...]
    node: ast.AST


def iter_branch_statements(func: ast.AST) -> Iterator[BranchStatement]:
    """按分支路径展开函数体（只下钻一层控制流，足够覆盖 UI 代码）。"""

    def walk(body: Sequence[ast.stmt], path: tuple[str, ...]) -> Iterator[BranchStatement]:
        for stmt in body:
            yield BranchStatement(path, stmt)
            if isinstance(stmt, ast.If):
                yield from walk(stmt.body, (*path, f"if@{stmt.lineno}"))
                yield from walk(stmt.orelse, (*path, f"else@{stmt.lineno}"))
            elif isinstance(stmt, ast.Try):
                yield from walk(stmt.body, (*path, f"try@{stmt.lineno}"))
                for handler in stmt.handlers:
                    yield from walk(handler.body, (*path, f"except@{handler.lineno}"))
                yield from walk(stmt.orelse, (*path, f"else@{stmt.lineno}"))
                yield from walk(stmt.finalbody, (*path, f"finally@{stmt.lineno}"))
            elif isinstance(stmt, (ast.For, ast.While, ast.AsyncFor)):
                yield from walk(stmt.body, (*path, f"loop@{stmt.lineno}"))
                yield from walk(stmt.orelse, (*path, f"loop-else@{stmt.lineno}"))
            elif isinstance(stmt, (ast.With, ast.AsyncWith)):
                yield from walk(stmt.body, (*path, f"with@{stmt.lineno}"))

    body = getattr(func, "body", [])
    yield from walk(body, ())


def iter_calls(func: ast.AST) -> Iterator[tuple[tuple[str, ...], ast.Call]]:
    """函数内所有调用，附带分支路径。

    复合语句的**头部表达式**（``if cond:`` 的 cond、``for x in it:`` 的 it）
    归属于外层路径，语句体则交给 ``iter_branch_statements`` 单独展开，
    这样同一个调用不会被数两次。嵌套函数体内自成作用域，这里不再下钻。
    """
    for item in iter_branch_statements(func):
        for target in _call_roots(item.node):
            for node in _walk_pruned(target, _SCOPE_BOUNDARIES, skip_root=True):
                if isinstance(node, ast.Call):
                    yield item.path, node


_SCOPE_BOUNDARIES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)


def _call_roots(node: ast.stmt) -> list[ast.AST]:
    """一条语句里需要直接统计调用的表达式根。"""
    if isinstance(node, (ast.If, ast.While)):
        return [node.test]
    if isinstance(node, ast.For | ast.AsyncFor):
        return [node.iter]
    if isinstance(node, ast.With | ast.AsyncWith):
        return [item.context_expr for item in node.items]
    if isinstance(node, (ast.Try, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        # 语句体/函数体自成作用域，由各自的遍历负责，避免重复统计
        return []
    return [node]


def _walk_pruned(node: ast.AST, prune: tuple[type, ...], *, skip_root: bool = False) -> Iterator[ast.AST]:
    """遍历 AST，但不下钻 ``prune`` 里的节点。"""
    stack: list[ast.AST] = list(ast.iter_child_nodes(node)) if skip_root else [node]
    while stack:
        current = stack.pop()
        yield current
        if isinstance(current, prune):
            continue
        stack.extend(ast.iter_child_nodes(current))
