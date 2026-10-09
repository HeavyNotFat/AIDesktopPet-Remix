
from PySide6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import (
    QAction,
    QColor,
    QCursor,
    QFont,
    QFontDatabase,
    QFontMetrics,
    QIcon,
    QPainter,
    QPixmap,
)

from ..base import CombinedMeta, MenuWidgetABS

# 条目左边图标的统一尺寸
MENU_ICON = 22


def menu_icon_pixmap(icon, size: int = MENU_ICON):
    """QIcon / QPixmap / 图片路径 → 画菜单用的 QPixmap；认不出来就返回 None。"""
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


class Action(QAction):
    """主题契约里的 Action：``(text, parent, icon)``，和 Qt 的 QAction 同源。"""

    def __init__(self, text, parent=None, icon: QIcon = None):
        super().__init__(text, parent)
        if icon is not None:
            self.setIcon(icon)


class HackerMenu(QWidget, MenuWidgetABS, metaclass=CombinedMeta):
    """右键菜单：条目自绘成一张 QPixmap，一层平铺、没有子菜单。"""

    triggered = Signal(object)
    # 菜单收起来了：宿主靠它复位拖拽状态
    menu_closed = Signal()

    ROW_HEIGHT = 36   # 单条菜单项的高度

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._actions = []
        self._items = []  # Track all items including separators
        self._action_items = []  # 每条 item 的绘制数据（用来统一宽度）
        self._max_width = 0
        self._closed_announced = False  # menu_closed 已经发过了（hide/close 会重复触发）

        font_id = QFontDatabase.addApplicationFont("./resources/fonts/jetbrains.ttf")
        if font_id != -1:
            family = QFontDatabase.applicationFontFamilies(font_id)[0]
            self.hacker_font = QFont(family, 16)
        else:
            self.hacker_font = QFont("Courier New", 16)

        self.box = QWidget(self)
        self.box.setObjectName("box")

        self.layout = QVBoxLayout(self.box)
        self.layout.setSpacing(6)
        self.layout.setContentsMargins(10, 10, 10, 10)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self.box)

        self.setStyleSheet("""
        #box {
            background: rgba(10, 10, 10, 220);
            border: 2px solid #00FF00;
            border-radius: 12px;
        }
        QLabel {
            background: transparent;
            color: #00FF00;
            padding: 0 12px;
            border-radius: 6px;
            min-height: 36px;
            max-height: 36px;
        }
        """)

    def addAction(self, action):
        self._actions.append(action)
        self._items.append(('action', action))

        text = action.text()
        pixmap = menu_icon_pixmap(action.icon())

        # 每条都按最宽的那条画，短条目的高亮才铺得满
        label = QLabel()
        label.setFixedHeight(self.ROW_HEIGHT)
        label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        label.setCursor(Qt.PointingHandCursor)
        if hasattr(action, 'toolTip'):
            label.setToolTip(action.toolTip())

        entry = {
            'label': label,
            'text': text,
            'pixmap': pixmap,
            'width': 0,
            'redraw': None,
        }
        entry['width'] = self._measure(text, pixmap)

        def redraw(hovered=False, entry=entry):
            row_width = max(entry['width'], self._max_width)
            entry['label'].setPixmap(self._render_row(entry, row_width, hovered))

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
        separator.setStyleSheet("background-color: rgba(0, 255, 0, 100); margin: 5px 0px;")
        separator.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.layout.addWidget(separator)
        self._items.append(('separator', separator))

        if self._max_width:
            separator.setFixedWidth(self._max_width)
        self.adjustSize()

    def _render_row(self, entry, width: int, hovered: bool) -> QPixmap:
        """把一条菜单项画成一张位图（没有反锯齿，字才是清楚的）。"""
        height = entry['label'].height() or self.ROW_HEIGHT
        pixmap = QPixmap(max(1, int(width)), int(height))
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        painter.setFont(self.hacker_font)
        painter.setPen(QColor("#00FF88" if hovered else "#00FF00"))

        metrics = QFontMetrics(self.hacker_font)
        text_x = 6
        if hovered:
            arrow_width = metrics.horizontalAdvance(" > ")
            painter.drawText(text_x, 0, arrow_width, height, Qt.AlignVCenter, ">")
            text_x += arrow_width
        if entry['pixmap']:
            painter.drawPixmap(text_x, (height - entry['pixmap'].height()) // 2, entry['pixmap'])
            text_x += entry['pixmap'].width() + 6

        painter.drawText(text_x, 0, max(0, width - text_x), height,
                         Qt.AlignVCenter, entry['text'])
        painter.end()
        return pixmap

    def _measure(self, text: str, pixmap) -> int:
        metrics = QFontMetrics(self.hacker_font)
        width = 6 + metrics.horizontalAdvance(" > ") + metrics.horizontalAdvance(text) + 16
        if pixmap:
            width += pixmap.width() + 6
        return width

    def _apply_width(self):
        """把每条 item 拉到同一宽度（= 最宽那条），保证一行铺满、高亮不留空。"""
        for entry in self._action_items:
            entry['width'] = self._measure(entry['text'], entry['pixmap'])
            self._max_width = max(self._max_width, entry['width'])

        for entry in self._action_items:
            entry['label'].setFixedWidth(self._max_width)
            entry['redraw'](False)

        self.box.setFixedWidth(self._max_width + 20)
        self.adjustSize()

    def _announce_closed(self):
        """通知宿主"菜单收起来了"（hide 与 close 可能都来一遍，去重）。"""
        if self._closed_announced:
            return
        self._closed_announced = True
        self.menu_closed.emit()

    def hideEvent(self, event, /):
        # Popup 关掉后鼠标事件才回到宿主手上
        self._announce_closed()
        super().hideEvent(event)

    def closeEvent(self, event, /):
        self._announce_closed()
        super().closeEvent(event)

    def menu_actions(self):
        """已经加进来的 QAction（Qt 的 actions() 拿不到自绘条目）。"""
        return list(self._actions)

    def _emit(self, action):
        self.triggered.emit(action)
        if hasattr(action, 'trigger'):
            action.trigger()
        self.close()

    def exec(self, pos=None):
        self.adjustSize()
        if pos is None:
            pos = QCursor.pos()
        self._closed_announced = False  # 重新弹出来，下一次关闭要再通知一遍
        self.move(pos)
        self.show()
