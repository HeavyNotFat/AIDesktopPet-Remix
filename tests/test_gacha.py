"""桌宠扭蛋机：概率/保底/图鉴的逻辑，以及 hook 接线。"""

import importlib
import random
import sys
from pathlib import Path

import pytest

PLUGIN_DIR = Path(__file__).resolve().parents[1] / "plugins" / "lucky_pet"
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

from gacha_model import (  # noqa: E402
    DAILY_COIN, EXCHANGE_SHARDS, PITY_SR, PITY_SSR, SINGLE_COST, TEN_COST, GachaState, load_items,
)


class FakeStorage(dict):
    def get(self, key, default=None):
        return dict.get(self, key, default)


def make_state(coins=200, seed=7, **kwargs):
    return GachaState(storage=FakeStorage(), items=load_items(), rng=random.Random(seed),
                      start_coin=coins, **kwargs)


def test_items_pool_matches_rarities():
    items = load_items()

    assert set(items) == {"N", "R", "SR", "SSR", "UR"}
    assert all(pool for pool in items.values()), "每档都要有东西，不然保底会抽空"
    ids = [item["id"] for pool in items.values() for item in pool]
    assert len(ids) == len(set(ids)), "收藏品 id 不能重复"


def test_pull_costs_coins_and_tracks_collection():
    state = make_state(coins=200)

    ok, message, results = state.pull(1)

    assert ok and len(results) == 1
    assert state.coins == 200 - SINGLE_COST
    assert state.data["total"] == 1
    assert state.data["collection"][results[0]["id"]] == 1
    assert results[0]["new"] is True
    assert results[0]["rarity"] in {"N", "R", "SR", "SSR", "UR"}
    assert results[0]["name"] in message or results[0]["rarity"] in message


def test_ten_pull_is_cheaper_and_ten_items():
    state = make_state(coins=200)

    ok, _message, results = state.pull(10)

    assert ok and len(results) == 10
    assert state.coins == 200 - TEN_COST


def test_pull_without_coins_is_refused():
    state = make_state(coins=5)

    ok, message, results = state.pull(1)

    assert ok is False and results == []
    assert "金币不够" in message
    assert state.coins == 5, "失败不能扣钱"


def test_sr_pity_triggers_on_tenth_pull():
    state = make_state(coins=500)
    rarities = [state.pull(1)[2][0]["rarity"] for _ in range(PITY_SR)]

    assert rarities[-1] in {"SR", "SSR", "UR"}, f"第 {PITY_SR} 抽必须保底：{rarities}"
    assert state.data["pity_sr"] == 0, "出保底后计数清零"


def test_ssr_pity_triggers_on_eightieth_pull():
    state = make_state(coins=2000)
    hits = []
    for index in range(PITY_SSR):
        item = state.pull(1)[2][0]
        hits.append(item["rarity"])
        if item["rarity"] in ("SSR", "UR"):
            break

    assert hits[-1] in {"SSR", "UR"}, f"第 {PITY_SSR} 抽必须出 SSR 以上：{hits}"
    assert state.data["pity_ssr"] == 0
    assert state.pity_left == PITY_SSR


def test_duplicates_become_shards():
    state = make_state(coins=2000)
    shards = 0
    for _ in range(200):
        _ok, _message, results = state.pull(1)
        for item in results:
            if not item["new"]:
                shards += item["shards"]

    assert state.shards == shards > 0, "重复的应该累计成星辉"


def test_daily_bonus_only_once_per_day():
    state = make_state(coins=10)

    claimed, coins = state.daily("2026-01-01")
    assert claimed and coins == DAILY_COIN
    assert state.coins == 10 + DAILY_COIN

    again, _coins = state.daily("2026-01-01")
    assert again is False
    assert state.coins == 10 + DAILY_COIN, "同一天不能重复领"

    tomorrow, _coins = state.daily("2026-01-02")
    assert tomorrow is True


def test_exchange_ur_for_shards():
    state = make_state(coins=10)
    state.data["shards"] = EXCHANGE_SHARDS

    ok, message, item = state.exchange()

    assert ok and item["rarity"] == "UR"
    assert state.shards == 0
    assert "UR" in message
    assert state.data["collection"][item["id"]] == 1

    state.data["shards"] = EXCHANGE_SHARDS - 1
    refused, message, item = state.exchange()
    assert refused is False and item is None
    assert "星辉不够" in message


def test_state_persists_through_storage():
    storage = FakeStorage()
    first = GachaState(storage=storage, items=load_items(), rng=random.Random(1), start_coin=100)
    first.pull(1)
    first.daily("2026-02-02")

    second = GachaState(storage=storage, items=load_items(), rng=random.Random(1), start_coin=999)

    assert second.coins == first.coins, "重开不能重置金币"
    assert second.data["total"] == 1
    assert second.data["last_daily"] == "2026-02-02"
    assert second.data["collection"] == first.data["collection"]


def test_codex_lists_every_item():
    state = make_state()
    lines = state.codex()

    assert len(lines) == 5 and lines[0].startswith("UR"), "从高稀有度往下列"
    assert all("未收集" in line for line in lines)


class FakeAPI:
    """照着 stlibs.plugins.api.PluginAPI 里用到的那几个方法做的假宿主。"""

    def __init__(self, settings=None):
        self.id = "lucky_pet"
        self.name = "桌宠扭蛋机"
        self.data = {}
        self.menus = []
        self.commands = []
        self.notes = []
        self.chat = []
        self.settings = settings or {}

    def log(self, message):
        pass

    def notify(self, text, level="info", timeout=3000):
        self.notes.append((level, text))

    def get_setting(self, key, default=None):
        return self.settings.get(key, default)

    def set_setting(self, key, value):
        self.settings[key] = value

    def storage_get(self, key, default=None):
        return self.data.get(key, default)

    def storage_set(self, key, value):
        self.data[key] = value

    def add_menu_item(self, label, action_id):
        self.menus.append((label, action_id))

    def register_command(self, name, description=""):
        self.commands.append(name)

    def send_to_chat(self, text):
        self.chat.append(text)

    def run_on_ui(self, function, *args):
        return None

    def play_motion(self, *args, **kwargs):
        return True


@pytest.fixture
def plugin(monkeypatch):
    module = importlib.import_module("main")
    importlib.reload(module)
    api = FakeAPI(settings={"start_coin": 60, "click_luck": 100})
    monkeypatch.setattr(module, "_state", None)
    monkeypatch.setattr(module, "_window", None)
    module.on_load(api)
    return module, api


def test_load_registers_menu_and_commands(plugin):
    module, api = plugin

    assert [action for _label, action in api.menus] == [
        module.MENU_OPEN, module.MENU_PULL, module.MENU_CODEX]
    assert {"抽卡", "十连", "签到", "图鉴", "扭蛋"} <= set(api.commands)
    assert any("扭蛋机装好了" in text for _level, text in api.notes)
    assert module._get_state(api).coins == 60, "初始金币来自插件设置"


def test_command_pull_and_daily(plugin):
    module, api = plugin

    message = module.on_command(api, {"name": "抽卡"})
    assert "金币" not in message or "抽" in message
    assert api.data["gacha"]["total"] == 1

    daily = module.on_command(api, {"name": "签到"})
    assert "签到成功" in daily
    assert "签到成功" in module.on_command(api, {"name": "签到"}) or "已经签到" in \
        module.on_command(api, {"name": "签到"})


def test_command_codex_and_exchange(plugin):
    module, api = plugin

    codex = module.on_command(api, {"name": "图鉴"})
    assert "未收集" in codex

    refused = module.on_command(api, {"name": "兑换"})
    assert "星辉不够" in refused


def test_click_can_drop_coins(plugin):
    module, api = plugin
    before = module._get_state(api).coins

    module.on_event(api, {"name": "pet_click"})

    assert module._get_state(api).coins == before + 5, "概率 100% 时必须掉金币"
    assert any("+5" in text for _level, text in api.notes)

    module.on_event(api, {"name": "chat_finished"})
    assert module._get_state(api).coins == before + 5, "别的事件不动金币"


def test_comment_goes_to_chat(plugin):
    module, api = plugin
    module.on_command(api, {"name": "抽卡"})

    note = module._handle(api, "comment")

    assert api.chat and "手气" in api.chat[-1]
    assert "点评" in note


def test_system_prompt_mentions_odds_and_progress(plugin):
    module, api = plugin

    prompt = module.on_system_prompt(api, {})

    assert "扭蛋机" in prompt and "保底" in prompt and "0.5%" in prompt
    assert "金币" in prompt


def test_unload_resets_module_state(plugin):
    module, api = plugin
    module.on_command(api, {"name": "抽卡"})

    module.on_unload(api)

    assert module._state is None
