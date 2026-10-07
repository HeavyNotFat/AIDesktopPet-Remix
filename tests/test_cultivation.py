import json
import random
import sys
from pathlib import Path

import pytest

PLUGIN_DIR = Path(__file__).resolve().parents[1] / "plugins" / "cultivation_system"
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

from cultivation_model import (  # noqa: E402
    HUNGRY_MAX_GAP,
    HUNGRY_MIN_GAP,
    PetState,
    default_state,
    load_foods,
)

FOODS = {
    "汉堡": {"price": 80, "hungry": 8, "favor": 10, "level": 0},
    "烤鱼": {"price": 850, "hungry": 80, "favor": 85, "level": 180},
    "剩骨头": {"price": 1, "hungry": 2, "favor": -5, "level": 0},
}


class Clock:
    """可控时钟：测饥饿衰减不用真的等一分多钟。"""
    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def state(clock):
    return PetState(storage={}, foods=dict(FOODS), rng=random.Random(2024), clock=clock)


def test_defaults_are_playable():
    data = default_state()

    assert data["coin"] == 0
    assert data["level"]["level"] == 1
    assert data["hungry"]["hungry"] < data["hungry"]["current"], "一开始就该能喂食"


def test_real_foods_file_loads():
    foods = load_foods()

    assert "汉堡" in foods
    assert all("price" in item for item in foods.values())


def test_initial_status_text(state):
    text = state.status_text()

    assert "金币 0" in text
    assert "Lv.1" in text
    assert "饥饿 60/100" in text


def test_buy_and_bag(state):
    state.state["coin"] = 100

    ok, message = state.buy("汉堡")

    assert ok is True
    assert state.coin == 20
    assert state.bag() == {"汉堡": 1}
    assert "找零 20" in message


def test_buy_without_enough_coin(state):
    ok, message = state.buy("烤鱼")

    assert ok is False
    assert "金币不足" in message
    assert "850" in message


def test_buy_unknown_food(state):
    ok, message = state.buy("螺蛳粉")

    assert ok is False
    assert "没有这种食物" in message


def test_eat_requires_item_in_bag(state):
    ok, message, events = state.eat("汉堡")

    assert ok is False
    assert "背包里没有" in message
    assert events == []


def test_eat_raises_hungry_favor_and_level(state):
    state.state["coin"] = 1000
    state.buy("汉堡")

    ok, message, events = state.eat("汉堡")

    assert ok is True
    assert state.hungry["hungry"] == 60 + 8
    assert state.bag() == {}
    assert "汉堡" in message
    assert state.favor["current"] >= 10, "好感 +10"


def test_eat_rejects_when_it_would_overflow(state):
    """沿用老插件的规矩：吃下去会超过上限就直接拒绝，而不是截断。"""
    state.state["coin"] = 1000
    state.buy("烤鱼")  # 饥饿 +80，而当前只有 60/100 的空间

    ok, message, _events = state.eat("烤鱼")

    assert ok is False
    assert "吃饱" in message
    assert state.bag() == {"烤鱼": 1}


def test_eat_stops_when_full(state):
    state.state["coin"] = 1000
    state.buy("烤鱼")
    state.hungry["hungry"] = state.hungry["current"]

    ok, message, _events = state.eat("烤鱼")

    assert ok is False
    assert "吃饱" in message
    assert state.bag() == {"烤鱼": 1}, "没吃成就不该消耗食物"


def test_level_up_raises_hungry_cap(state):
    before_cap = state.hungry["current"]

    events = state.add_level_exp(120)

    assert events and "升级" in events[0]
    assert state.level["level"] == 2
    assert state.hungry["current"] == before_cap + 50
    assert state.level["next"] > 100, "下一级门槛要变高"


def test_multi_level_up_in_one_go(state):
    events = state.add_level_exp(100000)

    assert state.level["level"] > 2
    assert len([item for item in events if "升级" in item]) == state.level["level"] - 1


def test_negative_exp_drops_level(state):
    state.add_level_exp(120)
    level = state.level["level"]

    state.add_level_exp(-50)

    assert state.level["current"] >= 0
    assert state.level["level"] in (level, level - 1)


def test_exp_never_goes_negative_at_level_one(state):
    state.add_level_exp(-999)

    assert state.level["level"] == 1
    assert state.level["current"] == 0


def test_favor_levelling(state):
    events = state.add_favor_exp(120)

    assert state.favor["favorability"] == 1
    assert events and "好感" in events[0]


def test_click_reward_gives_coin_and_favor(state):
    coin, favor, message, _events = state.click_reward(max_coin=5)

    assert 1 <= coin <= 5
    assert 1 <= favor <= 3
    assert "金币" in message
    assert state.coin == coin


def test_click_reward_cap_from_settings(state):
    for _ in range(20):
        coin, _favor, _message, _events = state.click_reward(max_coin=2)
        assert 1 <= coin <= 2


def test_click_reward_coins_override(state):
    coin, favor, _message, _events = state.click_reward(only_coin=True, coins=7)

    assert coin == 7
    assert favor == 0


def test_reply_reward_scales_with_length(state):
    short = state.reply_reward("嗯")
    long = state.reply_reward("这是一段很长的回答。" * 20)

    assert short[0] >= 1 and short[1] >= 1
    assert long[0] > short[0]
    assert long[1] > short[1]
    assert state.state["replies"] == 2


def test_reply_reward_ignores_empty(state):
    assert state.reply_reward("") == (0, 0, [])
    assert state.state["replies"] == 0


def test_hungry_decay_and_starving(state):
    assert state.decay_hungry(1) is False
    assert state.hungry["hungry"] == 59

    assert state.decay_hungry(999) is True, "掉到 0 要喊饿"
    assert state.hungry["hungry"] == 0


def test_tick_only_decays_after_the_gap(state, clock):
    assert state.tick() == {}, "还没到时间"

    clock.advance(HUNGRY_MAX_GAP + 1)
    result = state.tick()

    assert result["hungry"] == 59
    assert result["starving"] is False
    assert HUNGRY_MIN_GAP <= state.next_decay_at - clock() <= HUNGRY_MAX_GAP + 1


def test_tick_reports_starving(state, clock):
    state.hungry["hungry"] = 0
    clock.advance(HUNGRY_MAX_GAP + 1)

    assert state.tick()["starving"] is True


def test_save_and_reload_round_trip(tmp_path, clock):
    storage = {}
    first = PetState(storage=storage, foods=dict(FOODS), rng=random.Random(1), clock=clock)
    first.state["coin"] = 321
    first.add_level_exp(120)
    first.save()

    second = PetState(storage=storage, foods=dict(FOODS), rng=random.Random(1), clock=clock)

    assert second.coin == 321
    assert second.level["level"] == first.level["level"]
    assert second.hungry["current"] == first.hungry["current"]


def test_storage_object_style(clock):
    """插件的 storage 是对象（storage_get/storage_set）也要能用。"""
    class ApiStorage:
        def __init__(self):
            self.data = {}

        def storage_get(self, key, default=None):
            return self.data.get(key, default)

        def storage_set(self, key, value):
            self.data[key] = value

    storage = ApiStorage()
    state = PetState(storage=storage, foods=dict(FOODS), rng=random.Random(1), clock=clock)
    state.state["coin"] = 5
    state.save()

    assert storage.data["state"]["coin"] == 5
    assert json.loads(json.dumps(storage.data, ensure_ascii=False))["state"]["coin"] == 5


def test_corrupted_save_falls_back_to_defaults(clock):
    class Broken:
        def storage_get(self, key, default=None):
            return "这不是字典"

        def storage_set(self, key, value):
            pass

    state = PetState(storage=Broken(), foods=dict(FOODS), rng=random.Random(1), clock=clock)

    assert state.coin == 0
    assert state.hungry["hungry"] == 60


def test_mood_prompt_when_hungry(state):
    state.hungry["hungry"] = 5

    assert "饿" in state.mood_prompt()


def test_mood_prompt_when_favoured(state):
    state.favor["favorability"] = 3

    assert state.mood_prompt()


def test_mood_prompt_empty_when_neutral(state):
    assert state.mood_prompt() == ""
