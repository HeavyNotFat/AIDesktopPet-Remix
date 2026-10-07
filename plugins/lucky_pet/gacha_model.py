from __future__ import annotations

import json
import random
from datetime import date
from pathlib import Path

ITEMS_PATH = Path(__file__).resolve().parent / "resources" / "items.json"

RARITIES = ("N", "R", "SR", "SSR", "UR")
RARITY_COLOR = {"N": "#9aa0a6", "R": "#4dabf7", "SR": "#b197fc", "SSR": "#ffd166", "UR": "#ff6b6b"}
RARITY_WEIGHT = {"N": 55.0, "R": 30.0, "SR": 12.0, "SSR": 2.5, "UR": 0.5}
DUP_SHARDS = {"N": 1, "R": 2, "SR": 6, "SSR": 25, "UR": 120}

SINGLE_COST = 10
TEN_COST = 90
PITY_SR = 10
PITY_SSR = 80
DAILY_COIN = 30
EXCHANGE_SHARDS = 60


def load_items(path: Path | str = ITEMS_PATH) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {rarity: list(data.get(rarity) or []) for rarity in RARITIES}


class GachaState:
    """扭蛋机的全部状态：金币、星辉、保底计数、图鉴；都从插件存储里读写。"""

    KEY = "gacha"

    def __init__(self, storage=None, items: dict | None = None, rng: random.Random | None = None,
                 start_coin: int = 60):
        self.storage = storage
        self.items = items if items is not None else load_items()
        self.rng = rng or random.Random()
        self.data = self._load(start_coin)
        self.last_results: list = []

    def _load(self, start_coin: int) -> dict:
        raw = {}
        if self.storage is not None:
            raw = self.storage.get(self.KEY) or {}
        if not isinstance(raw, dict):
            raw = {}

        data = {
            "coins": int(raw.get("coins", start_coin)),
            "shards": int(raw.get("shards", 0)),
            "pity_sr": int(raw.get("pity_sr", 0)),
            "pity_ssr": int(raw.get("pity_ssr", 0)),
            "total": int(raw.get("total", 0)),
            "collection": dict(raw.get("collection") or {}),
            "last_daily": str(raw.get("last_daily") or ""),
        }
        if not isinstance(data["collection"], dict):
            data["collection"] = {}
        return data

    def save(self):
        if self.storage is not None:
            self.storage[self.KEY] = self.data

    @property
    def coins(self) -> int:
        return self.data["coins"]

    @property
    def shards(self) -> int:
        return self.data["shards"]

    @property
    def pity_left(self) -> int:
        """还有几抽必出 SSR 以上（给进度条用）。"""
        return max(0, PITY_SSR - self.data["pity_ssr"])

    def add_coins(self, count: int):
        self.data["coins"] = max(0, self.data["coins"] + int(count))
        self.save()

    def daily(self, today: str | None = None):
        """每日签到：一天只能领一次。"""
        today = today or date.today().isoformat()
        if self.data["last_daily"] == today:
            return False, 0
        self.data["last_daily"] = today
        self.add_coins(DAILY_COIN)
        return True, DAILY_COIN

    def pick_rarity(self) -> str:
        pool = [(rarity, RARITY_WEIGHT[rarity]) for rarity in RARITIES if self.items.get(rarity)]
        total = sum(weight for _rarity, weight in pool)
        point = self.rng.random() * total
        for rarity, weight in pool:
            point -= weight
            if point <= 0:
                return rarity
        return pool[-1][0]

    def _one(self) -> dict:
        pity_sr = self.data["pity_sr"] + 1
        pity_ssr = self.data["pity_ssr"] + 1

        if pity_ssr >= PITY_SSR:
            rarity = "UR" if self.rng.random() < 0.2 else "SSR"
        elif pity_sr >= PITY_SR:
            rarity = self.rng.choice(["SR", "SSR"])
        else:
            rarity = self.pick_rarity()

        pool = self.items.get(rarity) or self.items.get("N") or [{"id": "nothing", "name": "空气", "emoji": "💨"}]
        item = dict(self.rng.choice(pool))

        self.data["pity_sr"] = 0 if rarity in ("SR", "SSR", "UR") else pity_sr
        self.data["pity_ssr"] = 0 if rarity in ("SSR", "UR") else pity_ssr
        self.data["total"] += 1

        owned = int(self.data["collection"].get(item["id"], 0))
        item["rarity"] = rarity
        item["new"] = owned == 0
        item["shards"] = 0 if item["new"] else DUP_SHARDS[rarity]
        self.data["collection"][item["id"]] = owned + 1
        self.data["shards"] += item["shards"]
        return item

    def pull(self, times: int = 1):
        cost = TEN_COST if times >= 10 else SINGLE_COST * times
        if self.coins < cost:
            return False, f"金币不够啦（要 {cost}，现在 {self.coins}）。发「/签到」或者摸我几下捡星辉～", []

        self.data["coins"] -= cost
        results = [self._one() for _ in range(times)]
        self.last_results = results
        self.save()
        return True, self.summary(results), results

    @staticmethod
    def summary(results: list) -> str:
        if not results:
            return "什么都没抽到"
        best = max(results, key=lambda item: RARITIES.index(item["rarity"]))
        head = f"{len(results)} 连：{best['rarity']} {best['emoji']} {best['name']}"
        return head if len(results) == 1 else f"{head}（最高稀有度）"

    def exchange(self):
        """星辉直接换一个 UR（重复抽多了的保底出口）。"""
        pool = self.items.get("UR") or []
        if not pool:
            return False, "这个扭蛋机里没有 UR", None
        if self.shards < EXCHANGE_SHARDS:
            return False, f"星辉不够（要 {EXCHANGE_SHARDS}，现在 {self.shards}）", None

        item = dict(self.rng.choice(pool))
        self.data["shards"] -= EXCHANGE_SHARDS
        owned = int(self.data["collection"].get(item["id"], 0))
        item.update({"rarity": "UR", "new": owned == 0, "shards": 0})
        self.data["collection"][item["id"]] = owned + 1
        self.last_results = [item]
        self.save()
        return True, f"用 {EXCHANGE_SHARDS} 星辉换到了 UR {item['emoji']} {item['name']}", item

    def codex(self) -> list:
        """图鉴：按稀有度从高到低列，已收集的打勾。"""
        lines = []
        for rarity in reversed(RARITIES):
            entries = []
            for item in self.items.get(rarity) or []:
                count = int(self.data["collection"].get(item["id"], 0))
                mark = f"×{count}" if count else "未收集"
                entries.append(f"{item['emoji']} {item['name']}（{mark}）")
            if entries:
                lines.append(f"{rarity}：" + "、".join(entries))
        return lines

    def stats_text(self) -> str:
        owned = len(self.data["collection"])
        total_items = sum(len(pool) for pool in self.items.values())
        return (f"金币 {self.coins}　星辉 {self.shards}　已抽 {self.data['total']} 次　"
                f"图鉴 {owned}/{total_items}　距 SSR 保底 {self.pity_left} 抽")

    def comment_prompt(self, results: list) -> str:
        """给 AI 的点评素材（让桌宠用自己的人设吐槽这次手气）。"""
        if not results:
            return "我刚想去扭蛋，但金币不够。用你的语气吐槽我两句，20 字以内。"
        best = max(results, key=lambda item: RARITIES.index(item["rarity"]))
        detail = "、".join(f"{item['rarity']}{item['name']}" for item in results[:10])
        return (f"我刚在扭蛋机抽到：{detail}。最高是 {best['rarity']}。"
                f"用你的语气点评一下我的手气，30 字以内，不要客套。")


__all__ = ["DUP_SHARDS", "GachaState", "RARITIES", "RARITY_COLOR", "RARITY_WEIGHT", "load_items"]
