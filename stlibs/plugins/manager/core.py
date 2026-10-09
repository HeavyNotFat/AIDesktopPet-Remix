from __future__ import annotations

import threading
import traceback
from dataclasses import dataclass, field
from pathlib import Path

from .. import api as api_module
from .. import manifest as manifest_module
from ..api import PluginAPI, PluginError
from ..manifest import ManifestError, PluginManifest
from ..pages import PluginPages
from . import python_plugin

DEFAULT_DIR = "./plugins"
DEFAULT_TIMEOUT = 3.0

# invokeMethod 的接收者要活到槽执行完，否则会被 GC 掉
_KEEP_ALIVE: list = []


@dataclass
class PluginInfo:
    manifest: PluginManifest
    loaded: bool = False
    error: str = ""
    runtime: str = ""
    calls: int = 0

    @property
    def id(self) -> str:
        return self.manifest.id

    def public(self) -> dict:
        data = self.manifest.public()
        data.update({"loaded": self.loaded, "error": self.error, "runtime": self.runtime, "calls": self.calls})
        return data


@dataclass
class MenuItem:
    plugin: str
    label: str
    action: str


@dataclass
class MenuGroup:
    """右键菜单里一个插件那一组：标题、条目和 QPixmap 图标。"""
    plugin: str
    title: str
    items: list = field(default_factory=list)
    icon: object = None

    def __len__(self) -> int:
        return len(self.items)

    def public(self) -> dict:
        return {
            "plugin": self.plugin,
            "title": self.title,
            "items": [{"label": item.label, "action": item.action} for item in self.items],
        }


@dataclass
class PluginManager:
    directory: str = DEFAULT_DIR
    timeout: float = DEFAULT_TIMEOUT

    infos: dict = field(default_factory=dict)
    problems: list = field(default_factory=list)
    # 插件注册的设置页
    pages: PluginPages = None
    _apis: dict = field(default_factory=dict)
    _hooks: dict = field(default_factory=dict)
    _lock: threading.RLock = field(default_factory=threading.RLock)
    _prompts_cache: list = field(default_factory=list)
    _ui_dispatch: object = None

    def __post_init__(self):
        self.directory = str(self.directory or DEFAULT_DIR)
        if self.pages is None:
            self.pages = PluginPages(self)

    @staticmethod
    def _config() -> dict:
        from ... import Config

        plugins = getattr(Config, "plugins", None)
        return plugins if isinstance(plugins, dict) else {}

    def enabled(self) -> bool:
        return bool(self._config().get("enable", True))

    def disabled_ids(self) -> list:
        disabled = self._config().get("disabled") or []
        return [str(item) for item in disabled] if isinstance(disabled, list) else []

    def settings_for(self, plugin_id: str) -> dict:
        settings = self._config().get("settings") or {}
        if not isinstance(settings, dict):
            return {}
        values = settings.get(plugin_id) or {}
        return dict(values) if isinstance(values, dict) else {}

    def set_setting(self, plugin_id: str, key: str, value):
        from ... import Config, ConfigLoader

        plugins = self._config()
        settings = plugins.setdefault("settings", {})
        settings.setdefault(plugin_id, {})[key] = value
        Config.plugins = plugins
        ConfigLoader.save_config()
        return value

    def set_disabled(self, plugin_id: str, disabled: bool):
        from ... import Config, ConfigLoader

        plugins = self._config()
        items = [str(item) for item in (plugins.get("disabled") or [])]
        if disabled and plugin_id not in items:
            items.append(plugin_id)
        elif not disabled and plugin_id in items:
            items.remove(plugin_id)

        plugins["disabled"] = items
        Config.plugins = plugins
        ConfigLoader.save_config()
        return disabled

    def data_file(self, plugin_id: str) -> str:
        return str(manifest_module.data_path(self.directory, plugin_id))

    def discover(self) -> list:
        manifests, problems = manifest_module.discover(
            self.directory, disabled=self.disabled_ids(), data_dir=self.directory
        )
        with self._lock:
            self.problems = problems
            known = {info.id for info in self.infos.values()}
            for item in manifests:
                if item.id in known:
                    self.infos[item.id].manifest = item
                else:
                    self.infos[item.id] = PluginInfo(manifest=item)
            for plugin_id in list(self.infos):
                if plugin_id not in {item.id for item in manifests}:
                    self.unload(plugin_id)
                    self.infos.pop(plugin_id, None)
        return list(self.infos.values())

    def load_all(self) -> list:
        if not self.enabled():
            return []
        for info in self.discover():
            if info.manifest.enabled:
                self.load(info.id)
        return list(self.infos.values())

    def load(self, plugin_id: str) -> PluginInfo:
        info = self.infos.get(plugin_id)
        if info is None:
            raise PluginError(f"没有这个插件：{plugin_id}")
        if info.loaded:
            return info

        manifest = info.manifest
        plugin_api = PluginAPI(manifest, self)
        try:
            if manifest.language == "python":
                hook_table = python_plugin.load_hooks(manifest, plugin_api)
                info.runtime = "in-process"
            else:
                from .js_plugin import JsHooks, JsPluginProcess

                process = JsPluginProcess(manifest, plugin_api, timeout=self.timeout)
                hook_table = JsHooks(process)
                info.runtime = f"node({process.node})"
        except Exception as exc:  # noqa: BLE001 - 插件加载失败只标记它自己
            info.loaded = False
            info.error = f"{type(exc).__name__}: {exc}"
            plugin_api.reset()
            self._report(info, f"加载失败：{info.error}")
            return info

        with self._lock:
            self._apis[plugin_id] = plugin_api
            self._hooks[plugin_id] = hook_table
            info.loaded = True
            info.error = ""

        self._call(plugin_id, api_module.ON_LOAD, None)
        self._invalidate_prompts()
        return info

    def unload(self, plugin_id: str) -> bool:
        # 卸载/重载后不许留下孤儿页面
        self.pages.remove_plugin(plugin_id)

        with self._lock:
            hook_table = self._hooks.pop(plugin_id, None)
            plugin_api = self._apis.pop(plugin_id, None)

        if hook_table is None:
            return False

        self._call(plugin_id, api_module.ON_UNLOAD, None, table=hook_table)
        try:
            hook_table.close()
        except Exception as exc:  # noqa: BLE001
            print(f"[plugin:{plugin_id}] 关闭失败：{exc}")

        if plugin_api is not None:
            plugin_api.reset()

        info = self.infos.get(plugin_id)
        if info is not None:
            info.loaded = False
        self._invalidate_prompts()
        return True

    def reload(self, plugin_id: str | None = None) -> list:
        if plugin_id is None:
            for key in list(self._hooks):
                self.unload(key)
            self._invalidate_prompts()
            return self.load_all()

        self.unload(plugin_id)
        info = self.infos.get(plugin_id)
        if info is not None and info.manifest.enabled:
            self.load(plugin_id)
        return list(self.infos.values())

    def set_enabled(self, plugin_id: str, enabled: bool) -> PluginInfo:
        self.set_disabled(plugin_id, not enabled)
        info = self.infos.get(plugin_id)
        if info is None:
            raise PluginError(f"没有这个插件：{plugin_id}")

        info.manifest.enabled = bool(enabled)
        if enabled:
            self.load(plugin_id)
        else:
            self.unload(plugin_id)
        return info

    def _call(self, plugin_id: str, hook: str, payload=None, table=None):
        with self._lock:
            hook_table = table if table is not None else self._hooks.get(plugin_id)
        info = self.infos.get(plugin_id)

        if hook_table is None or not hook_table.has(hook):
            return None
        if info is not None and not info.manifest.enabled:
            return None

        try:
            value = hook_table.call(hook, payload)
        except Exception as exc:  # noqa: BLE001 - 插件出错只记它自己
            error = f"{type(exc).__name__}: {exc}"
            if info is not None and info.error != error:
                info.error = error
                self._report(info, f"{hook} 出错：{error}")
            return None

        if info is not None:
            info.calls += 1
            if info.error.startswith(("PluginError", "TypeError", "AttributeError", "RuntimeError")):
                info.error = ""
        return value

    def _report(self, info: PluginInfo, message: str):
        print(f"[plugin:{info.id}] {message}")
        try:
            from ... import notify

            notify(f"插件「{info.manifest.name}」{message}", "error", 4000)
        except Exception:  # noqa: BLE001 - 没有界面时就算了
            pass

    def _each(self, hook: str):
        with self._lock:
            items = [(plugin_id, table) for plugin_id, table in self._hooks.items()]
        for plugin_id, table in items:
            yield plugin_id, table

    def chat_text(self, text, role: str = "user"):
        hook = api_module.CHAT_REPLY if role == "assistant" else api_module.CHAT_SEND
        current = text
        for plugin_id, _table in self._each(hook):
            payload = {"text": current, "role": role, "original": text}
            value = self._call(plugin_id, hook, payload)
            if isinstance(value, str) and value.strip():
                current = value
        return current

    def run_command(self, text: str):
        """聊天里 ``/命令 参数``：返回 (是否被插件处理, 结果文本)。"""
        if not text.startswith("/"):
            return False, ""

        head, _sep, rest = text[1:].partition(" ")
        name = head.strip()
        if not name:
            return False, ""

        with self._lock:
            items = list(self._hooks.items())

        for plugin_id, _table in items:
            plugin_api = self._apis.get(plugin_id)
            if plugin_api is None or name not in plugin_api.commands:
                continue
            value = self._call(plugin_id, api_module.COMMAND, {"name": name, "args": rest.strip(), "text": text})
            return True, value if isinstance(value, str) else ""
        return False, ""

    def commands(self) -> dict:
        result = {}
        for plugin_id, plugin_api in self._apis.items():
            info = self.infos.get(plugin_id)
            if info is not None and not info.manifest.enabled:
                continue
            for name, help_text in plugin_api.commands.items():
                result[name] = {"plugin": plugin_id, "help": help_text}
        return result

    def settings_pages(self) -> list:
        """插件注册的设置页信息（设置窗与 SDK 都用它）。"""
        return self.pages.public()

    def settings_action(self, plugin_id: str, page_key: str, action: str, value=None, key: str | None = None):
        """设置页控件动了：值落盘后派发给 on_settings_action。"""
        if key:
            try:
                self.set_setting(plugin_id, key, value)
            except Exception as exc:  # noqa: BLE001 - 存不下来也要通知插件
                print(f"[plugin:{plugin_id}] 设置没存下来：{exc}")

        payload = {"page": page_key, "action": action or key or "", "key": key or "", "value": value}
        result = self._call(plugin_id, api_module.SETTINGS_ACTION, payload)
        if isinstance(result, str) and result.strip():
            self._say(result.strip())
        return result

    @staticmethod
    def _say(text: str):
        try:
            from ... import notify

            notify(text, "info")
        except Exception:  # noqa: BLE001 - 没有界面时就算了
            pass

    def system_prompts(self) -> list:
        if self._prompts_cache:
            return list(self._prompts_cache)

        prompts = []
        for plugin_id, _table in self._each(api_module.SYSTEM_PROMPT):
            value = self._call(plugin_id, api_module.SYSTEM_PROMPT, None)
            if isinstance(value, str) and value.strip():
                prompts.append(value.strip())

        for plugin_id, plugin_api in self._apis.items():
            info = self.infos.get(plugin_id)
            if info is not None and not info.manifest.enabled:
                continue
            prompts.extend(plugin_api.prompts)

        seen = []
        for item in prompts:
            if item not in seen:
                seen.append(item)
        self._prompts_cache = seen
        return list(seen)

    def _invalidate_prompts(self):
        self._prompts_cache = []

    def menu_groups(self) -> list:
        """插件注册的菜单项，按插件分组成一层子菜单。"""
        with self._lock:
            apis = list(self._apis.items())
            tables = list(self._hooks.items())

        items: list[MenuItem] = []
        for plugin_id, plugin_api in apis:
            info = self.infos.get(plugin_id)
            if info is not None and not info.manifest.enabled:
                continue
            items.extend(MenuItem(plugin_id, item["label"], item["action"]) for item in plugin_api.menu_items)

        for plugin_id, _table in tables:
            value = self._call(plugin_id, api_module.MENU, None)
            for item in value or []:
                if isinstance(item, dict) and item.get("label"):
                    items.append(MenuItem(plugin_id, str(item["label"]), str(item.get("action") or item["label"])))

        groups: dict[str, MenuGroup] = {}
        for item in items:
            group = groups.get(item.plugin)
            if group is None:
                group = MenuGroup(item.plugin, self.menu_title(item.plugin), [], self.menu_icon(item.plugin))
                groups[item.plugin] = group
            group.items.append(item)
        return list(groups.values())

    def menu_items(self) -> list:
        """扁平的菜单项列表（SDK/探针/测试还在用）。"""
        return [item for group in self.menu_groups() for item in group.items]

    def menu_title(self, plugin_id: str) -> str:
        info = self.infos.get(plugin_id)
        if info is None:
            return plugin_id
        return info.manifest.menu_title

    def menu_icon(self, plugin_id: str):
        """插件图标（QPixmap）；没装 Qt / 解码失败都返回 None，菜单退化成纯文字。"""
        info = self.infos.get(plugin_id)
        if info is None:
            return None

        try:
            from .. import icons as icons_module

            return icons_module.plugin_pixmap(info.manifest, 22)
        except Exception as exc:  # noqa: BLE001 - 图标只是装饰，画不出来不该影响菜单
            print(f"[plugin:{plugin_id}] 图标加载失败：{exc}")
            return None

    def plugin_icon(self, plugin_id: str, size: int = 64):
        """插件图标（QIcon）；设置页和别的地方共用同一份缓存。"""
        info = self.infos.get(plugin_id)
        if info is None:
            return None

        try:
            from .. import icons as icons_module

            return icons_module.plugin_icon(info.manifest, size)
        except Exception as exc:  # noqa: BLE001
            print(f"[plugin:{plugin_id}] 图标加载失败：{exc}")
            return None

    def trigger_menu(self, action: str) -> str:
        """菜单项被点击：转成插件的 on_command（action 当命令名）。"""
        for plugin_id, plugin_api in self._apis.items():
            for item in plugin_api.menu_items:
                if item["action"] == action:
                    value = self._call(plugin_id, api_module.COMMAND, {"name": action, "args": "", "text": ""})
                    return value if isinstance(value, str) else ""
        return ""

    def emit_event(self, name: str, data=None):
        for plugin_id, _table in self._each(api_module.EVENT):
            self._call(plugin_id, api_module.EVENT, {"name": name, "data": data})

    def send_to_chat(self, text: str, role: str = "assistant"):
        window = None
        try:
            from ... import SharingData

            window = SharingData.chat_window
        except Exception:  # noqa: BLE001
            window = None

        chat = getattr(window, "chat", None)
        if chat is None:
            from ... import notify

            return notify(text, "info")

        def push():
            if role == "user":
                chat.add_user_msg(text)
            else:
                chat.add_assistant_msg(text)

        self.run_on_ui(push)
        return True

    def play_motion(self, name: str, index: int = 0):
        from ... import SharingData

        window = SharingData.setting_window
        if window is None:
            return False
        window.live2d_mot_signal.emit([name, index])
        return True

    def play_expression(self, name: str):
        from ... import SharingData

        window = SharingData.setting_window
        if window is None:
            return False
        window.live2d_exp_signal.emit([name])
        return True

    @staticmethod
    def motions() -> list:
        from ... import SharingData

        return list(getattr(SharingData, "motions", None) or [])

    @staticmethod
    def expressions() -> list:
        from ... import SharingData

        return list(getattr(SharingData, "expressions", None) or [])

    def run_on_ui(self, func, *args, **kwargs):
        if threading.current_thread() is threading.main_thread():
            return func(*args, **kwargs)

        from PySide6.QtCore import QCoreApplication, QObject, QMetaObject, Qt, Slot

        if QCoreApplication.instance() is None:
            return func(*args, **kwargs)

        class _Holder(QObject):
            @Slot()
            def run(self):
                try:
                    func(*args, **kwargs)
                except Exception:  # noqa: BLE001 - 插件回调出错不该带崩事件循环
                    traceback.print_exc()

        holder = _Holder()
        _KEEP_ALIVE.append(holder)
        QMetaObject.invokeMethod(holder, "run", Qt.ConnectionType.QueuedConnection)
        return None

    def status(self) -> dict:
        return {
            "enable": self.enabled(),
            "directory": self.directory,
            "plugins": [info.public() for info in self.infos.values()],
            "problems": list(self.problems),
            "commands": self.commands(),
            "pages": self.settings_pages(),
        }


def format_traceback(exc: BaseException) -> str:
    return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))


manager = PluginManager()

__all__ = [
    "DEFAULT_DIR",
    "DEFAULT_TIMEOUT",
    "ManifestError",
    "MenuGroup",
    "MenuItem",
    "PluginInfo",
    "PluginManager",
    "format_traceback",
    "manager",
]
