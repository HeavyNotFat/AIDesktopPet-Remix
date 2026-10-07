from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

MANIFEST_NAME = "plugin.json"
DATA_DIR_NAME = ".data"

LANGUAGES = {
    "python": ("main.py",),
    "javascript": ("main.js",),
}
DEFAULT_ENTRY = {name: entries[0] for name, entries in LANGUAGES.items()}

_ID_PATTERN = re.compile(r"^[\w.\-]+$", re.UNICODE)

SETTING_TYPES = ("text", "password", "number", "switch")

# 插件图标：相对插件目录、必须是图片文件（svg 由 Qt 的 svg 插件按需解码）
ICON_SUFFIXES = (".png", ".svg", ".jpg", ".jpeg", ".webp", ".ico", ".bmp")


class ManifestError(ValueError):
    """清单缺失/字段不对/入口文件找不到。"""

@dataclass
class PluginManifest:
    id: str
    name: str
    path: Path
    language: str = "python"
    entry: str = ""
    version: str = "0.1.0"
    description: str = ""
    author: str = ""
    hooks: tuple = ()
    settings: tuple = ()
    enabled: bool = True
    order: int = 100
    icon: str = ""
    menu: str = ""

    @property
    def entry_path(self) -> Path:
        return self.path / self.entry

    @property
    def icon_path(self) -> Path | None:
        """自定义图标的绝对路径；没配或文件不在就返回 None（调用方回退到内置徽章）。"""
        if not self.icon:
            return None
        target = self.path / self.icon
        return target if target.is_file() else None

    @property
    def menu_title(self) -> str:
        """右键菜单里这一组的标题：清单里的 menu，没写就用插件名。"""
        return self.menu or self.name

    def public(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "language": self.language,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "hooks": list(self.hooks),
            "settings": [dict(item) for item in self.settings],
            "enabled": self.enabled,
            "icon": self.icon,
            "menu": self.menu_title,
            "path": str(self.path),
        }


def _clean_settings(raw) -> tuple:
    if not isinstance(raw, list):
        return ()

    items = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip()
        if not key:
            continue
        kind = str(item.get("type") or "text").strip().lower()
        items.append({
            "key": key,
            "label": str(item.get("label") or key),
            "type": kind if kind in SETTING_TYPES else "text",
            "default": item.get("default", ""),
        })
    return tuple(items)


def _clean_icon(raw, path: Path) -> str:
    """图标路径：只认插件目录内的相对路径；不合法就当没写（回退内置徽章，不算错误）。

    插件清单写错图标不该让整个插件加载不了——图标只是装饰。
    """
    text = str(raw or "").strip().replace("\\", "/")
    if not text:
        return ""

    relative = Path(text)
    if relative.is_absolute() or ".." in relative.parts:
        return ""
    if relative.suffix.lower() not in ICON_SUFFIXES:
        return ""
    return text


def parse_manifest(directory, raw: dict, enabled: bool = True) -> PluginManifest:
    if not isinstance(raw, dict):
        raise ManifestError("plugin.json 必须是 JSON 对象")

    plugin_id = str(raw.get("id") or os.path.basename(str(directory))).strip()
    if not plugin_id or not _ID_PATTERN.match(plugin_id):
        raise ManifestError(f"插件 id 不合法：{plugin_id!r}（只允许字母数字、下划线、点、短横线）")

    language = str(raw.get("language") or "python").strip().lower()
    if language not in LANGUAGES:
        raise ManifestError(f"不支持的语言：{language}（可选 {', '.join(LANGUAGES)}）")

    entry = str(raw.get("entry") or DEFAULT_ENTRY[language]).strip()
    if os.path.isabs(entry) or ".." in Path(entry).parts:
        raise ManifestError(f"entry 必须是插件目录内的相对路径：{entry!r}")

    path = Path(directory)
    if not (path / entry).is_file():
        raise ManifestError(f"找不到入口文件：{entry}")

    hooks = raw.get("hooks") or ()
    if isinstance(hooks, str):
        hooks = (hooks,)
    hooks = tuple(str(item).strip() for item in hooks if str(item).strip())

    try:
        order = int(raw.get("order", 100))
    except (TypeError, ValueError):
        order = 100

    return PluginManifest(
        id=plugin_id,
        name=str(raw.get("name") or plugin_id),
        path=path,
        language=language,
        entry=entry,
        version=str(raw.get("version") or "0.1.0"),
        description=str(raw.get("description") or ""),
        author=str(raw.get("author") or ""),
        hooks=hooks,
        settings=_clean_settings(raw.get("settings")),
        enabled=enabled,
        order=order,
        icon=_clean_icon(raw.get("icon"), path),
        menu=str(raw.get("menu") or "").strip(),
    )


def load_manifest(directory, enabled: bool = True) -> PluginManifest:
    manifest_path = Path(directory) / MANIFEST_NAME
    if not manifest_path.is_file():
        raise ManifestError(f"缺少 {MANIFEST_NAME}")

    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ManifestError(f"读不了 {MANIFEST_NAME}：{exc}") from exc

    return parse_manifest(directory, raw, enabled=enabled)


def discover(directory, disabled=(), data_dir=None) -> tuple[list[PluginManifest], list[dict]]:
    root = Path(directory)
    plugins: list[PluginManifest] = []
    problems: list[dict] = []
    seen: dict[str, Path] = {}

    if not root.is_dir():
        return plugins, problems

    for child in sorted(root.iterdir()):
        if not child.is_dir() or child.name.startswith(".") or child.name.startswith("_"):
            continue

        try:
            manifest = load_manifest(child, enabled=child.name not in set(disabled))
        except ManifestError as exc:
            problems.append({"path": str(child), "name": child.name, "error": str(exc)})
            continue

        if manifest.id in seen:
            problems.append({
                "path": str(child),
                "name": manifest.id,
                "error": f"插件 id 与 {seen[manifest.id]} 重复",
            })
            continue

        seen[manifest.id] = child
        plugins.append(manifest)

    plugins.sort(key=lambda item: (item.order, item.id))
    return plugins, problems


def data_path(directory, plugin_id: str) -> Path:
    return Path(directory) / DATA_DIR_NAME / f"{plugin_id}.json"


__all__ = [
    "DATA_DIR_NAME",
    "DEFAULT_ENTRY",
    "ICON_SUFFIXES",
    "LANGUAGES",
    "MANIFEST_NAME",
    "ManifestError",
    "PluginManifest",
    "SETTING_TYPES",
    "data_path",
    "discover",
    "load_manifest",
    "parse_manifest",
]
