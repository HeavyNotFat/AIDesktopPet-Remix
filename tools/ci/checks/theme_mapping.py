from __future__ import annotations

import ast
from collections import defaultdict
from typing import Iterator

from ..core import Finding, Location, Severity
from ..contract import EXTRA_ATTRS, MAPPING_ABC, ThemeContract
from ..source import SourceFile

THEME_ROOT = "stlibs/themes/"


def _theme_packages(ctx) -> dict[str, SourceFile]:
    """``stlibs/themes/<name>/__init__.py`` → 主题包。"""
    packages: dict[str, SourceFile] = {}
    for src in ctx.sources.files:
        parts = src.rel.split("/")
        if len(parts) == 4 and parts[0] == "stlibs" and parts[1] == "themes" and parts[3] == "__init__.py":
            packages[parts[2]] = src
    return packages


def _exports(src: SourceFile) -> dict[str, tuple[str, ast.AST]]:
    exports: dict[str, tuple[str, ast.AST]] = {}
    class_names = {node.name for node in src.tree.body if isinstance(node, ast.ClassDef)}

    for node in src.tree.body:
        if isinstance(node, ast.ClassDef):
            exports[node.name] = ("class", node)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            exports[node.name] = ("function", node)
        elif isinstance(node, ast.Assign):
            kind, value = _value_kind(node.value, class_names)
            for target in node.targets:
                if isinstance(target, ast.Name):
                    exports[target.id] = (kind, node.value)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            kind, value = _value_kind(node.value, class_names)
            exports[node.target.id] = (kind, node)
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "*":
                    continue
                local = alias.asname or alias.name
                # 存 alias 本身：后面要靠它把 import 进来的映射解析回真实类
                exports.setdefault(local, ("import", alias))
    return exports


def _value_kind(value: ast.AST | None, class_names: set[str]) -> tuple[str, ast.AST | None]:
    if isinstance(value, ast.Name) and value.id in class_names:
        return "class", value
    if isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id in class_names:
        return "instance", value
    if value is None:
        return "value", value
    return "value", value


def _export_class_name(sources, src: SourceFile, entry: tuple[str, ast.AST] | None) -> str | None:
    """映射指向哪个类：本文件的类、import 重导出、实例映射，统一走 ``resolve_class`` 解析。"""
    if not entry:
        return None

    kind, node = entry
    if kind == "class" and isinstance(node, ast.Name):
        name = node.id
    elif kind == "instance" and isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        name = node.func.id
    elif kind == "value" and isinstance(node, ast.Name):
        name = node.id
    elif kind == "import":
        alias = getattr(node, "asname", None) or getattr(node, "name", None)
        if not isinstance(alias, str):
            return None
        name = alias
    else:
        return None

    record = sources.resolve_class(src, name)
    return record.name if record is not None else None


def _module_members(ctx, theme: str, submodule: str) -> set[str] | None:
    """``stlibs/themes/<theme>/<submodule>.py`` 顶层提供的名字。"""
    src = ctx.sources.modules.get(f"stlibs.themes.{theme}.{submodule}")
    if src is None:
        return None
    return set(ctx.sources.module_members(src.module))


# 这些目录不是应用代码，里面的 `theme` 变量名会干扰用法扫描
NON_APP_PREFIXES = ("tools/", "tests/", "docs/", "resources/")


def _usage_sites(ctx) -> tuple[dict[str, list[Location]], list[tuple[str, str, Location]]]:
    attributes: dict[str, list[Location]] = defaultdict(list)
    module_members: list[tuple[str, str, Location]] = []

    for src, node in ctx.sources.iter_nodes(ast.Attribute):
        if src.rel.startswith(NON_APP_PREFIXES):
            continue
        chain = _chain(node)
        if chain is None:
            continue
        for index, part in enumerate(chain):
            if part != "theme" or index == 0:
                continue
            rest = chain[index + 1 :]
            if not rest:
                continue
            name = rest[0]
            attributes[name].append(Location.of(node, src.rel, f"theme.{'.'.join(rest)}"))
            if len(rest) >= 2:
                module_members.append((name, rest[1], Location.of(node, src.rel, f"theme.{'.'.join(rest)}")))
            break

    return attributes, module_members


def _chain(node: ast.AST) -> list[str] | None:
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    else:
        return None
    return list(reversed(parts))


def check_mapping_missing(ctx) -> Iterator[Finding]:
    contract: ThemeContract = ctx.contract
    for theme, src in sorted(_theme_packages(ctx).items()):
        exports = _exports(src)
        for name in contract.mappings:
            if name in exports:
                continue
            yield Finding(
                check="theme/mapping-missing",
                severity=Severity.ERROR,
                message=(
                    f"主题 {theme!r} 没有提供映射 {name}，"
                    f"运行到 SharingData.theme.{name} 时会 AttributeError"
                ),
                location=Location.of(src.tree, src.rel, f"themes.{theme}"),
                hint=f"在 {src.rel} 里补上 {name} = <实现类>（契约见 {contract.declared_at}）",
            )


def check_submodule_missing(ctx) -> Iterator[Finding]:
    contract: ThemeContract = ctx.contract
    for theme, src in sorted(_theme_packages(ctx).items()):
        for name in contract.submodules:
            module = ctx.sources.modules.get(f"stlibs.themes.{theme}.{name}")
            if module is not None:
                continue
            yield Finding(
                check="theme/submodule-missing",
                severity=Severity.ERROR,
                message=(
                    f"主题 {theme!r} 缺少子模块 {name}，"
                    f"SharingData.theme.{name}.* 无法使用"
                ),
                location=Location.of(src.tree, src.rel, f"themes.{theme}"),
                hint=f"新建 stlibs/themes/{theme}/{name}.py 并在 {src.rel} 里 import",
            )


def check_member_missing(ctx) -> Iterator[Finding]:
    contract: ThemeContract = ctx.contract
    from .abstract_api import Hierarchy

    hierarchy = Hierarchy(ctx.sources)
    for theme, src in sorted(_theme_packages(ctx).items()):
        exports = _exports(src)
        for mapping, members in contract.required_members.items():
            if mapping not in exports:
                continue  # 缺映射本身已经由 theme/mapping-missing 报过
            class_name = _export_class_name(ctx.sources, src, exports[mapping])
            if class_name is None:
                continue
            record = ctx.sources.resolve_class(src, class_name)
            if record is None:
                continue
            provided = set(record.methods) | set(record.attributes)
            for base in hierarchy.bases(record):
                provided |= set(base.methods) | set(base.attributes)
            missing = [name for name in members if name not in provided]
            if not missing:
                continue
            yield Finding(
                check="theme/member-missing",
                severity=Severity.ERROR,
                message=(
                    f"主题 {theme!r} 的 {mapping}（{record.name}）缺少契约成员："
                    f"{', '.join(missing)}"
                ),
                location=record.location,
                hint=f"补上这些方法/属性（契约来源：{_abc_hint(mapping)}）",
            )


def check_member_kind(ctx) -> Iterator[Finding]:
    """抽象声明是 property、实现却是方法（或反过来）。"""
    contract: ThemeContract = ctx.contract
    from .abstract_api import Hierarchy

    hierarchy = Hierarchy(ctx.sources)
    for theme, src in sorted(_theme_packages(ctx).items()):
        exports = _exports(src)
        for mapping in contract.required_members:
            class_name = _export_class_name(ctx.sources, src, exports.get(mapping))
            if class_name is None:
                continue
            record = ctx.sources.resolve_class(src, class_name)
            if record is None:
                continue
            for base in hierarchy.bases(record):
                for name, base_method in base.methods.items():
                    impl = record.methods.get(name)
                    if impl is None:
                        continue
                    base_is_prop = _has_decorator(base_method, "property")
                    impl_is_prop = _has_decorator(impl, "property")
                    if base_is_prop == impl_is_prop:
                        continue
                    yield Finding(
                        check="theme/member-kind",
                        severity=Severity.WARNING,
                        message=(
                            f"{record.name}.{name} 与抽象声明形态不一致"
                            f"（声明 {'property' if base_is_prop else '方法'}，"
                            f"实现 {'property' if impl_is_prop else '方法'}）"
                        ),
                        location=Location.of(impl, src.rel, f"{record.name}.{name}"),
                        hint="统一成同一种形态，否则调用方取值方式会不一样",
                    )


def check_usage_unsupported(ctx) -> Iterator[Finding]:
    """代码里用到的 ``theme.xxx``，每个主题都必须提供。"""
    contract: ThemeContract = ctx.contract
    usage, _ = _usage_sites(ctx)

    for name, locations in sorted(usage.items()):
        for theme, src in sorted(_theme_packages(ctx).items()):
            exports = _exports(src)
            if name in exports or name in contract.submodules:
                continue
            yield Finding(
                check="theme/usage-unsupported",
                severity=Severity.ERROR,
                message=f"主题 {theme!r} 没有提供 {name}，但代码在用 SharingData.theme.{name}",
                location=locations[0],
                hint=f"在主题 {theme} 里补上 {name}，或调整调用方",
            )


def check_protocol_drift(ctx) -> Iterator[Finding]:
    """代码用到的映射没写进 ``_ThemeTypingProtocol``。"""
    contract: ThemeContract = ctx.contract
    usage, _ = _usage_sites(ctx)
    allowed = set(contract.all_names()) | set(EXTRA_ATTRS)

    for name, locations in sorted(usage.items()):
        if name in allowed:
            continue
        yield Finding(
            check="theme/protocol-drift",
            severity=Severity.WARNING,
            message=(
                f"{locations[0].symbol} 用了主题映射 {name}，但它没有声明在 "
                "_ThemeTypingProtocol 里，IDE 与 CI 都无法约束主题实现"
            ),
            location=locations[0],
            hint="在 stlibs/__init__.py 的 _ThemeTypingProtocol 里补上该成员",
        )


def check_module_member(ctx) -> Iterator[Finding]:
    """``SharingData.theme.<子模块>.<成员>``：每个主题的同名子模块都要有该成员。"""
    contract: ThemeContract = ctx.contract
    _, module_usage = _usage_sites(ctx)

    for name, member, location in module_usage:
        if name not in contract.submodules:
            continue
        for theme, _src in sorted(_theme_packages(ctx).items()):
            members = _module_members(ctx, theme, name)
            if members is None:
                continue  # 子模块缺失已单独报
            if member in members:
                continue
            yield Finding(
                check="theme/module-member",
                severity=Severity.ERROR,
                message=(
                    f"主题 {theme!r} 的子模块 {name} 里没有 {member}，"
                    f"而代码在用 SharingData.theme.{name}.{member}"
                ),
                location=location,
                hint=f"在 stlibs/themes/{theme}/{name}.py 里补上 {member}",
            )


def check_kind_mismatch(ctx) -> Iterator[Finding]:
    contract: ThemeContract = ctx.contract
    kinds: dict[str, dict[str, str]] = defaultdict(dict)
    for theme, src in sorted(_theme_packages(ctx).items()):
        exports = _exports(src)
        for name in contract.mappings:
            if name in exports:
                kinds[name][theme] = exports[name][0]

    for name, per_theme in sorted(kinds.items()):
        distinct = set(per_theme.values())
        if len(distinct) < 2:
            continue
        detail = "、".join(f"{theme}={kind}" for theme, kind in sorted(per_theme.items()))
        src = _theme_packages(ctx)[sorted(per_theme)[0]]
        yield Finding(
            check="theme/kind-mismatch",
            severity=Severity.ERROR,
            message=f"映射 {name} 在各主题里的形态不一致（{detail}），换主题会改变调用方式",
            location=Location.of(src.tree, src.rel, name),
            hint="所有主题保持同一种形态（通常都是类）",
        )


def check_alias_duplicate(ctx) -> Iterator[Finding]:
    contract: ThemeContract = ctx.contract
    for theme, src in sorted(_theme_packages(ctx).items()):
        exports = _exports(src)
        seen: dict[str, list[str]] = defaultdict(list)
        for name in contract.mappings:
            entry = exports.get(name)
            if not entry:
                continue
            target = getattr(entry[1], "id", None) or ast.unparse(entry[1])
            seen[target].append(name)
        for target, names in seen.items():
            if len(names) < 2:
                continue
            yield Finding(
                check="theme/alias-duplicate",
                severity=Severity.WARNING,
                message=f"主题 {theme!r} 把 {target} 同时绑给了 {', '.join(sorted(names))}，多半是复制粘贴漏改",
                location=Location.of(src.tree, src.rel, target),
                hint="确认这些映射本来就该是同一个控件类，否则替换成对应的实现",
            )


def check_protocol_declared(ctx) -> Iterator[Finding]:
    """契约映射本身必须存在。"""
    contract: ThemeContract = ctx.contract
    if contract.declared_at is None:
        src = ctx.sources.modules.get("stlibs")
        yield Finding(
            check="theme/protocol-declared",
            severity=Severity.ERROR,
            message="找不到 _ThemeTypingProtocol，主题契约无法校验",
            location=Location(src.rel if src else "stlibs/__init__.py", 1, "_ThemeTypingProtocol"),
            hint="在 stlibs/__init__.py 里恢复该 Protocol",
        )
        return
    if not contract.mappings:
        yield Finding(
            check="theme/protocol-declared",
            severity=Severity.ERROR,
            message="_ThemeTypingProtocol 里没有任何映射声明，主题检查会形同虚设",
            location=contract.declared_at,
            hint="把主题必须提供的类映射写进 Protocol（Window=…, Button=…）",
        )


def check_abc_mapping(ctx) -> Iterator[Finding]:
    """契约里引用的抽象基类必须真的存在，名字改了要同步。"""
    contract: ThemeContract = ctx.contract
    known = set(contract.abc_members)
    for mapping, abc_name in MAPPING_ABC.items():
        if abc_name in known:
            continue
        yield Finding(
            check="theme/abc-mapping",
            severity=Severity.WARNING,
            message=(
                f"契约把 {mapping} 关联到 {abc_name}，但 stlibs/themes/base.py 里找不到它，"
                "该映射的成员要求会失效"
            ),
            location=contract.declared_at or Location("stlibs/themes/base.py", 1),
            hint="同步 base.py 里的抽象基类名字",
        )


def _has_decorator(node: ast.AST, name: str) -> bool:
    for dec in getattr(node, "decorator_list", []):
        target = dec.func if isinstance(dec, ast.Call) else dec
        if isinstance(target, ast.Name) and target.id == name:
            return True
        if isinstance(target, ast.Attribute) and target.attr == name:
            return True
    return False


def _abc_hint(mapping: str) -> str:
    abc = MAPPING_ABC.get(mapping)
    return f"stlibs/themes/base.py::{abc}" if abc else "stlibs/__init__.py::_ThemeTypingProtocol"
