from __future__ import annotations

from gacha_model import RARITIES, RARITY_COLOR, RARITY_WEIGHT, GachaState

from stlibs.plugins.api import COMMAND, EVENT, ON_LOAD, ON_UNLOAD, SYSTEM_PROMPT

MENU_OPEN = "lucky_pet:open"
MENU_PULL = "lucky_pet:pull"
MENU_CODEX = "lucky_pet:codex"

_state: GachaState | None = None
_window = None


def _storage(api):
    """插件存储的读写口；直接塞进 api 的几个方法就够了。"""

    class Storage:
        def get(self, key, default=None):
            return api.storage_get(key, default)

        def __setitem__(self, key, value):
            api.storage_set(key, value)

    return Storage()


def _get_state(api) -> GachaState:
    global _state
    if _state is None:
        start_coin = int(api.get_setting("start_coin", 60) or 60)
        _state = GachaState(storage=_storage(api), start_coin=start_coin)
    return _state


def _open_window(api):
    global _window
    state = _get_state(api)

    def start():
        from gacha_window import GachaWindow

        global _window
        if _window is None:
            _window = GachaWindow(api, state, on_action=lambda action, payload=None: _handle(api, action))
        _window.show_panel()

    api.run_on_ui(start)
    return state.stats_text()


def _handle(api, action: str):
    """面板按钮和命令共用的入口。"""
    state = _get_state(api)

    if action == "close":
        if _window is not None:
            _window.hide()
        return ""

    if action in ("pull", "ten"):
        times = 10 if action == "ten" else 1
        ok, message, results = state.pull(times)
        if _window is not None:
            _window.show_results(results, message)
        _tell(api, ok, message, results)
        return message

    if action == "daily":
        claimed, coins = state.daily()
        message = f"签到成功，拿到 {coins} 金币" if claimed else "今天已经签到过啦，明天再来"
        if _window is not None:
            _window.set_message(message, "#4dabf7" if claimed else "#ffd166")
            _window.refresh()
        api.notify(message, "success" if claimed else "info", 2600)
        return message

    if action == "exchange":
        ok, message, item = state.exchange()
        if _window is not None:
            _window.show_results([item] if item else [], message)
        api.notify(message, "success" if ok else "warning", 3200)
        return message

    if action == "comment":
        results = (_window.last_results if _window is not None else None) or state.last_results
        api.send_to_chat(state.comment_prompt(results))
        return "让桌宠点评一下这次的手气～"

    if action == "codex":
        lines = state.codex()
        if _window is not None:
            _window.show_panel()
        return state.stats_text() + "\n" + "\n".join(lines)

    return ""


def _tell(api, ok: bool, message: str, results: list):
    if not ok:
        api.notify(message, "warning", 3200)
        return
    best = max(results, key=lambda item: RARITIES.index(item["rarity"])) if results else None
    level = "success" if best and best["rarity"] in ("SSR", "UR") else "info"
    api.notify(message, level, 3600)


def on_load(api):
    state = _get_state(api)
    api.log(f"扭蛋机就绪：{state.stats_text()}")
    api.add_menu_item("扭蛋机：打开面板", MENU_OPEN)
    api.add_menu_item("扭蛋机：来一发（10 金币）", MENU_PULL)
    api.add_menu_item("扭蛋机：看图鉴", MENU_CODEX)
    api.register_command("抽卡", "单抽一次（10 金币）")
    api.register_command("十连", "连抽十次（90 金币，有保底）")
    api.register_command("签到", "每日签到领金币")
    api.register_command("图鉴", "看收藏品收集进度")
    api.register_command("扭蛋", "打开扭蛋机面板")
    api.notify("扭蛋机装好了：发「/抽卡」试试手气", "success", 3200)


def on_unload(api):
    global _state, _window
    if _window is not None:
        _window.hide()
        _window = None
    _state = None
    api.log("扭蛋机已停用")


def on_command(api, ctx):
    name = str(ctx.get("name") or "")
    if name in (MENU_OPEN, "扭蛋", "open"):
        return _open_window(api)
    if name in (MENU_PULL, "抽卡", "pull"):
        return _handle(api, "pull")
    if name in ("十连", "ten"):
        return _handle(api, "ten")
    if name in ("签到", "daily"):
        return _handle(api, "daily")
    if name in (MENU_CODEX, "图鉴", "codex"):
        return _handle(api, "codex")
    if name in ("兑换", "exchange"):
        return _handle(api, "exchange")
    return ""


def on_event(api, ctx):
    """摸桌宠有小概率捡到星辉——抽卡货币的唯一白嫖来源。"""
    if not ctx or ctx.get("name") != "pet_click":
        return

    state = _get_state(api)
    chance = int(api.get_setting("click_luck", 8) or 8)
    import random

    if random.randint(1, 100) > chance:
        return
    state.add_coins(5)
    api.notify("桌宠抖出一枚金币！+5", "success", 1600)
    if _window is not None and _window.isVisible():
        _window.refresh()


def on_system_prompt(api, ctx):
    state = _get_state(api)
    weights = "、".join(f"{rarity} {RARITY_WEIGHT[rarity]}%" for rarity in RARITIES)
    return (
        "你桌上有一台扭蛋机，用户可以用 /抽卡（10 金币）、/十连（90 金币）、/签到（每日 30 金币）来抽收藏品，"
        f"稀有度概率是 {weights}，第 10 抽保底 SR 以上、第 80 抽保底 SSR 以上，重复的会换成星辉。"
        f"当前：{state.stats_text()}。"
        "用户聊到抽卡、手气、收集品时，用你自己的语气接话；不要编造他没抽到过的东西。"
    )


__all__ = ["MENU_CODEX", "MENU_OPEN", "MENU_PULL", "ON_COMMAND", "ON_EVENT", "ON_LOAD", "ON_SYSTEM_PROMPT",
           "ON_UNLOAD", "on_command", "on_event", "on_load", "on_system_prompt", "on_unload"]
