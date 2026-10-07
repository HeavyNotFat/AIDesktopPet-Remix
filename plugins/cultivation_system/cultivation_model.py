from __future__ import annotations

import json
import random
import time
from pathlib import Path

RESOURCES = Path(__file__).resolve().parent / "resources"
FOODS_FILE = RESOURCES / "foods.json"
FOODS_DIR = RESOURCES / "foods"

HUNGRY_MIN_GAP = 60.0
HUNGRY_MAX_GAP = 165.0

LEVEL_PROMPT = "你现在有点饿（饥饿值 {hungry}/{cap}），回答的时候可以顺口提一下想吃东西。"
FULL_PROMPT = "你现在吃得很饱、心情也不错（好感 {favor}），回答可以轻松活泼一点。"


def default_state() -> dict:
    # 初始饥饿给 60/100：老插件一上来就是满的，得等一分多钟才能喂第一口
    return {
        "coin": 0,
        "foods": [],
        "level": {"level": 1, "current": 0, "next": 100},
        "favorability": {"favorability": 0, "current": 0, "next": 100},
        "hungry": {"hungry": 60, "current": 100, "next": 150},
        "last_decay": time.time(),
        "replies": 0,
    }


def load_foods() -> dict:
    try:
        raw = json.loads(FOODS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {name: value for name, value in raw.items() if isinstance(value, dict)}


class PetState:
    """一只可以养的桌宠：金币、等级、好感、饥饿，外加一个背包。"""
    def __init__(self, storage=None, foods=None, rng=None, clock=time.time):
        self.storage = storage
        self.foods = foods if foods is not None else load_foods()
        self.rng = rng or random.Random()
        self.clock = clock
        self.state = self._load()
        self.next_decay_at = self._next_decay_time()

    def _storage_get(self, key, default=None):
        """三种 storage 形态都认：dict、插件的 PluginAPI、带 get/set 的包装。"""
        if self.storage is None:
            return default
        if isinstance(self.storage, dict):
            return self.storage.get(key, default)
        if hasattr(self.storage, "storage_get"):
            return self.storage.storage_get(key, default)
        return self.storage.get(key, default)

    def _storage_set(self, key, value):
        if self.storage is None:
            return value
        if isinstance(self.storage, dict):
            self.storage[key] = value
        elif hasattr(self.storage, "storage_set"):
            self.storage.storage_set(key, value)
        else:
            self.storage.set(key, value)
        return value

    def _load(self) -> dict:
        state = default_state()
        saved = self._storage_get("state")

        if isinstance(saved, dict):
            for key, value in saved.items():
                if isinstance(value, dict) and isinstance(state.get(key), dict):
                    state[key].update(value)
                else:
                    state[key] = value
        state["foods"] = [str(item) for item in state.get("foods") or []]
        return state

    def save(self):
        self.state["last_decay"] = self.clock()
        payload = json.loads(json.dumps(self.state, ensure_ascii=False))
        self._storage_set("state", payload)

    @property
    def coin(self) -> int:
        return int(self.state["coin"])

    @property
    def level(self) -> dict:
        return self.state["level"]

    @property
    def favor(self) -> dict:
        return self.state["favorability"]

    @property
    def hungry(self) -> dict:
        return self.state["hungry"]

    def bag(self) -> dict:
        """背包：食物名 -> 数量。"""
        counts = {}
        for name in self.state["foods"]:
            counts[name] = counts.get(name, 0) + 1
        return counts

    def status_text(self) -> str:
        return (
            f"金币 {self.coin}｜Lv.{self.level['level']}（{self.level['current']}/{self.level['next']}）"
            f"｜好感 {self.favor['favorability']}（{self.favor['current']}/{self.favor['next']}）"
            f"｜饥饿 {self.hungry['hungry']}/{self.hungry['current']}"
        )

    def add_level_exp(self, amount: int) -> list:
        """加经验；返回一串升级提示（可能连着升好几级）。"""
        events = []
        if amount == 0:
            return events

        config = self.level
        if config["current"] + amount < 0:
            if config["level"] <= 1:
                config["current"] = 0
                return events
            config["level"] -= 1
            config["current"] = 0
            events.append(f"等级掉回 Lv.{config['level']}")
        else:
            config["current"] += amount

        while config["current"] >= config["next"]:
            config["current"] -= config["next"]
            config["level"] += 1
            config["next"] = int(round(config["next"] * 2 + self.rng.uniform(100, 300)))

            hungry = self.hungry
            hungry["current"] = hungry["next"]
            hungry["next"] += 50
            hungry["hungry"] = min(hungry["current"], hungry["hungry"] + 40)

            events.append(f"升级啦！Lv.{config['level'] - 1} → Lv.{config['level']}，饥饿上限提升 50")
            self.add_favor_exp(self.rng.randint(50, 100))

        return events

    def add_favor_exp(self, amount: int) -> list:
        events = []
        if amount == 0:
            return events

        config = self.favor
        if config["current"] + amount < 0:
            if config["favorability"] <= 0:
                config["current"] = 0
                return events
            config["favorability"] -= 1
            config["current"] = 0
            events.append(f"好感掉回 {config['favorability']}")
        else:
            config["current"] += amount

        while config["current"] >= config["next"]:
            config["current"] -= config["next"]
            config["favorability"] += 1
            config["next"] = int(round(config["next"] * (2 * self.rng.uniform(1.0, 1.5))))
            events.append(f"好感升级！{config['favorability'] - 1} → {config['favorability']}")

        return events

    def feed_hungry(self, amount: int) -> bool:
        """喂食时加饥饿值；吃饱了就不吃（返回 False）。"""
        hungry = self.hungry
        target = hungry["hungry"] + amount
        if target >= hungry["current"]:
            return False
        hungry["hungry"] = max(0, target)
        return True

    def decay_hungry(self, amount: int = 1) -> bool:
        """饿一点；已经见底返回 True（该喊饿了）。"""
        hungry = self.hungry
        hungry["hungry"] = max(0, hungry["hungry"] - max(0, amount))
        return hungry["hungry"] <= 0

    def _next_decay_time(self) -> float:
        return self.clock() + self.rng.uniform(HUNGRY_MIN_GAP, HUNGRY_MAX_GAP)

    def tick(self) -> dict:
        """定时器每次进来调一次：到点了就掉饥饿值。"""
        if self.clock() < self.next_decay_at:
            return {}

        self.next_decay_at = self._next_decay_time()
        starving = self.decay_hungry(1)
        self.save()
        return {"hungry": self.hungry["hungry"], "starving": starving}

    def buy(self, name: str):
        """买一份食物：(成功?, 提示语)。"""
        food = self.foods.get(name)
        if not food:
            return False, f"没有这种食物：{name}"

        price = int(food.get("price", 0))
        if self.coin < price:
            return False, f"金币不足！还差 {price - self.coin} 金币"

        self.state["coin"] -= price
        self.state["foods"].append(name)
        self.save()
        return True, f"{name} 已放进背包，找零 {self.coin} 金币"

    def eat(self, name: str):
        """吃一份食物：(成功?, 提示语, 升级事件列表)。"""
        food = self.foods.get(name)
        if not food:
            return False, f"没有这种食物：{name}", []
        if name not in self.state["foods"]:
            return False, f"背包里没有 {name}", []

        if not self.feed_hungry(int(food.get("hungry", 0))):
            return False, "已经吃饱啦，晚点再吃", []

        self.state["foods"].remove(name)
        events = self.add_favor_exp(int(food.get("favor", 0)))
        events += self.add_level_exp(int(food.get("level", 0)))
        self.save()

        message = f"好吃！{name} 让饥饿 +{food.get('hungry', 0)}、好感 +{food.get('favor', 0)}"
        return True, message, events

    def click_reward(self, only_coin: bool = False, coins: int | None = None, max_coin: int = 5):
        if coins is not None:
            gained_coin = int(coins)
        else:
            gained_coin = self.rng.randint(1, max(1, int(max_coin)))
        gained_favor = 0 if only_coin else self.rng.randint(1, 3)

        self.state["coin"] += gained_coin
        events = self.add_favor_exp(gained_favor) if gained_favor else []
        self.save()

        message = f"获得 {gained_coin} 枚金币"
        if gained_favor:
            message += f"，好感 +{gained_favor}"
        return gained_coin, gained_favor, message, events

    def reply_reward(self, text: str):
        """AI 说完一段话的奖励：(经验, 好感, 事件列表)。"""
        length = len(str(text or ""))
        if length <= 0:
            return 0, 0, []

        exp = max(1, length // 40)
        favor = max(1, length // 20)
        self.state["replies"] = int(self.state.get("replies", 0)) + 1

        events = self.add_level_exp(exp)
        events += self.add_favor_exp(favor)
        self.save()
        return exp, favor, events

    def mood_prompt(self) -> str:
        """给 AI 的心情提示（增强 Hook 用）。"""
        hungry = self.hungry
        if hungry["hungry"] <= max(20, hungry["current"] * 0.2):
            return LEVEL_PROMPT.format(hungry=hungry["hungry"], cap=hungry["current"])
        if self.favor["favorability"] >= 2:
            return FULL_PROMPT.format(favor=self.favor["favorability"])
        return ""


__all__ = [
    "FOODS_DIR",
    "FOODS_FILE",
    "FULL_PROMPT",
    "HUNGRY_MAX_GAP",
    "HUNGRY_MIN_GAP",
    "LEVEL_PROMPT",
    "PetState",
    "default_state",
    "load_foods",
]
