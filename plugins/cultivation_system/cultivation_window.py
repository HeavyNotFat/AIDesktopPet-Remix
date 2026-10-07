from __future__ import annotations

from cultivation_model import FOODS_DIR, PetState

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QPen
from PySide6.QtWidgets import QWidget, QProgressBar, QGridLayout, QHBoxLayout, QVBoxLayout, QFrame

BAR_STYLE = """
QProgressBar {
    background: rgba(0, 0, 0, 170);
    border: 1px solid rgba(0, 255, 0, 90);
    border-radius: 7px;
    height: 20px;
    text-align: center;
    color: #d8ffd8;
    font-size: 11px;
}
QProgressBar::chunk { background: %s; border-radius: 6px; }
"""

PANEL_STYLE = """
QFrame#panel {
    background: rgba(0, 0, 0, 110);
    border: 1px solid rgba(0, 255, 0, 90);
    border-radius: 10px;
}
QFrame#panel QLabel { background: transparent; color: #00FF88; }
"""

WINDOW_STYLE = """
QWidget { background: #16181c; color: #d8ffd8; }
QLabel { background: transparent; color: #00FF88; }
QScrollArea { border: none; background: transparent; }
"""

BAG_COLS = 2
SHOP_WIDTH = 250
BAG_WIDTH = 250


def _pet_name() -> str:
    try:
        from stlibs import Config

        return str(Config.name or "桌宠")
    except Exception:  # noqa: BLE001 - 拿不到配置就用通称
        return "桌宠"


def _food_icon(name: str, size: int = 28) -> QIcon:
    """食物图当图标；图不在就现画一个绿色方块，别让按钮空着。"""
    path = FOODS_DIR / f"{name}.png"
    if path.exists():
        pixmap = QPixmap(str(path))
        if not pixmap.isNull():
            return QIcon(pixmap.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    fallback = QPixmap(size, size)
    fallback.fill(Qt.transparent)
    painter = QPainter(fallback)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor("#00FF00"), 1))
    painter.setBrush(QColor(0, 255, 0, 40))
    painter.drawRoundedRect(1, 1, size - 2, size - 2, 6, 6)
    painter.end()
    return QIcon(fallback)


class CultivationWindow(QWidget):
    """上面状态、左边商店、右边背包（背包横着排）。"""

    def __init__(self, api, state: PetState, on_action=None):
        from stlibs.themes import hacker

        super().__init__(None)
        self.api = api
        self.state = state
        self.on_action = on_action or (lambda action, payload=None: None)

        self.setWindowTitle(f"养成系统 · {_pet_name()}")
        self.resize(620, 560)
        self.setStyleSheet(WINDOW_STYLE)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)

        root.addWidget(self._build_status(hacker))
        root.addLayout(self._build_columns(hacker), 1)
        root.addLayout(self._build_actions(hacker))

        self.refresh()

    def _build_status(self, hacker) -> QFrame:
        panel = QFrame(self)
        panel.setObjectName("panel")
        panel.setStyleSheet(PANEL_STYLE)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(6)

        head = QHBoxLayout()
        self.title = hacker.Label("养成系统", panel)
        head.addWidget(self.title)
        head.addStretch(1)
        self.coin_label = hacker.Label("", panel)
        head.addWidget(self.coin_label)
        layout.addLayout(head)

        self.status_label = hacker.Label("", panel)
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.level_bar = self._bar(panel, "#ffd166")
        self.favor_bar = self._bar(panel, "#ff6b6b")
        self.hungry_bar = self._bar(panel, "#a0522d")
        for bar in (self.level_bar, self.favor_bar, self.hungry_bar):
            layout.addWidget(bar)

        return panel

    def _build_columns(self, hacker) -> QHBoxLayout:
        columns = QHBoxLayout()
        columns.setSpacing(10)

        shop_panel, shop_layout = self._panel(hacker, "商店（点一下购买）")
        self.shop_holder = self._grid_holder(shop_panel, BAG_COLS)
        shop_layout.addWidget(self.shop_holder)
        shop_layout.addStretch(1)
        columns.addWidget(shop_panel, 1)

        bag_panel, bag_layout = self._panel(hacker, "背包（点一下吃掉）")
        self.bag_holder = self._grid_holder(bag_panel, BAG_COLS)
        bag_layout.addWidget(self.bag_holder)
        bag_layout.addStretch(1)
        columns.addWidget(bag_panel, 1)

        columns.setStretch(0, 1)
        columns.setStretch(1, 1)
        self.shop_panel, self.bag_panel = shop_panel, bag_panel
        return columns

    def _panel(self, hacker, title: str):
        panel = QFrame(self)
        panel.setObjectName("panel")
        panel.setStyleSheet(PANEL_STYLE)
        panel.setMinimumWidth(SHOP_WIDTH)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)
        layout.addWidget(hacker.Label(title, panel))
        return panel, layout

    def _build_actions(self, hacker) -> QHBoxLayout:
        actions = QHBoxLayout()
        actions.setSpacing(8)
        for label, action in (
            ("点一下赚金币", "click"),
            ("刷新", "refresh"),
            ("关闭", "close"),
        ):
            button = hacker.Button(label, parent=self)
            button.set_border()
            button.setMinimumHeight(34)
            button.clicked.connect(lambda _checked=False, name=action: self.on_action(name))
            actions.addWidget(button)
        actions.addStretch(1)
        return actions

    def _grid_holder(self, parent: QWidget, columns: int) -> QWidget:
        holder = QWidget(parent)
        grid = QGridLayout(holder)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        holder.grid = grid
        holder.columns = columns
        return holder

    def _bar(self, parent: QWidget, color: str) -> QProgressBar:
        bar = QProgressBar(parent)
        bar.setStyleSheet(BAR_STYLE % color)
        bar.setTextVisible(True)
        bar.setFixedHeight(20)
        return bar

    def refresh(self):
        state = self.state
        self.coin_label.setText(f"金币 {state.coin}")

        level = state.level
        favor = state.favor
        hungry = state.hungry
        bag_count = sum(state.bag().values())
        self.status_label.setText(
            f"Lv.{level['level']}　·　好感 {favor['favorability']}　·　"
            f"饥饿 {hungry['hungry']}/{hungry['current']}　·　背包 {bag_count} 件"
        )

        self.level_bar.setMaximum(max(1, int(level["next"])))
        self.level_bar.setValue(int(level["current"]))
        self.level_bar.setFormat(f"Lv.{level['level']}　{level['current']}/{level['next']}")

        self.favor_bar.setMaximum(max(1, int(favor["next"])))
        self.favor_bar.setValue(int(favor["current"]))
        self.favor_bar.setFormat(f"好感 {favor['favorability']}　{favor['current']}/{favor['next']}")

        self.hungry_bar.setMaximum(max(1, int(hungry["current"])))
        self.hungry_bar.setValue(int(hungry["hungry"]))
        self.hungry_bar.setFormat(f"饥饿 {hungry['hungry']}/{hungry['current']}")

        self._fill(self.bag_holder, state.bag(), "eat", empty="背包是空的，去左边商店买点吃的")
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

        columns = max(1, holder.columns)
        if action == "eat":
            columns = columns if len(items) > 1 else 1

        if not items:
            if empty:
                hint = hacker.Label(empty, holder)
                hint.setWordWrap(True)
                grid.addWidget(hint, 0, 0, 1, columns)
            return

        for index, (name, count) in enumerate(sorted(items.items())):
            if action == "eat":
                text = f"{name} ×{count}"
                tooltip = "点一下吃掉"
            else:
                text = f"{name}\n{self._price(name)}"
                tooltip = f"{name}：饥饿 +{self._food(name, 'hungry')}、好感 +{self._food(name, 'favor')}"

            button = hacker.Button(text, icon=_food_icon(name), parent=holder)
            button.set_border()
            button.setToolTip(tooltip)
            button.setMinimumHeight(52)
            button.clicked.connect(lambda _checked=False, food=name: self.on_action(action, food))
            grid.addWidget(button, index // columns, index % columns)

    def _food(self, name: str, key: str):
        return (self.state.foods.get(name) or {}).get(key, "?")

    def _price(self, name: str) -> str:
        food = self.state.foods.get(name) or {}
        return f"{food.get('price', '?')} 金币"

    def show_panel(self):
        self.refresh()
        self.show()
        self.raise_()


__all__ = ["BAR_STYLE", "BAG_COLS", "PANEL_STYLE", "WINDOW_STYLE", "CultivationWindow"]
