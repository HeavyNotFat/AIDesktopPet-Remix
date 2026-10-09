
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import (
    QAction,
    QColor,
    QCursor,
    QFont,
    QFontMetrics,
    QIcon,
    QPainter,
    QPainterPath,
    QPixmap,
)
from PySide6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

from ..base import CombinedMeta, MenuWidgetABS
from .theme import (
    ACCENT_SOFT,
    BORDER,
    BORDER_STRONG,
    PRIMARY,
    PRIMARY_SOFT,
    RADIUS,
    RADIUS_SMALL,
    SURFACE,
    TEXT,
    font_css,
)

# 条目左边图标统一按这个尺寸取
MENU_ICON = 20


class Action(QAction):
    """主题契约里的 Action，参数是 (text, parent, icon)。"""

    def __init__(self, text, parent=None, icon: QIcon = None):
        super().__init__(text, parent)
        if icon is not None:
            self.setIcon(icon)


def menu_icon_pixmap(icon, size: int = MENU_ICON):
    """QIcon / QPixmap / 路径 转成菜单用的 QPixmap，认不出返回 None。"""
    if isinstance(icon, QPixmap):
        pixmap = icon
    elif isinstance(icon, QIcon):
        pixmap = icon.pixmap(size, size)
    elif isinstance(icon, str) and icon:
        pixmap = QPixmap(icon)
    else:
        return None

    if pixmap.isNull():
        return None
    return pixmap


class BreezeMenu(QWidget, MenuWidgetABS, metaclass=CombinedMeta):
    """右键菜单：白底圆角卡片，条目自绘，一层平铺。"""

    triggered = Signal(object)
    menu_closed = Signal()

    ROW_HEIGHT = 34
    PADDING = 8
    SHADOW_MARGIN = 2   # 卡片外面留一点边，圆角描边不会被窗边切掉
    HOVER_BG = ACCENT_SOFT

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._actions = []
        self._items = []
        self._action_items = []
        self._max_width = 0
        self._closed_announced = False

        self.hacker_font = QFont()
        self.hacker_font.setPointSize(10)

        self.box = QWidget(self)
        # objectName 要带主题前缀，否则两个主题的样式会互相打到
        self.box.setObjectName("breezeMenuBox")

        # 顶部/底部内边距：让条目的圆角高亮不贴着卡片边
        self.layout = QVBoxLayout(self.box)
        self.layout.setSpacing(2)
        self.layout.setContentsMargins(self.PADDING, self.PADDING, self.PADDING, self.PADDING)

        root = QVBoxLayout(self)
        root.setContentsMargins(self.SHADOW_MARGIN, self.SHADOW_MARGIN,
                                self.SHADOW_MARGIN, self.SHADOW_MARGIN)
        root.addWidget(self.box)

        self.setStyleSheet(f"""
            #breezeMenuBox {{
                background: {SURFACE};
                border: 1px solid {BORDER_STRONG};
                border-radius: {RADIUS}px;
            }}
            #breezeMenuBox QLabel {{
                background: transparent;
                border: none;
                padding: 0px;
                {font_css(14)}
            }}
        """)

    # 装配
    def addAction(self, action):
        self._actions.append(action)
        self._items.append(('action', action))

        text = action.text()
        pixmap = menu_icon_pixmap(action.icon())

        # 每条都按「最宽的那条」来画：短条目右边留空、高亮只亮一半会很难看
        label = QLabel()
        label.setFixedHeight(self.ROW_HEIGHT)
        label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        label.setCursor(Qt.PointingHandCursor)
        # 条目是自己画的，QAction 的 tooltip 不会自动出现，得挂到 label 上
        if hasattr(action, 'toolTip'):
            label.setToolTip(action.toolTip())

        entry = {'label': label, 'text': text, 'pixmap': pixmap, 'width': 0, 'redraw': None}
        entry['width'] = self._measure(text, pixmap)

        def redraw(hovered=False, entry=entry):
            width = max(entry['width'], self._max_width)
            entry['label'].setPixmap(self._render_row(entry, width, hovered))

        entry['redraw'] = redraw
        redraw(False)

        def enter_event(_event, redraw=redraw):
            redraw(True)

        def leave_event(_event, redraw=redraw):
            redraw(False)

        def mouse_press_event(event, action=action):
            # 只认左键：右键/中键点菜单项不该触发动作
            if event is None or event.button() == Qt.MouseButton.LeftButton:
                self._emit(action)

        label.enterEvent = enter_event
        label.leaveEvent = leave_event
        label.mousePressEvent = mouse_press_event

        self._action_items.append(entry)
        self.layout.addWidget(label)
        self._apply_width()
        return entry

    def addSeparator(self):
        separator = QWidget()
        separator.setFixedHeight(1)
        separator.setStyleSheet(f"background: {BORDER}; border: none;")
        separator.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.layout.addWidget(separator)
        self._items.append(('separator', separator))

        if self._max_width:
            separator.setFixedWidth(self._max_width)
        self.adjustSize()

    # 绘制
    def _render_row(self, entry, width: int, hovered: bool) -> QPixmap:
        """把一条菜单项画成一张位图。"""
        height = entry['label'].height() or self.ROW_HEIGHT
        pixmap = QPixmap(max(1, int(width)), int(height))
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setFont(self.hacker_font)

        if hovered:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(self.HOVER_BG))
            painter.drawRoundedRect(0, 0, width, height, RADIUS_SMALL, RADIUS_SMALL)

        painter.setPen(QColor(PRIMARY if hovered else TEXT))
        metrics = QFontMetrics(self.hacker_font)
        text_x = 8
        if entry['pixmap']:
            painter.drawPixmap(text_x, (height - entry['pixmap'].height()) // 2, entry['pixmap'])
            text_x += entry['pixmap'].width() + 8
        else:
            text_x += 2

        available = max(0, width - text_x - 8)
        text = metrics.elidedText(entry['text'], Qt.TextElideMode.ElideRight, available)
        painter.drawText(text_x, 0, available, height, Qt.AlignVCenter, text)
        painter.end()
        return pixmap

    def _measure(self, text: str, pixmap) -> int:
        metrics = QFontMetrics(self.hacker_font)
        # 左右各 8px 内边距；右侧再多留 16px，免得长条目贴着圆角边框
        width = 16 + metrics.horizontalAdvance(text) + 16
        width += (pixmap.width() + 8) if pixmap else 2
        return width

    def _apply_width(self):
        """把每条 item 拉到最宽那条，一行铺满、高亮不留空。"""
        for entry in self._action_items:
            entry['width'] = self._measure(entry['text'], entry['pixmap'])
            self._max_width = max(self._max_width, entry['width'])

        for entry in self._action_items:
            entry['label'].setFixedWidth(self._max_width)
            entry['redraw'](False)

        self.box.setFixedWidth(self._max_width + self.PADDING * 2)
        self.adjustSize()
    # 生命周期
    def _announce_closed(self):
        """通知宿主菜单收起来了，hide 与 close 只发一次。"""
        if self._closed_announced:
            return
        self._closed_announced = True
        self.menu_closed.emit()

    def hideEvent(self, event, /):
        self._announce_closed()
        super().hideEvent(event)

    def closeEvent(self, event, /):
        self._announce_closed()
        super().closeEvent(event)

    def menu_actions(self):
        """已经加进来的 QAction（Qt 的 actions() 拿不到）。"""
        return list(self._actions)

    def _emit(self, action):
        self.triggered.emit(action)
        if hasattr(action, 'trigger'):
            action.trigger()
        self.close()

    def exec(self, pos=None):
        """弹出菜单，宽度按内容收敛。"""
        if pos is None:
            pos = QCursor.pos()
        self._closed_announced = False  # 重新弹出来，下一次关闭要再通知一遍
        self._apply_width()
        self.show()
        self._apply_width()
        self.resize(self.minimumSizeHint())
        self.move(pos)


def draw_badge(glyph: str, size: int = 64, color: str = PRIMARY, background: str = PRIMARY_SOFT) -> QPixmap:
    """画一个圆角小徽章（标题栏图标、页面角标用）。"""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    path = QPainterPath()
    path.addRoundedRect(0, 0, size, size, size * 0.32, size * 0.32)
    painter.fillPath(path, QColor(background))

    font = QFont()
    font.setPointSizeF(size * 0.42)
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QColor(color))
    painter.drawText(0, 0, size, size, Qt.AlignmentFlag.AlignCenter, glyph)
    painter.end()
    return pixmap


__all__ = ["Action", "BreezeMenu", "MENU_ICON", "draw_badge", "menu_icon_pixmap"]
