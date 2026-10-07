from __future__ import annotations

from cultivation_model import FOODS_DIR, PetState

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QProgressBar, QGridLayout

BAR_STYLE = """
QProgressBar {
    background: rgba(0, 0, 0, 160);
    border: 1px solid rgba(0, 255, 0, 90);
    border-radius: 6px;
    height: 16px;
    text-align: center;
    color: #d8ffd8;
    font-size: 11px;
}
QProgressBar::chunk { background: %s; border-radius: 5px; }
"""


def _pet_name() -> str:
    try:
        from stlibs import Config

        return str(Config.name or "桌宠")
    except Exception:  # noqa: BLE001 - 拿不到配置就用通称
        return "桌宠"


class CultivationWindow(QWidget):
    """状态条 + 背包 + 商店，三块内容。"""
    COLS = 3

    def __init__(self, api, state: PetState, on_action=None):
        from stlibs.themes import hacker

        super().__init__(None)
        self.api = api
        self.state = state
        self.on_action = on_action or (lambda action, payload=None: None)

        pet = _pet_name()
        self.setWindowTitle(f"养成系统 · {pet}")
        self.resize(560, 580)
        self.setStyleSheet(
            "QWidget { background: #1e1f22; color: #d8ffd8; }"
            "QLabel { color: #00FF88; background: transparent; }"
        )

        self.title = hacker.Label("养成系统", self)
        self.title.setGeometry(16, 10, 200, 28)

        self.coin_label = hacker.Label("", self)
        self.coin_label.setGeometry(16, 40, 320, 24)

        self.status_label = hacker.Label("", self)
        self.status_label.setWordWrap(True)
        self.status_label.setGeometry(16, 66, 520, 40)

        self.level_bar = self._bar(16, 112, "#ffd166")
        self.favor_bar = self._bar(16, 150, "#ff6b6b")
        self.hungry_bar = self._bar(16, 188, "#a0522d")

        self.bag_label = hacker.Label("背包（点一下吃掉）", self)
        self.bag_label.setGeometry(16, 216, 300, 24)
        self.bag_holder = self._grid_holder(16, 244, 100)
        self.bag_grid = self.bag_holder.grid

        self.shop_label = hacker.Label("商店（点一下购买）", self)
        self.shop_label.setGeometry(16, 352, 300, 24)
        self.shop_holder = self._grid_holder(16, 380, 148)
        self.shop_grid = self.shop_holder.grid

        for index, (label, action) in enumerate((
            ("点一下赚金币", "click"),
            ("刷新", "refresh"),
            ("关闭", "close"),
        )):
            button = hacker.Button(label, parent=self)
            button.set_border()
            button.setGeometry(16 + index * 110, 536, 100, 30)
            button.clicked.connect(lambda _checked=False, name=action: self.on_action(name))

        self.refresh()

    def _bar(self, x: int, y: int, color: str) -> QProgressBar:
        bar = QProgressBar(self)
        bar.setGeometry(x, y, 520, 18)
        bar.setStyleSheet(BAR_STYLE % color)
        bar.setTextVisible(True)
        return bar

    def _grid_holder(self, x: int, y: int, height: int) -> QWidget:
        holder = QWidget(self)
        holder.setGeometry(x, y, 528, height)
        grid = QGridLayout(holder)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(6)
        holder.grid = grid
        return holder

    def refresh(self):
        from stlibs.themes import hacker

        state = self.state
        self.coin_label.setText(f"金币：{state.coin}")
        self.status_label.setText(state.status_text())

        level = state.level
        self.level_bar.setMaximum(max(1, int(level["next"])))
        self.level_bar.setValue(int(level["current"]))
        self.level_bar.setFormat(f"Lv.{level['level']}  {level['current']}/{level['next']}")

        favor = state.favor
        self.favor_bar.setMaximum(max(1, int(favor["next"])))
        self.favor_bar.setValue(int(favor["current"]))
        self.favor_bar.setFormat(f"好感 {favor['favorability']}  {favor['current']}/{favor['next']}")

        hungry = state.hungry
        self.hungry_bar.setMaximum(max(1, int(hungry["current"])))
        self.hungry_bar.setValue(int(hungry["hungry"]))
        self.hungry_bar.setFormat(f"饥饿 {hungry['hungry']}/{hungry['current']}")

        self._fill(self.bag_holder, state.bag(), "eat", empty="背包是空的，先去商店买点吃的")
        self._fill(self.shop_holder, {name: 1 for name in state.foods}, "buy")

    def _fill(self, holder: QWidget, items: dict, action: str, empty: str = ""):
        from stlibs.themes import hacker

        grid = holder.grid
        while grid.count():
            item = grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        if not items:
            if empty:
                grid.addWidget(hacker.Label(empty, holder), 0, 0, 1, self.COLS)
            return

        for index, (name, count) in enumerate(sorted(items.items())):
            label = f"{name} x{count}" if action == "eat" else f"{name}（{self._price(name)}）"
            button = hacker.Button(label, parent=holder)
            button.set_border()
            button.setToolTip(f"{FOODS_DIR / (name + '.png')}")
            button.clicked.connect(lambda _checked=False, food=name: self.on_action(action, food))
            grid.addWidget(button, index // self.COLS, index % self.COLS)

    def _price(self, name: str) -> str:
        food = self.state.foods.get(name) or {}
        return f"{food.get('price', '?')} 金币"

    def show_panel(self):
        self.refresh()
        self.show()
        self.raise_()


__all__ = ["BAR_STYLE", "CultivationWindow"]
