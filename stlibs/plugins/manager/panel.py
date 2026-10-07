from __future__ import annotations

import os
from pathlib import Path

from .core import PluginManager

LANGUAGE_LABEL = {"python": "Python（进程内）", "javascript": "JavaScript（node 子进程）"}

EMPTY_HINT = "还没有插件。往插件目录里放一个带 plugin.json 的文件夹就能被认出来。"
READY_HINT = "选中一行可以启用/停用或重载；停用状态会写进配置。"
NO_SELECTION = ("warning", "先在表里选中一个插件")


class PluginsPanel:

    def __init__(self, manager: PluginManager | None = None):
        self._manager = manager

    @property
    def manager(self) -> PluginManager:
        if self._manager is not None:
            return self._manager

        from .core import manager as current

        return current

    def refresh(self):
        """重新读配置里的目录并扫描磁盘。"""
        from ... import Config

        config = getattr(Config, "plugins", None) or {}
        directory = config.get("directory")
        if directory:
            self.manager.directory = str(directory)
        self.manager.discover()
        return self

    def directory(self) -> str:
        return str(self.manager.directory)

    def enabled(self) -> bool:
        return self.manager.enabled()

    def rows(self) -> list:
        """表格行：名称 / 语言 / 版本 / 状态 / 调用次数（先 refresh 再读）。

        ``icon`` 是这一行的图标（QIcon）；没有 Qt 时是 None，展示层跳过图标列就行。
        """
        rows = []
        for info in self.manager.status()["plugins"]:
            rows.append({
                "id": info["id"],
                "name": info["name"],
                "title": f"{info['name']}  ({info['id']})",
                "language": LANGUAGE_LABEL.get(info["language"], info["language"]),
                "version": info["version"],
                "state": state_text(info),
                "calls": str(info["calls"]),
                "enabled": info["enabled"],
                "loaded": info["loaded"],
                "icon": self.icon(info["id"]),
            })
        return rows

    def icon(self, plugin_id: str, size: int = 48):
        """这一行的插件图标（自定义图或字母徽章）；没有界面/拿不到就返回 None。"""
        try:
            icon = self.manager.plugin_icon(plugin_id, size)
        except Exception as exc:  # noqa: BLE001 - 图标只是装饰
            print(f"[plugin:{plugin_id}] 图标读取失败：{exc}")
            return None

        # 空图标（没有 QGuiApplication 时就是这种）按"没有"处理，展示层好判断
        return None if icon is None or icon.isNull() else icon

    def hint(self) -> str:
        """详情行文案（先 refresh 再读）。"""
        problems = (self.manager.problems or [])
        if problems:
            return "有问题：" + "；".join(f"{item['name']} —— {item['error']}" for item in problems)
        if not self.manager.infos:
            return EMPTY_HINT
        return READY_HINT

    def selected(self, row: int):
        """行号 -> 插件 id（表格里显示的标题带 id 后缀，这里直接按顺序取更稳）。"""
        infos = list(self.manager.infos.values())
        if row < 0 or row >= len(infos):
            return None
        return infos[row].id

    def set_enabled(self, enabled: bool):
        """总开关：关掉会把已加载的插件全部卸载。"""
        from ... import Config, ConfigLoader

        plugins = Config.plugins if isinstance(Config.plugins, dict) else {}
        plugins["enable"] = bool(enabled)
        Config.plugins = plugins
        ConfigLoader.save_config()

        if enabled:
            self.manager.load_all()
            self.refresh()
            return "success", "插件系统已启用"

        for plugin_id in list(self.manager.infos):
            self.manager.unload(plugin_id)
        self.refresh()
        return "info", "插件系统已停用（插件都卸载了）"

    def toggle(self, plugin_id: str | None):
        if not plugin_id:
            return NO_SELECTION

        info = self.manager.infos.get(plugin_id)
        if info is None:
            return "error", f"找不到插件 {plugin_id}"

        target = not info.manifest.enabled
        try:
            self.manager.set_enabled(plugin_id, target)
        except Exception as exc:  # noqa: BLE001
            return "error", f"切换失败：{exc}"

        self.refresh()
        return "success", f"插件「{info.manifest.name}」已{'启用' if target else '停用'}"

    def reload(self, plugin_id: str | None):
        if not plugin_id:
            return NO_SELECTION

        try:
            self.manager.reload(plugin_id)
        except Exception as exc:  # noqa: BLE001
            return "error", f"重载失败：{exc}"

        info = self.manager.infos.get(plugin_id)
        if info is not None and not info.loaded and info.error:
            self.refresh()
            return "error", f"重载后仍然失败：{info.error[:120]}"

        self.refresh()
        return "success", f"已重载插件 {plugin_id}"

    def open_folder(self):
        """创建（如果还没建）并打开插件目录。"""
        target = Path(self.manager.directory).resolve()
        try:
            target.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return "error", f"建不了插件目录：{exc}"

        _open_local(str(target))
        return "info", f"插件目录：{target}"

    def commands(self) -> dict:
        return self.manager.commands()


def _open_local(path: str) -> bool:
    """用系统文件管理器打开目录；没有界面时退化成打印路径。"""
    try:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        return True
    except Exception as exc:  # noqa: BLE001 - 没装 Qt / 无界面都只是打不开而已
        print(f"[plugin] 插件目录：{path}（打开失败：{exc}）")
        return False


def state_text(item: dict) -> str:
    """状态列文案：停用 / 加载失败 / 运行出错 / 已加载 / 未加载。"""
    if not item.get("enabled", True):
        return "已停用"
    if item.get("error"):
        # 加载成功但 hook 抛异常也要露出来，否则看着像一切正常
        prefix = "运行出错：" if item.get("loaded") else "加载失败："
        return prefix + str(item["error"])[:60]
    if item.get("loaded"):
        return f"已加载（{item.get('runtime', '')}）"
    return "未加载"


def ensure_directory(directory: str) -> str:
    """把插件目录准备好（第一次跑的时候它可能还不存在）。"""
    target = Path(directory).resolve()
    os.makedirs(target, exist_ok=True)
    return str(target)


__all__ = [
    "EMPTY_HINT",
    "LANGUAGE_LABEL",
    "NO_SELECTION",
    "READY_HINT",
    "PluginsPanel",
    "ensure_directory",
    "state_text",
]
