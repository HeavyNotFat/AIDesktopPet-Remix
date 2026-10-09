from __future__ import annotations

import ast
from dataclasses import dataclass, field

from .core import Location
from .source import SourceIndex

PROTOCOL_MODULE = "stlibs"
PROTOCOL_CLASS = "_ThemeTypingProtocol"
BASE_MODULE = "stlibs.themes.base"

# 主题包内必须存在的子模块（``SharingData.theme.<sub>.<Page>`` 用它取页面）
REQUIRED_SUBMODULES: tuple[str, ...] = ("general", "llm", "tts", "settings", "animation")

# 契约映射名 → 对应的抽象基类（成员要求从 ABC 自动推导）
MAPPING_ABC: dict[str, str] = {
    "Window": "MainWindowABS",
    "Menu": "MenuWidgetABS",
    "ModelChat": "ModelChatABS",
    "IconList": "IconListABS",
}

# 抽象基类管不到的映射，显式列出调用方，改动时必须同步。
EXTRA_MEMBERS: dict[str, tuple[str, ...]] = {
    # stlibs/themes/hacker/__init__.py::ModelChat 通过 self.chat.xxx 调用
    "ChatWidget": (
        "userInputSignal",
        "add_user_msg",
        "add_assistant_msg",
        "disable_send_button",
        "enable_send_button",
        "update_bubble_widths",
        "scroll_to_bottom",
        "clear_messages",
    ),
    # stlibs/graphics/chat.py 与 ModelChat 通过气泡对象追加流式文本
    "ChatBubble": ("append_text", "updateBubbleWidth"),
}

# ``SharingData.theme`` 上允许出现的名字（除映射与子模块外）
EXTRA_ATTRS: tuple[str, ...] = ("base", "PALETTE", "THEME_LABEL")


@dataclass(slots=True)
class ThemeContract:
    mappings: dict[str, str] = field(default_factory=dict)      # 名称 → 注解源码
    submodules: tuple[str, ...] = REQUIRED_SUBMODULES
    required_members: dict[str, tuple[str, ...]] = field(default_factory=dict)
    declared_at: Location | None = None
    abc_members: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def all_names(self) -> tuple[str, ...]:
        return (*self.mappings.keys(), *self.submodules)

    def is_module(self, name: str) -> bool:
        return name in self.submodules

    def describe(self) -> list[str]:
        lines = [f"契约来源：{self.declared_at}"]
        for name, annotation in self.mappings.items():
            members = self.required_members.get(name, ())
            suffix = f"  必需成员：{', '.join(members)}" if members else ""
            lines.append(f"  {name:12s} : {annotation}{suffix}")
        lines.append(f"  子模块      : {', '.join(self.submodules)}")
        return lines


def build_contract(sources: SourceIndex) -> ThemeContract:
    contract = ThemeContract()
    proto = sources.modules.get(PROTOCOL_MODULE)
    modules: list[str] = []
    if proto is not None:
        for node in proto.tree.body:
            if isinstance(node, ast.ClassDef) and node.name == PROTOCOL_CLASS:
                contract.declared_at = Location.of(node, proto.rel, node.name)
                _read_protocol(node, contract, modules)

    # ``theme`` 本身指主题包，不需要在主题包里再"提供"一次
    declared = tuple(name for name in modules if name != "theme")
    contract.submodules = declared or REQUIRED_SUBMODULES

    contract.abc_members = collect_abc_members(sources)
    for mapping, abc_name in MAPPING_ABC.items():
        members = contract.abc_members.get(abc_name)
        if members:
            contract.required_members[mapping] = members
    for mapping, members in EXTRA_MEMBERS.items():
        merged = list(contract.required_members.get(mapping, ()))
        merged.extend(name for name in members if name not in merged)
        if merged:
            contract.required_members[mapping] = tuple(merged)

    return contract


def _read_protocol(node: ast.ClassDef, contract: ThemeContract, modules: list[str]) -> None:
    for item in node.body:
        if not (isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name)):
            continue
        name = item.target.id
        if name.startswith("_"):
            continue
        annotation = ast.unparse(item.annotation)
        if "ModuleType" in annotation:
            modules.append(name)
            continue
        contract.mappings[name] = annotation


def collect_abc_members(sources: SourceIndex) -> dict[str, tuple[str, ...]]:
    """``stlibs/themes/base.py`` 里每个 ABC 的抽象成员。"""
    module = sources.modules.get(BASE_MODULE)
    if module is None:
        return {}

    raw: dict[str, tuple[str, ...]] = {}
    bases: dict[str, tuple[str, ...]] = {}
    for node in module.tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        names: list[str] = []
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if any(_decorator_name(dec) == "abstractmethod" for dec in item.decorator_list):
                    names.append(item.name)
        raw[node.name] = tuple(names)
        bases[node.name] = tuple(ast.unparse(base) for base in node.bases)

    resolved: dict[str, tuple[str, ...]] = {}
    for name in raw:
        merged: list[str] = []
        for base in bases.get(name, ()):
            for member in resolved.get(base, raw.get(base, ())):
                if member not in merged:
                    merged.append(member)
        for member in raw[name]:
            if member not in merged:
                merged.append(member)
        resolved[name] = tuple(merged)
    return resolved


def _decorator_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Call):
        return _decorator_name(node.func)
    return ""
