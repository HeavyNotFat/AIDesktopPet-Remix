"""抽象类 / 抽象方法检测。

覆盖的坑（都在这个仓库真实出现过或差点出现）：

* ``abs/contract``        —— 抽象方法没实现，实例化时直接 ``TypeError``；
* ``abs/instantiate``     —— 明明还有抽象方法却去构造（动态取主题映射时最容易踩）；
* ``abs/decorator-order`` —— ``@abstractmethod`` 与 ``@property`` 顺序写反，装饰器失效；
* ``abs/not-enforced``    —— 类里写了 ``@abstractmethod`` 但没有 ABCMeta，约束形同虚设；
* ``abs/metaclass``       —— Qt 类 + 抽象基类没写 ``metaclass=CombinedMeta``，元类冲突；
* ``abs/signature``       —— 子类签名和抽象声明不一致（按基类写法调用就炸）。
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Iterator

from ..core import Finding, Location, Severity
from ..contract import MAPPING_ABC
from ..source import ClassRecord, SourceIndex

ABSTRACT_DECORATORS = frozenset(
    {"abstractmethod", "abstractproperty", "abstractstaticmethod", "abstractclassmethod"}
)
ABC_METACLASSES = frozenset({"ABCMeta", "abc.ABCMeta"})
ABC_BASES = frozenset({"ABC", "abc.ABC"})


@dataclass(slots=True)
class ClassInfo:
    record: ClassRecord
    abstract: dict[str, ast.FunctionDef]           # 仍未实现的抽象成员
    is_abc_derived: bool
    is_qt: bool
    has_abc_metaclass: bool


class Hierarchy:
    """项目内的类继承关系（只解析能解析得动的边）。"""

    def __init__(self, sources: SourceIndex):
        self.sources = sources
        self._bases: dict[str, list[ClassRecord]] = {}
        self._abstract: dict[str, dict[str, ast.FunctionDef]] = {}

    # -- 基类解析 ---------------------------------------------------------
    def base_of(self, record: ClassRecord, base_name: str) -> ClassRecord | None:
        sources = self.sources
        if not base_name:
            return None
        if "." in base_name:
            head, _, tail = base_name.rpartition(".")
            module = sources.module_of(record.file, head)
            if module is not None:
                found = sources.class_in_module(module.module, tail)
                if found is not None:
                    return found
            if sources.class_in_module(record.file.module, head) is not None:
                return sources.class_in_module(record.file.module, tail)
            return None
        return sources.resolve_class(record.file, base_name)

    def bases(self, record: ClassRecord) -> list[ClassRecord]:
        cached = self._bases.get(record.qualname)
        if cached is not None:
            return cached
        resolved: list[ClassRecord] = []
        for name in record.bases:
            base = self.base_of(record, name)
            if base is not None and base.qualname != record.qualname:
                resolved.append(base)
        self._bases[record.qualname] = resolved
        return resolved

    def ancestors(self, record: ClassRecord) -> list[ClassRecord]:
        seen: dict[str, ClassRecord] = {}
        stack = list(self.bases(record))
        while stack:
            current = stack.pop()
            if current.qualname in seen:
                continue
            seen[current.qualname] = current
            stack.extend(self.bases(current))
        return list(seen.values())

    # -- 抽象成员 ---------------------------------------------------------
    def abstract_members(self, record: ClassRecord) -> dict[str, ast.FunctionDef]:
        """该类「还没有实现」的抽象成员（含从祖先继承来的）。"""
        cached = self._abstract.get(record.qualname)
        if cached is not None:
            return dict(cached)

        members: dict[str, ast.FunctionDef] = {}
        for base in self.bases(record):
            members.update(self.abstract_members(base))
            for name, node in base.methods.items():
                if is_abstract(node):
                    members[name] = node
                elif name in members:
                    # 基类给了具体实现，约束解除
                    members.pop(name, None)

        for name, node in record.methods.items():
            if is_abstract(node):
                members[name] = node
            else:
                members.pop(name, None)
        for name in record.attributes:
            # 类属性也算实现：主题里 Signal / QIcon 都是这么挂的
            members.pop(name, None)

        self._abstract[record.qualname] = members
        return dict(members)

    # -- 分类 -------------------------------------------------------------
    def has_abc_metaclass(self, record: ClassRecord) -> bool:
        """本类或任一祖先是否用上了 ABCMeta 系元类。

        元类会被继承：``class C(A)`` 里 A 用了 ``metaclass=ABCMeta``，
        C 里再写 ``@abstractmethod`` 也是有效的，不能只看直接基类。
        """
        meta = record.metaclass
        if meta:
            short = meta.rpartition(".")[2]
            if meta in ABC_METACLASSES or short.endswith("ABCMeta"):
                return True
            # 项目内自定义的合并元类（CombinedMeta / _CombinedMeta）：
            # 看它自己有没有继承 ABCMeta
            meta_record = self.sources.resolve_class(record.file, short)
            if meta_record is not None:
                return any(
                    base.rpartition(".")[2].endswith("ABCMeta") for base in meta_record.bases
                )
            return False
        if any(base in ABC_BASES or base.rpartition(".")[2] in ABC_BASES for base in record.bases):
            return True
        return any(self.has_abc_metaclass(base) for base in self.bases(record))

    def is_qt_like(self, record: ClassRecord, _seen: set[str] | None = None) -> bool:
        """基类里出现 ``Qxxx``，或者项目内的基类本身是 Qt 类。"""
        seen = _seen if _seen is not None else set()
        if record.qualname in seen:
            return False
        seen.add(record.qualname)

        table = self.sources.table(record.file)
        for base in record.bases:
            head = base.rpartition(".")[2] or base
            if head.startswith("Q") and head[1:2].isupper():
                return True
            resolved = table.resolved(head) or ""
            if resolved.rpartition(".")[2].startswith("Q"):
                return True
        return any(self.is_qt_like(base, seen) for base in self.bases(record))

    def metaclass_kind(self, record: ClassRecord, _seen: set[str] | None = None) -> str:
        """这个类实际用的元类属于哪一类：``abc`` / ``qt`` / ``plain``。

        元类是会被继承的：``class Child(QtABCBase)`` 不需要再写一次
        ``metaclass=``，所以不能只看显式声明，否则会误报元类冲突。
        """
        seen = _seen if _seen is not None else set()
        if record.qualname in seen:
            return "plain"
        seen.add(record.qualname)

        if record.metaclass:
            return "abc" if self.has_abc_metaclass(record) else "plain"

        kinds = {self.metaclass_kind(base, seen) for base in self.bases(record)}
        if "abc" in kinds:
            return "abc"
        # 直接继承外部 Qt 类：Qt 的元类基本都不是 ABCMeta 系
        for base in record.bases:
            head = base.rpartition(".")[2] or base
            if head.startswith("Q") and head[1:2].isupper():
                return "qt"
        if "qt" in kinds:
            return "qt"
        return "plain"

    def is_abc_derived(self, record: ClassRecord) -> bool:
        if self.has_abc_metaclass(record):
            return True
        return any(is_abstract_node(base) for base in self.ancestors(record))


def is_abstract(node: ast.AST) -> bool:
    return any(decorator_name(dec) in ABSTRACT_DECORATORS for dec in getattr(node, "decorator_list", []))


def is_abstract_node(record: ClassRecord) -> bool:
    return any(is_abstract(method) for method in record.methods.values())


def decorator_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Call):
        return decorator_name(node.func)
    return ""


def is_property(node: ast.AST) -> bool:
    return any(
        decorator_name(dec) in {"property", "cached_property"} for dec in getattr(node, "decorator_list", [])
    )


def is_static(node: ast.AST) -> bool:
    decorators = {decorator_name(dec) for dec in getattr(node, "decorator_list", [])}
    return bool(decorators & {"staticmethod", "abstractstaticmethod"})


def positional_params(node: ast.FunctionDef, *, strip_self: bool = True) -> list[ast.arg]:
    args = [*node.args.posonlyargs, *node.args.args]
    if strip_self and args and args[0].arg in {"self", "cls"}:
        args = args[1:]
    return args


def required_params(node: ast.FunctionDef, *, strip_self: bool = True) -> list[ast.arg]:
    """没有默认值的位置参数。"""
    args = positional_params(node, strip_self=strip_self)
    defaults = len(node.args.defaults)
    if defaults:
        args = args[: len(args) - defaults] if defaults <= len(args) else []
    return args


def _theme_mapped_classes(sources: SourceIndex) -> set[str]:
    """被绑到主题映射名上的类——应用一定会构造它们。

    ``Window = HackerWindow`` 和 ``IconList = IconList()`` 两种形态都要认。
    """
    mapped: set[str] = set()
    for src in sources.files:
        if not src.rel.startswith("stlibs/themes/") or not src.rel.endswith("__init__.py"):
            continue
        for node in src.tree.body:
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if not (isinstance(target, ast.Name) and target.id in MAPPING_ABC):
                    continue
                class_name: str | None = None
                if isinstance(node.value, ast.Name):
                    class_name = node.value.id
                elif isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name):
                    class_name = node.value.func.id
                if class_name is None:
                    continue
                record = sources.class_in_module(src.module, class_name)
                if record is not None:
                    mapped.add(record.qualname)
    return mapped


def _instantiated_names(sources: SourceIndex) -> set[str]:
    names: set[str] = set()
    for _, node in sources.iter_nodes(ast.Call):
        func = node.func
        if isinstance(func, ast.Name):
            names.add(func.id)
        elif isinstance(func, ast.Attribute):
            names.add(func.attr)
    return names | _theme_mapped_classes(sources)


def collect(sources: SourceIndex) -> tuple[Hierarchy, list[ClassInfo]]:
    hierarchy = Hierarchy(sources)
    infos = [
        ClassInfo(
            record=record,
            abstract=hierarchy.abstract_members(record),
            is_abc_derived=hierarchy.is_abc_derived(record),
            is_qt=hierarchy.is_qt_like(record),
            has_abc_metaclass=hierarchy.has_abc_metaclass(record),
        )
        for record in sources.classes
    ]
    return hierarchy, infos


def check_contract(ctx) -> Iterator[Finding]:
    """``abs/contract``：抽象基类的实现类必须补齐所有抽象成员。"""
    _, infos = collect(ctx.sources)
    instantiated = _instantiated_names(ctx.sources)

    for info in infos:
        record = info.record
        if not info.abstract or not info.is_abc_derived:
            continue
        if is_abstract_node(record):
            # 自己就是抽象基类（还在声明抽象方法），允许留空
            continue

        missing = sorted(info.abstract)
        used = record.name in instantiated
        hint = f"补上 {', '.join(missing)}，或继承一个已经实现它们的基类"
        if used:
            hint = f"该基类会被构造，运行时会 TypeError；{hint}"
        yield Finding(
            check="abs/contract",
            severity=Severity.ERROR if used else Severity.WARNING,
            message=f"{record.name} 继承自抽象基类，但没有实现抽象成员：{', '.join(missing)}",
            location=record.location,
            hint=hint,
        )


def check_instantiate(ctx) -> Iterator[Finding]:
    """``abs/instantiate``：构造一个仍有未实现抽象成员的类。

    这里**不**跳过"自己还声明着抽象方法的类"：既然在构造它，
    那些没实现的成员就是运行期地雷（PySide6 下运行期还不会拦你）。
    """
    _, infos = collect(ctx.sources)
    by_qualname = {info.record.qualname: info for info in infos}
    by_name: dict[str, ClassInfo] = {}
    for info in infos:
        by_name.setdefault(info.record.name, info)

    for src, node in ctx.sources.iter_nodes(ast.Call):
        func = node.func
        if isinstance(func, ast.Attribute):
            info = by_qualname.get(f"{src.module}.{func.attr}") or by_name.get(func.attr)
        elif isinstance(func, ast.Name):
            info = by_name.get(func.id)
        else:
            info = None
        if info is None or not info.abstract:
            continue
        yield Finding(
            check="abs/instantiate",
            severity=Severity.ERROR,
            message=(
                f"构造 {info.record.name} 会失败：抽象成员未实现"
                f"（{', '.join(sorted(info.abstract))}）"
            ),
            location=Location.of(node, src.rel, info.record.name),
            hint="先实现抽象成员，或改用一个具体子类",
        )


def check_decorator_order(ctx) -> Iterator[Finding]:
    """``abs/decorator-order``：``@abstractmethod`` 必须是最内层装饰器。"""
    for src, node in ctx.sources.iter_nodes(ast.FunctionDef):
        decorators = [decorator_name(dec) for dec in node.decorator_list]
        if "abstractmethod" not in decorators:
            continue
        if decorators.index("abstractmethod") == len(decorators) - 1:
            continue
        yield Finding(
            check="abs/decorator-order",
            severity=Severity.ERROR,
            message=(
                f"@abstractmethod 不是最内层装饰器（当前顺序："
                f"{' → '.join('@' + d for d in decorators)}），抽象约束会失效"
            ),
            location=Location.of(node, src.rel, node.name),
            hint="把 @abstractmethod 放到紧贴 def 的位置：@property 在上、@abstractmethod 在下",
        )


def check_not_enforced(ctx) -> Iterator[Finding]:
    """``abs/not-enforced``：写了 ``@abstractmethod`` 但类没有真正的抽象元类。"""
    hierarchy = Hierarchy(ctx.sources)
    for record in ctx.sources.classes:
        if not is_abstract_node(record) or hierarchy.has_abc_metaclass(record):
            continue
        if any(decorator_name(dec).endswith("Protocol") for dec in record.decorators):
            continue
        if any(base.rpartition(".")[2] == "Protocol" for base in record.bases):
            continue
        yield Finding(
            check="abs/not-enforced",
            severity=Severity.WARNING,
            message=f"{record.name} 用了 @abstractmethod，但没有 ABCMeta 元类也没继承 ABC，约束不生效",
            location=record.location,
            hint="加 metaclass=ABCMeta（Qt 子类用 CombinedMeta），或继承 abc.ABC",
        )


def check_metaclass_conflict(ctx) -> Iterator[Finding]:
    """``abs/metaclass``：同一个类里直接混合 Qt 与 ABCMeta 才需要合并元类。

    元类会被继承：``class Child(QtABCBase)`` 不需要再写 ``metaclass=``，
    所以只有当「纯 Qt 元类的基类」和「ABC 元类的基类」同时出现在直接基类里
    才算冲突——基类已经用 CombinedMeta 合并过的不算。
    """
    hierarchy = Hierarchy(ctx.sources)
    for record in ctx.sources.classes:
        if record.metaclass:
            continue
        base_records = hierarchy.bases(record)
        if not any(hierarchy.metaclass_kind(base) == "abc" for base in base_records):
            continue
        if not any(
            hierarchy.metaclass_kind(base) != "abc" and _touches_qt(hierarchy, base)
            for base in base_records
        ) and not any(_is_qt_name(name) for name in record.bases):
            continue
        yield Finding(
            check="abs/metaclass",
            severity=Severity.ERROR,
            message=(
                f"{record.name} 同时继承 Qt 类与抽象基类却没有指定 metaclass，"
                "运行时会 TypeError: metaclass conflict"
            ),
            location=record.location,
            hint="加 metaclass=CombinedMeta（见 stlibs/themes/base.py）",
        )


def _touches_qt(hierarchy: Hierarchy, record: ClassRecord) -> bool:
    """该类自身或它的任一基类是不是 Qt 类。"""
    if any(_is_qt_name(name) for name in record.bases):
        return True
    return hierarchy.is_qt_like(record)


def _is_qt_name(name: str) -> bool:
    head = name.rpartition(".")[2] or name
    return head.startswith("Q") and head[1:2].isupper()


def check_signature(ctx) -> Iterator[Finding]:
    """``abs/signature``：实现签名必须兼容抽象声明。"""
    hierarchy = Hierarchy(ctx.sources)
    for record in ctx.sources.classes:
        for name, node in record.methods.items():
            base_node = _declared_abstract(hierarchy, record, name)
            if base_node is None:
                continue

            if is_property(base_node) and not is_property(node):
                yield Finding(
                    check="abs/signature",
                    severity=Severity.WARNING,
                    message=f"{record.name}.{name} 抽象声明是 property，实现却是普通方法",
                    location=Location.of(node, record.file.rel, f"{record.name}.{name}"),
                    hint="改成 @property，或把抽象声明改成方法",
                )

            base_params = positional_params(base_node, strip_self=not is_static(base_node))
            impl_required = required_params(node, strip_self=not is_static(node))
            impl_params = positional_params(node, strip_self=not is_static(node))

            if len(impl_required) > len(base_params):
                yield Finding(
                    check="abs/signature",
                    severity=Severity.ERROR,
                    message=(
                        f"{record.name}.{name} 需要 {len(impl_required)} 个必填参数，"
                        f"但抽象声明 {_signature_text(base_node)} 只提供 {len(base_params)} 个"
                    ),
                    location=Location.of(node, record.file.rel, f"{record.name}.{name}"),
                    hint="给多出来的参数加默认值，或同步修改抽象声明",
                )
                continue

            for index, (expected, actual) in enumerate(zip(base_params, impl_params)):
                if expected.arg == actual.arg:
                    continue
                yield Finding(
                    check="abs/signature",
                    severity=Severity.WARNING,
                    message=(
                        f"{record.name}.{name} 第 {index + 1} 个参数名是 {actual.arg!r}，"
                        f"抽象声明里是 {expected.arg!r}，按位置调用会传错"
                    ),
                    location=Location.of(node, record.file.rel, f"{record.name}.{name}"),
                    hint=f"统一成 {expected.arg}（{_signature_text(base_node)}），或统一用关键字调用",
                )
                break


def _declared_abstract(hierarchy: Hierarchy, record: ClassRecord, name: str) -> ast.FunctionDef | None:
    for base in hierarchy.bases(record):
        for ancestor in [base, *hierarchy.ancestors(base)]:
            node = ancestor.methods.get(name)
            if node is not None and is_abstract(node):
                return node
    return None


def _signature_text(node: ast.FunctionDef) -> str:
    params = ", ".join(arg.arg for arg in positional_params(node, strip_self=not is_static(node)))
    return f"{node.name}({params})"
