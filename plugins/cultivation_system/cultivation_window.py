
from __future__ import annotations

from cultivation_model import FOODS_DIR, PetState

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from stlibs import SharingData
from stlibs.graphics.palette import palette

SHOP_COLS = 3
SHOP_IMAGE = 72
BAG_COLS = 2
BAG_IMAGE = 58


def _theme():
    """当前主题包（插件宿主一定绑好了；拿不到就回退 hacker）。"""
    theme = getattr(SharingData, "theme", None)
    if theme is not None:
        return theme
    from stlibs.themes import hacker

    return hacker


def _pet_name() -> str:
    try:
        from stlibs import Config

        return str(Config.name or "桌宠")
    except Exception:  # noqa: BLE001 - 拿不到配置就用通称
        return "桌宠"


def bar_style(colors, key: str) -> str:
    """进度条样式：底色/描边取主题，填充色按语义（等级 / 好感 / 饥饿）。"""
    bright, soft = colors.tint(key)
    return f"""
    QProgressBar {{
        background: {colors.track};
        border: 1px solid {colors.border};
        border-radius: 7px;
        height: 20px;
        text-align: center;
        color: {colors.text};
        font-size: 11px;
    }}
    QProgressBar::chunk {{
        background: {bright};
        border-radius: 6px;
    }}
    """


def panel_style(colors) -> str:
    return f"""
    QFrame#panel {{
        background: {colors.surface};
        border: 1px solid {colors.border};
        border-radius: {colors.radius}px;
    }}
    QFrame#panel QLabel {{ background: transparent; color: {colors.text}; }}
    """


def tile_style(colors) -> str:
    return f"""
    QFrame#tile {{
        background: {colors.surface_soft};
        border: 1px solid {colors.border};
        border-radius: {colors.radius_small + 3}px;
    }}
    QFrame#tile:hover {{
        background: {colors.hover};
        border: 1px solid {colors.border_strong};
    }}
    QFrame#tile QLabel {{ background: transparent; color: {colors.text}; }}
    """


def _food_pixmap(name: str, size: int, colors=None) -> QPixmap:
    """食物图；图不在就按主题色现画一个，别让格子空着。"""
    path = FOODS_DIR / f"{name}.png"
    if path.exists():
        pixmap = QPixmap(str(path))
        if not pixmap.isNull():
            return pixmap.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)

    colors = colors or palette()
    fallback = QPixmap(size, size)
    fallback.fill(Qt.transparent)
    painter = QPainter(fallback)
    painter.setRenderHint(QPainter.Antialiasing)

    fill = QColor(colors.primary)
    fill.setAlpha(40)
    painter.setPen(QPen(QColor(colors.primary), 1))
    painter.setBrush(fill)
    painter.drawRoundedRect(1, 1, size - 2, size - 2, 8, 8)
    painter.end()
    return fallback


def _food_icon(name: str, size: int = 28) -> QIcon:
    """给按钮用的图标形式（兼容旧调用）。"""
    return QIcon(_food_pixmap(name, size))


class FoodTile(QFrame):
    """一格食物：上面大图，下面名字与价格（或数量）。整格可点。"""

    def __init__(self, name: str, detail: str, image_size: int, parent: QWidget, on_click=None):
        super().__init__(parent)
        colors = palette()

        self.setObjectName("tile")
        self.setStyleSheet(tile_style(colors))
        self.setCursor(Qt.PointingHandCursor)
        self.name = name
        self.on_click = on_click

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 10, 8, 10)
        layout.setSpacing(6)

        self.image_label = QLabel(self)
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setPixmap(_food_pixmap(name, image_size, colors))
        self.image_label.setFixedHeight(image_size)
        layout.addWidget(self.image_label)

        self.name_label = QLabel(name, self)
        self.name_label.setAlignment(Qt.AlignCenter)
        self.name_label.setStyleSheet(f"color: {colors.text}; background: transparent;")
        layout.addWidget(self.name_label)

        self.detail_label = QLabel(detail, self)
        self.detail_label.setAlignment(Qt.AlignCenter)
        self.detail_label.setStyleSheet(f"color: {colors.text_dim}; background: transparent;")
        layout.addWidget(self.detail_label)

        layout.addStretch(1)

    def text(self) -> str:
        return self.name

    def click(self):
        if self.on_click is not None:
            self.on_click(self.name)

    def mouseReleaseEvent(self, event, /):
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self.click()
        super().mouseReleaseEvent(event)


class CultivationWindow(QWidget):
    """上面状态、左边商店、右边背包（背包横着排）。"""

    def __init__(self, api, state: PetState, on_action=None):
        super().__init__(None)
        self.api = api
        self.state = state
        self.on_action = on_action or (lambda action, payload=None: None)
        self.colors = palette()
        self.theme = _theme()

        self.setWindowTitle(f"养成系统 · {_pet_name()}")
        self.resize(720, 660)
        self.setStyleSheet(self.colors.sheet("QWidget"))

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)

        root.addWidget(self._build_status())
        root.addLayout(self._build_columns(), 1)
        root.addLayout(self._build_actions())

        self.refresh()

    # -- 构建 ---------------------------------------------------------------
    def _label(self, text: str, parent: QWidget) -> QLabel:
        """主题的标签控件：换主题时字体/配色自动跟着变。"""
        return self.theme.Label(text, parent)

    def _build_status(self) -> QFrame:
        panel = QFrame(self)
        panel.setObjectName("panel")
        panel.setStyleSheet(panel_style(self.colors))

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(6)

        head = QHBoxLayout()
        self.title = self._label("养成系统", panel)
        head.addWidget(self.title)
        head.addStretch(1)
        self.coin_label = self._label("", panel)
        head.addWidget(self.coin_label)
        layout.addLayout(head)

        self.status_label = self._label("", panel)
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.level_bar = self._bar(panel, "level")
        self.favor_bar = self._bar(panel, "favor")
        self.hungry_bar = self._bar(panel, "hungry")
        for bar in (self.level_bar, self.favor_bar, self.hungry_bar):
            layout.addWidget(bar)

        return panel

    def _build_columns(self) -> QHBoxLayout:
        columns = QHBoxLayout()
        columns.setSpacing(10)

        shop_panel, shop_layout = self._panel("商店（点一下购买）")
        self.shop_holder = self._grid_holder(shop_panel, SHOP_COLS)
        shop_layout.addWidget(self.shop_holder)
        shop_layout.addStretch(1)
        columns.addWidget(shop_panel, 3)

        bag_panel, bag_layout = self._panel("背包（点一下吃掉）")
        self.bag_holder = self._grid_holder(bag_panel, BAG_COLS)
        bag_layout.addWidget(self.bag_holder)
        bag_layout.addStretch(1)
        columns.addWidget(bag_panel, 2)

        self.shop_panel, self.bag_panel = shop_panel, bag_panel
        return columns

    def _panel(self, title: str):
        panel = QFrame(self)
        panel.setObjectName("panel")
        panel.setStyleSheet(panel_style(self.colors))

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)
        layout.addWidget(self._label(title, panel))
        return panel, layout

    def _build_actions(self) -> QHBoxLayout:
        actions = QHBoxLayout()
        actions.setSpacing(8)
        for label, action in (
            ("点一下赚金币", "click"),
            ("刷新", "refresh"),
            ("关闭", "close"),
        ):
            button = self.theme.Button(label, parent=self)
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

    def _bar(self, parent: QWidget, key: str) -> QProgressBar:
        bar = QProgressBar(parent)
        bar.setStyleSheet(bar_style(self.colors, key))
        bar.setTextVisible(True)
        bar.setFixedHeight(20)
        return bar

    # -- 刷新 ---------------------------------------------------------------
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
                hint = self._label(empty, holder)
                hint.setWordWrap(True)
                grid.addWidget(hint, 0, 0, 1, columns)
            return

        image_size = SHOP_IMAGE if action == "buy" else BAG_IMAGE
        for index, (name, count) in enumerate(sorted(items.items())):
            if action == "eat":
                detail = f"×{count}"
                tooltip = f"{name}：点一下吃掉（还有 {count} 个）"
            else:
                detail = self._price(name)
                tooltip = f"{name}：饥饿 +{self._food(name, 'hungry')}、好感 +{self._food(name, 'favor')}"

            tile = FoodTile(name, detail, image_size, holder,
                            on_click=lambda food, act=action: self.on_action(act, food))
            tile.setToolTip(tooltip)
            tile.setMinimumHeight(image_size + 54)
            grid.addWidget(tile, index // columns, index % columns)

    def _food(self, name: str, key: str):
        return (self.state.foods.get(name) or {}).get(key, "?")

    def _price(self, name: str) -> str:
        food = self.state.foods.get(name) or {}
        return f"{food.get('price', '?')} 金币"

    def show_panel(self):
        self.refresh()
        self.show()
        self.raise_()


__all__ = [
    "BAG_COLS",
    "BAG_IMAGE",
    "SHOP_COLS",
    "SHOP_IMAGE",
    "CultivationWindow",
    "FoodTile",
    "bar_style",
    "panel_style",
    "tile_style",
]
