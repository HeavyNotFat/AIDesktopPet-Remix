"""配置与资源结构校验。

这个项目的配置是「dataclass 定义结构 + JSON 存数据」：

* ``resources/configure.json``  ←→ ``stlibs._BaseModelConfig``
* ``resources/animation/*.json`` ←→ ``stlibs._BaseModelAnimation``

两者的连接处是**静默**的：``ConfigLoader`` 只挑认识的键，JSON 里多写的键
保存时会被丢掉，少写的键则会在业务代码取用时 ``KeyError``。所以这里既查
JSON→dataclass，也查代码实际取用的键。

* ``config/schema``      configure.json 与 dataclass 字段对不上
* ``config/missing-key`` 代码里 ``Config.x['y']`` 用到的键在 JSON 里没有
* ``config/animation``   动画映射指向的字段在动画 JSON 里不存在
* ``config/prompts``     prompts.json 缺键
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Iterator

from ..core import Finding, Location, Severity

CONFIG_PATH = "resources/configure.json"
ANIMATION_PATHS = ("resources/animation/live2d.json", "resources/animation/static.json")
PROMPTS_PATH = "resources/prompts.json"

CONFIG_DATACLASS = ("stlibs", "_BaseModelConfig")
ANIMATION_DATACLASS = ("stlibs", "_BaseModelAnimation")


def _json(ctx, rel: str):
    path = ctx.root / rel
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _dataclass_fields(ctx, module: str, name: str) -> list[str]:
    src = ctx.sources.modules.get(module)
    if src is None:
        return []
    for node in src.tree.body:
        if isinstance(node, ast.ClassDef) and node.name == name:
            fields: list[str] = []
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    fields.append(item.target.id)
            return fields
    return []


def check_schema(ctx) -> Iterator[Finding]:
    data = _json(ctx, CONFIG_PATH)
    if data is None:
        yield Finding(
            check="config/schema",
            severity=Severity.ERROR,
            message=f"读不到或解析不了 {CONFIG_PATH}",
            location=Location(CONFIG_PATH, 1),
            hint="检查文件是否被误删、JSON 是否合法",
        )
        return

    fields = set(_dataclass_fields(ctx, *CONFIG_DATACLASS))
    if not fields:
        return

    for key in sorted(set(data) - fields):
        yield Finding(
            check="config/schema",
            severity=Severity.WARNING,
            message=f"{CONFIG_PATH} 里的 {key!r} 不是 {CONFIG_DATACLASS[1]} 的字段，保存配置时会被丢弃",
            location=Location(CONFIG_PATH, 1, key),
            hint=f"要么在 {CONFIG_DATACLASS[1]} 里补上该字段，要么删掉这个键",
        )
    for key in sorted(fields - set(data)):
        yield Finding(
            check="config/schema",
            severity=Severity.WARNING,
            message=f"{CONFIG_DATACLASS[1]} 声明了 {key!r}，但 {CONFIG_PATH} 里没有，首次保存前取用会报错",
            location=Location(CONFIG_PATH, 1, key),
            hint="补进 JSON，或给 dataclass 字段一个默认值",
        )


def check_missing_key(ctx) -> Iterator[Finding]:
    """代码里 ``Config.<section>['<key>']`` 用到的键必须在 JSON 里存在。"""
    data = _json(ctx, CONFIG_PATH)
    if not isinstance(data, dict):
        return

    reported: set[tuple[str, str]] = set()
    for src, node in ctx.sources.iter_nodes(ast.Subscript):
        chain = _chain(node.value)
        if not chain or len(chain) != 2 or chain[0] != "Config":
            continue
        section = chain[1]
        if section not in data or not isinstance(data[section], dict):
            continue
        key = node.slice
        if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
            continue
        if key.value in data[section]:
            continue
        marker = (section, key.value)
        if marker in reported:
            continue
        reported.add(marker)
        yield Finding(
            check="config/missing-key",
            severity=Severity.ERROR,
            message=f"代码取用 Config.{section}['{key.value}']，但 {CONFIG_PATH} 的 {section} 里没有这个键",
            location=Location.of(node, src.rel, f"Config.{section}"),
            hint=f"把 {key.value} 加进 {CONFIG_PATH} 的 {section} 段",
        )


def check_animation(ctx) -> Iterator[Finding]:
    fields = set(_dataclass_fields(ctx, *ANIMATION_DATACLASS))
    mappings = _animation_mappings(ctx)

    for rel in ANIMATION_PATHS:
        data = _json(ctx, rel)
        if data is None:
            continue
        animation = data.get("animation", {})
        special = data.get("special", {})

        for source_name, field in sorted(mappings.items()):
            if field in animation or field in special:
                continue
            if fields and field not in fields:
                yield Finding(
                    check="config/animation",
                    severity=Severity.ERROR,
                    message=f"动画映射 {source_name!r} → {field}，但 {ANIMATION_DATACLASS[1]} 里没有这个字段",
                    location=Location(rel, 1, source_name),
                    hint="改映射或补 dataclass 字段，二者必须一致",
                )
                continue
            yield Finding(
                check="config/animation",
                severity=Severity.ERROR,
                message=f"{rel} 缺少动画映射 {source_name!r} 指向的 {field}",
                location=Location(rel, 1, field),
                hint="补齐 JSON 键，否则点击/抚摸该部位会 KeyError",
            )

        extra = set(animation) | set(special)
        if fields:
            for key in sorted(extra - fields):
                yield Finding(
                    check="config/animation",
                    severity=Severity.WARNING,
                    message=f"{rel} 里的 {key} 不是 {ANIMATION_DATACLASS[1]} 的字段，加载时会被忽略",
                    location=Location(rel, 1, key),
                    hint="同步 dataclass 或删掉多余键",
                )


def _animation_mappings(ctx) -> dict[str, str]:
    """从**所有**主题里读 MAPPING_ANIMATION / MAPPING_SPECTIAL_ANIMATION。

    以前只读 hacker：新增主题的动画映射完全不被校验，
    而报错位置指向 JSON，排查时会看错方向。
    """
    mappings: dict[str, str] = {}
    for src in ctx.sources.files:
        if not src.rel.startswith("stlibs/themes/") or not src.rel.endswith("__init__.py"):
            continue
        for node in src.tree.body:
            if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Dict):
                continue
            for target in node.targets:
                if not (isinstance(target, ast.Name) and target.id.startswith("MAPPING_")):
                    continue
                for key, value in zip(node.value.keys, node.value.values):
                    if isinstance(key, ast.Constant) and isinstance(value, ast.Constant):
                        mappings[str(key.value)] = str(value.value)
    return mappings


def check_prompts(ctx) -> Iterator[Finding]:
    data = _json(ctx, PROMPTS_PATH)
    if not isinstance(data, dict):
        return
    for src in ctx.sources.files:
        # 只看真的加载了 prompts.json 的文件，避免把同名的局部字典当配置
        if "prompts.json" not in src.text:
            continue
        for node in ast.walk(src.tree):
            if not isinstance(node, ast.Subscript):
                continue
            chain = _chain(node.value)
            if not chain or chain[-1] != "prompts":
                continue
            key = node.slice
            if isinstance(key, ast.Constant) and isinstance(key.value, str) and key.value not in data:
                yield Finding(
                    check="config/prompts",
                    severity=Severity.ERROR,
                    message=f"代码取用 prompts['{key.value}']，但 {PROMPTS_PATH} 里没有这个键",
                    location=Location.of(node, src.rel, "prompts"),
                    hint="补进 prompts.json，或改用已有的键",
                )


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
