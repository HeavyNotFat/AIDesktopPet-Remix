from __future__ import annotations

from cultivation_model import PetState

STATE_KEY = "state"

_state: PetState | None = None
_window = None
_timer = None


def _get_state(api) -> PetState:
    global _state
    if _state is None:
        _state = PetState(storage=_Storage(api))
    return _state


class _Storage:
    """把插件的 storage 包装成 ``get/set`` 两个方法给 PetState 用。"""
    def __init__(self, api):
        self.api = api

    def get(self, key, default=None):
        return self.api.storage_get(key, default)

    def set(self, key, value):
        return self.api.storage_set(key, value)


def _notify_gains(api, events, extra: str = ""):
    if extra:
        api.notify(extra, "success", 2600)
    for event in events:
        api.notify(event, "success", 3200)


def _shop_lines(state: PetState) -> str:
    return "、".join(f"{name}（{food.get('price')} 金币）" for name, food in state.foods.items())


def on_load(api):
    state = _get_state(api)
    api.log(f"养成系统就绪：{state.status_text()}")

    api.add_menu_item("养成系统：打开面板", "cultivation_system:open")
    api.add_menu_item("养成系统：状态", "cultivation_system:status")
    api.register_command("养成", "打开养成面板")
    api.register_command("状态", "看桌宠当前状态")
    api.register_command("喂食", "喂一份背包里的食物：/喂食 汉堡")
    api.register_command("买", "买一份食物：/买 可乐")

    api.run_on_ui(_start_timer, api)


def on_unload(api):
    global _window, _timer
    if _timer is not None:
        try:
            _timer.stop()
        except RuntimeError:
            pass
        _timer = None
    if _window is not None:
        try:
            _window.close()
        except RuntimeError:
            pass
        _window = None
    api.log("养成系统已停用")


def _start_timer(api):
    """在 UI 线程里起一个定时器（插件线程不能直接创建 QTimer）。"""
    global _timer

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    if QApplication.instance() is None:
        api.log("没有 QApplication（无界面环境），饥饿定时器跳过")
        return

    if _timer is not None:
        return

    _timer = QTimer()
    _timer.setInterval(5000)
    _timer.timeout.connect(lambda: _tick(api))
    _timer.start()
    api.log("饥饿定时器已启动（每 5 秒检查一次）")


def _tick(api):
    state = _state
    if state is None:
        return

    result = state.tick()
    if not result:
        return

    if result.get("starving"):
        api.notify("我饿了！喂我点吃的吧～", "warning", 4000)
    if _window is not None and _window.isVisible():
        _window.refresh()


def _open_window(api):
    global _window

    from PySide6.QtWidgets import QApplication

    # 没有界面环境时创建 QWidget 会直接把进程带崩，这里先说清楚
    if QApplication.instance() is None:
        return f"没有界面环境，先看状态吧：{_get_state(api).status_text()}"

    from cultivation_window import CultivationWindow

    state = _get_state(api)
    if _window is None:
        _window = CultivationWindow(api, state, on_action=lambda action, payload=None: _action(api, action, payload))
    _window.show_panel()
    return "养成面板已打开"


def _action(api, action: str, payload=None):
    state = _get_state(api)

    if action == "close":
        if _window is not None:
            _window.hide()
        return ""

    if action == "refresh":
        if _window is not None:
            _window.refresh()
        return ""

    if action == "click":
        cap = int(api.get_setting("click_coin", 5) or 5)
        _coin, _favor, message, events = state.click_reward(max_coin=cap)
        _notify_gains(api, events, message)

    elif action == "buy":
        ok, message = state.buy(str(payload))
        api.notify(message, "success" if ok else "error", 3000)

    elif action == "eat":
        ok, message, events = state.eat(str(payload))
        api.notify(message, "success" if ok else "warning", 3200)
        _notify_gains(api, events, "")

    if _window is not None:
        _window.refresh()
    return ""


def on_command(api, ctx):
    state = _get_state(api)
    name = str(ctx.get("name") or "")
    args = str(ctx.get("args") or "").strip()

    if name in ("cultivation_system:open", "养成"):
        return _open_window(api)

    if name in ("cultivation_system:status", "状态"):
        return (
            f"{state.status_text()}\n背包：{state.bag() or '空'}\n"
            f"商店：{_shop_lines(state)}"
        )

    if name in ("喂食", "eat"):
        food = args
        if not food:
            return f"要喂什么？背包里有：{'、'.join(state.bag()) or '（空的）'}"
        ok, message, events = state.eat(food)
        if _window is not None:
            _window.refresh()
        return message + ("\n" + "\n".join(events) if events else "")

    if name in ("买", "buy"):
        food = args
        if not food:
            return f"要买什么？商店里有：{_shop_lines(state)}"
        ok, message = state.buy(food)
        if _window is not None:
            _window.refresh()
        return message

    return None


def on_chat_reply(api, ctx):
    state = _get_state(api)
    exp, favor, events = state.reply_reward(ctx.get("text", ""))
    if events:
        _notify_gains(api, events, "")
    if _window is not None and _window.isVisible():
        _window.refresh()
    api.log(f"聊天奖励：经验 +{exp}，好感 +{favor}")
    return None


def on_event(api, ctx):
    if not ctx or ctx.get("name") != "pet_click":
        return

    state = _get_state(api)
    cap = int(api.get_setting("click_coin", 5) or 5)
    _coin, _favor, message, events = state.click_reward(max_coin=cap)
    api.notify(message, "success", 1200)
    _notify_gains(api, events)
    if _window is not None and _window.isVisible():
        _window.refresh()


def on_system_prompt(api):
    if not api.get_setting("mood_prompt", True):
        return None
    return _state.mood_prompt() if _state is not None else None
