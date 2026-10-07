from __future__ import annotations

import json
import os
import threading
from pathlib import Path

# hook 名：插件按需实现，宿主按名派发
ON_LOAD = "on_load"
ON_UNLOAD = "on_unload"
CHAT_SEND = "on_chat_send"
CHAT_REPLY = "on_chat_reply"
SYSTEM_PROMPT = "on_system_prompt"
MENU = "on_menu"
COMMAND = "on_command"
EVENT = "on_event"

ALL_HOOKS = (ON_LOAD, ON_UNLOAD, CHAT_SEND, CHAT_REPLY, SYSTEM_PROMPT, MENU, COMMAND, EVENT)

HOOK_HELP = {
    ON_LOAD: "插件加载后调用一次（注册菜单/命令/系统提示）",
    ON_UNLOAD: "插件卸载前调用一次（清理资源）",
    CHAT_SEND: "发送前改用户输入：返回字符串就替换，返回空/None 不改",
    CHAT_REPLY: "收到回复后改内容：返回字符串就替换，返回空/None 不改",
    SYSTEM_PROMPT: "追加一段系统提示词（增强插件常用）",
    MENU: "返回菜单项列表 [{label, action}]，会挂到桌宠右键菜单",
    COMMAND: "聊天里输入 /命令 时触发（api.register_command 注册）",
    EVENT: "宿主事件：theme_changed / chat_opened / plugin_loaded 等",
}


class PluginError(RuntimeError):
    """插件自身出错（加载失败、hook 抛异常、超时）。"""

def _jsonable(value):
    try:
        json.dumps(value)
    except (TypeError, ValueError):
        return str(value)
    return value


class PluginAPI:
    """一个插件一个实例：所有副作用都记在它身上，方便卸载时清理。"""
    def __init__(self, manifest, manager):
        self._manifest = manifest
        self._manager = manager
        self._lock = threading.RLock()
        self.menu_items: list = []
        self.commands: dict = {}
        self.prompts: list = []
        self.data_file = manager.data_file(manifest.id)
        self._cache = None

    @property
    def id(self) -> str:
        return self._manifest.id

    @property
    def name(self) -> str:
        return self._manifest.name

    @property
    def version(self) -> str:
        return self._manifest.version

    @property
    def path(self) -> str:
        return str(self._manifest.path)

    def __repr__(self):
        return f"<PluginAPI {self.id}>"

    def log(self, message):
        print(f"[plugin:{self.id}] {message}")

    def notify(self, text, level="info", timeout=2600):
        from .. import notify

        return notify(f"[{self.name}] {text}", level, timeout)

    def get_setting(self, key, default=None):
        """清单里声明的设置项（值存在配置里，面板上可以改）。"""
        settings = self._manager.settings_for(self.id)
        if key in settings:
            return settings[key]
        for item in self._manifest.settings:
            if item["key"] == key:
                return item.get("default", default)
        return default

    def set_setting(self, key, value):
        return self._manager.set_setting(self.id, key, value)

    def settings(self) -> dict:
        result = {item["key"]: item.get("default") for item in self._manifest.settings}
        result.update(self._manager.settings_for(self.id))
        return result

    def _load_data(self) -> dict:
        if self._cache is not None:
            return self._cache

        try:
            raw = json.loads(Path(self.data_file).read_text(encoding="utf-8"))
            self._cache = raw if isinstance(raw, dict) else {}
        except (OSError, ValueError):
            self._cache = {}
        return self._cache

    def storage_get(self, key, default=None):
        with self._lock:
            return self._load_data().get(key, default)

    def storage_set(self, key, value):
        with self._lock:
            data = dict(self._load_data())
            data[key] = _jsonable(value)
            self._cache = data

            target = Path(self.data_file)
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, target)
        return value

    def storage_all(self) -> dict:
        with self._lock:
            return dict(self._load_data())

    def add_menu_item(self, label, action=None):
        """UI Hook：往桌宠右键菜单加一项；点了会回调插件的 on_command(action)。"""
        action = action or f"plugin:{self.id}:{len(self.menu_items)}"
        item = {"plugin": self.id, "label": str(label), "action": str(action)}
        with self._lock:
            self.menu_items = [entry for entry in self.menu_items if entry["action"] != item["action"]]
            self.menu_items.append(item)
        return item["action"]

    def register_command(self, name, help_text=""):
        """增强：聊天里 /name 触发插件的 on_command。"""
        name = str(name or "").strip().lstrip("/")
        if not name:
            raise PluginError("命令名不能为空")
        with self._lock:
            self.commands[name] = str(help_text or "")
        return name

    def append_system_prompt(self, text):
        """增强：把这段文本追加到系统提示词（本地与网页聊天都会带上）。"""
        text = str(text or "").strip()
        if not text:
            return ""
        with self._lock:
            if text not in self.prompts:
                self.prompts.append(text)
        return text

    def clear_system_prompt(self):
        with self._lock:
            self.prompts = []

    def send_to_chat(self, text, role="assistant"):
        """UI Hook：直接往聊天窗塞一条消息（不调模型）。"""
        return self._manager.send_to_chat(str(text), str(role or "assistant"))

    def run_on_ui(self, func, *args, **kwargs):
        """Python 插件要在主线程碰 Qt 时用它。"""
        return self._manager.run_on_ui(func, *args, **kwargs)

    def play_motion(self, name, index=0):
        """UI Hook：播 Live2D 动作（和 UDP SDK 里那个是同一条路）。"""
        return self._manager.play_motion(str(name), int(index))

    def play_expression(self, name):
        return self._manager.play_expression(str(name))

    def motions(self) -> list:
        return self._manager.motions()

    def expressions(self) -> list:
        return self._manager.expressions()

    def call(self, method, *args, **kwargs):
        """给 JavaScript 桥用：按名字调上面这些方法。"""
        handler = getattr(self, method, None)
        if handler is None or method.startswith("_") or not callable(handler):
            raise PluginError(f"没有这个 API：{method}")
        return handler(*args, **kwargs)

    def reset(self):
        """卸载时清掉注册过的东西。"""
        with self._lock:
            self.menu_items = []
            self.commands = {}
            self.prompts = []


__all__ = [
    "ALL_HOOKS",
    "CHAT_REPLY",
    "CHAT_SEND",
    "COMMAND",
    "EVENT",
    "HOOK_HELP",
    "MENU",
    "ON_LOAD",
    "ON_UNLOAD",
    "PluginAPI",
    "PluginError",
    "SYSTEM_PROMPT",
]
