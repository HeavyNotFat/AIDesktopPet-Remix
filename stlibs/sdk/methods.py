from __future__ import annotations

import time

from .base import SDKMethodError

# 方法名 -> 说明（``list_methods`` 直接用它生成文档）
METHOD_HELP: dict[str, str] = {
    "ping": "探活：返回 pong 与服务器时间",
    "version": "协议/程序版本",
    "list_methods": "列出所有可调方法与说明",
    "get_status": "宿主概况：主题、模型、插件数、窗口状态、运行时长",
    "emit_event": "让服务器给订阅者推一条自定义事件（方便调试）",

    "notify": "弹一条界面提示：notify(text, level='info', timeout=2600)",
    "play_live2d_motion": "播动作：play_live2d_motion(name, index=0)",
    "play_live2d_expression": "切表情：play_live2d_expression(name)",
    "get_live2d_motion": "列出可用动作",
    "get_live2d_expression": "列出可用表情",
    "get_appearance": "读当前外观：尺寸/透明度/旋转",
    "set_appearance": "改外观：set_appearance(size=?, opacity=?, rotate=?)",

    "send_to_chat": "往聊天窗塞一条消息（不调模型）：send_to_chat(text, role='assistant')",
    "get_chat_history": "读当前聊天窗里的消息",
    "clear_chat": "清空聊天窗的消息",
    "ask": "真的问一次模型并等回答：ask(question, model=None, timeout=None)",

    "get_config": "读配置（整个或某个键）",
    "set_config": "改配置并落盘：set_config(key, value)",
    "list_plugins": "列出插件与状态",
    "trigger_plugin_action": "触发插件的菜单动作：trigger_plugin_action(action)",
    "run_plugin_command": "跑一条插件命令：run_plugin_command('/统计')",

    "memory_stats": "短期/长期记忆概况",
    "memory_recall": "按关键词召回长期记忆：memory_recall(query, top_k=3)",
    "memory_clear": "清空长期记忆（scope 可选）",
}


class HostMethods:
    """宿主能力的实现。"""
    def __init__(self, server=None, started_at: float | None = None):
        self.server = server
        self.started_at = started_at or time.time()

    @staticmethod
    def ping():
        return {"pong": True, "time": time.time()}

    @staticmethod
    def version():
        from .. import __name__ as package

        return {
            "protocol": 2,
            "package": package,
            "python": _python_version(),
        }

    @staticmethod
    def list_methods():
        return [{"name": name, "help": text} for name, text in sorted(METHOD_HELP.items())]

    def get_status(self):
        from .. import Config, SharingData

        plugins = []
        try:
            from .. import plugin_manager

            status = plugin_manager().status()
            plugins = status.get("plugins") or []
        except Exception:  # noqa: BLE001 - 插件系统坏了不影响 SDK 概况
            pass

        return {
            "uptime": round(time.time() - self.started_at, 3),
            "theme": Config.theme,
            "assistant": Config.name,
            "live2d_model": Config.model_live2d,
            "static_model": Config.static_model,
            "chat_open": _visible(SharingData.chat_window),
            "settings_open": _visible(SharingData.setting_window),
            "plugins": {
                "total": len(plugins),
                "loaded": sum(1 for item in plugins if item.get("loaded")),
            },
            "methods": len(METHOD_HELP),
        }

    def emit_event(self, name, data=None):
        if self.server is None:
            raise SDKMethodError("这个服务器没有事件通道")
        count = self.server.emit(str(name), data)
        return {"name": str(name), "subscribers": count}

    @staticmethod
    def notify(text, level="info", timeout=2600):
        from .. import notify

        notify(str(text), str(level or "info"), int(timeout or 2600))
        return {"notified": str(text)}

    @staticmethod
    def play_live2d_motion(name, index=0):
        window = _window("设置窗口")
        window.live2d_mot_signal.emit([str(name), int(index)])
        return {"played": str(name), "index": int(index)}

    @staticmethod
    def play_live2d_expression(name):
        window = _window("设置窗口")
        window.live2d_exp_signal.emit([str(name)])
        return {"played": str(name)}

    @staticmethod
    def get_live2d_motion():
        from .. import SharingData

        return list(getattr(SharingData, "motions", None) or []) or "No Motion Data"

    @staticmethod
    def get_live2d_expression():
        from .. import SharingData

        return list(getattr(SharingData, "expressions", None) or []) or "No Expression Data"

    @staticmethod
    def get_appearance():
        from .. import Config

        return {"size": Config.size, "opacity": Config.opacity, "rotate": Config.rotate}

    @staticmethod
    def set_appearance(size=None, opacity=None, rotate=None):
        from .. import Config, ConfigLoader

        changed = {}
        for key, value in (("size", size), ("opacity", opacity), ("rotate", rotate)):
            if value is None:
                continue
            try:
                Config[key] = int(value)
            except (TypeError, ValueError) as exc:
                raise SDKMethodError(f"{key} 需要整数：{value!r}") from exc
            changed[key] = Config[key]

        if changed:
            ConfigLoader.save_config()
            _apply_appearance(changed)

        return changed

    @staticmethod
    def send_to_chat(text, role="assistant"):
        from .. import plugin_manager

        plugin_manager().send_to_chat(str(text), str(role or "assistant"))
        return {"sent": str(text), "role": str(role or "assistant")}

    @staticmethod
    def get_chat_history():
        from .. import SharingData

        chat = getattr(SharingData.chat_window, "chat", None)
        if chat is None:
            return []

        history = []
        for bubble in getattr(chat, "bubbles", []):
            try:
                history.append({
                    "role": "user" if bubble.is_user else "assistant",
                    "text": bubble.text_label.text(),
                })
            except AttributeError:
                continue
        return history

    @staticmethod
    def clear_chat():
        from .. import SharingData

        chat = getattr(SharingData.chat_window, "chat", None)
        if chat is None:
            raise SDKMethodError("聊天窗还没打开过")
        if hasattr(chat, "clear_messages"):
            chat.clear_messages()
        else:
            for bubble in list(getattr(chat, "bubbles", [])):
                bubble.setParent(None)
            chat.bubbles = []
        return {"cleared": True}

    @staticmethod
    def ask(question, model=None, timeout=None):
        """跑一次真实模型，属于慢方法（客户端记得把超时调大）。"""
        from .. import get_model_lists
        from ..ai import build_llm, chat_prompt

        question = str(question or "").strip()
        if not question:
            raise SDKMethodError("问题不能为空")

        target = str(model or "").strip()
        if not target:
            models = get_model_lists()
            if not models:
                raise SDKMethodError("没有可用的本地模型（先 ollama pull 一个）")
            target = models[0]

        llm = build_llm(target, "", coop=False)
        started = time.time()
        answer = "".join(
            chunk for chunk in chat_prompt(llm, question) if isinstance(chunk, str)
        ).strip()
        return {
            "model": target,
            "answer": answer,
            "seconds": round(time.time() - started, 3),
        }

    @staticmethod
    def get_config(key=None):
        from .. import Config

        fields = (
            "name", "model_live2d", "static_model", "opacity", "size", "rotate", "theme",
            "models", "memory", "rag", "mcp", "coop", "skills", "plugins",
        )
        if key:
            if key not in fields:
                raise SDKMethodError(f"没有这个配置项：{key}（可选 {', '.join(fields)}）")
            return {key: getattr(Config, key, None)}
        return {name: getattr(Config, name, None) for name in fields}

    @staticmethod
    def set_config(key, value):
        from .. import Config, ConfigLoader

        allowed = {"name", "model_live2d", "static_model", "opacity", "size", "rotate", "theme",
                   "memory", "rag", "mcp", "coop", "skills", "plugins"}
        if key not in allowed:
            raise SDKMethodError(f"这个配置项不允许外部改：{key}（可选 {', '.join(sorted(allowed))}）")

        Config[key] = value
        ConfigLoader.save_config()
        return {key: value}

    @staticmethod
    def list_plugins():
        from .. import plugin_manager

        manager = plugin_manager()
        manager.discover()
        return manager.status()

    @staticmethod
    def trigger_plugin_action(action):
        from .. import plugin_manager

        result = plugin_manager().trigger_menu(str(action))
        return {"action": str(action), "result": result}

    @staticmethod
    def run_plugin_command(text):
        from .. import run_plugin_command

        handled, result = run_plugin_command(str(text))
        return {"handled": bool(handled), "result": result}

    @staticmethod
    def memory_stats():
        from .. import SharingData

        stats = {"instances": len(SharingData.llm_instances), "long_term": None}
        for llm in list(SharingData.llm_instances.values()):
            memory = getattr(llm, "lt_memory", None)
            if memory is not None:
                stats["long_term"] = memory.stats()
                break
        return stats

    @staticmethod
    def memory_recall(query, top_k=3):
        from .. import SharingData

        for llm in list(SharingData.llm_instances.values()):
            memory = getattr(llm, "lt_memory", None)
            if memory is not None:
                return memory.recall(str(query), top_k=int(top_k or 3), scope=None)
        return []

    @staticmethod
    def memory_clear(scope=None):
        from .. import SharingData

        removed = 0
        for llm in list(SharingData.llm_instances.values()):
            memory = getattr(llm, "lt_memory", None)
            if memory is not None:
                removed += memory.clear(scope)
        return {"removed": removed}


def _python_version() -> str:
    import platform

    return platform.python_version()


def _visible(window) -> bool:
    if window is None:
        return False
    try:
        return bool(window.isVisible())
    except Exception:  # noqa: BLE001
        return False


def _window(label: str):
    from .. import SharingData

    window = SharingData.setting_window
    if window is None:
        raise SDKMethodError(f"{label}还没创建（先启动界面）")
    return window


def _apply_appearance(changed: dict):
    """改完配置顺手作用到桌宠上（拿不到窗口就算了，下次启动会读配置）。"""
    from .. import SharingData

    ui = SharingData.mainloop_ui
    if ui is None:
        return
    try:
        if "size" in changed and hasattr(ui, "resize"):
            ui.resize(int(ui.width()), int(ui.height()))
        if "opacity" in changed and hasattr(ui, "setCanvasOpacity"):
            ui.setCanvasOpacity(changed["opacity"] / 100 if changed["opacity"] > 1 else changed["opacity"])
        if "rotate" in changed and hasattr(ui, "setRotationAngle"):
            ui.setRotationAngle(changed["rotate"])
    except Exception as exc:  # noqa: BLE001 - 应用失败不影响配置已保存
        print(f"[sdk] 应用外观失败：{exc}")


__all__ = ["METHOD_HELP", "HostMethods"]
