"""hacker 主题的主窗口：标题栏 + 侧栏导航 + 堆叠页 + 快捷键，外加菜单图标集 `IconList`。

`IconList` 的三张图标是画出来的（齿轮 / 气泡 / 关机），桌宠右键菜单和 shader 都用它。
"""

import math

from PySide6.QtWidgets import (
    QHBoxLayout,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QKeySequence, QPainter, QPainterPath, QPen, QPixmap, QShortcut

from ..base import CombinedMeta, IconListABS, MainWindowABS

from .chrome import _CodeRain, _HackerCategory, _HackerNavButton, _HackerTitleBar


class IconList(IconListABS):
    SETTING = None
    CHAT = None
    SHUTDOWN = None

    def init(self):
        self.draw_gear()
        self.draw_chat()
        self.draw_shutdown()

    def draw_gear(self, size=24, teeth=8, color=QColor(0, 255, 0)):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QBrush(color))
        painter.setPen(QPen(color, 2))

        cx, cy = size / 2, size / 2
        r_outer = size / 2 - 2
        r_inner = r_outer * 0.6

        for i in range(teeth):
            angle = i * (360 / teeth)
            rad = math.radians(angle)
            x1 = cx + r_inner * math.cos(rad)
            y1 = cy + r_inner * math.sin(rad)
            x2 = cx + r_outer * math.cos(rad)
            y2 = cy + r_outer * math.sin(rad)
            painter.drawLine(int(x1), int(y1), int(x2), int(y2))

        painter.setBrush(QBrush(color))
        painter.drawEllipse(int(cx - r_inner * 0.6), int(cy - r_inner * 0.6), int(r_inner * 1.2), int(r_inner * 1.2))

        painter.end()
        self.SETTING = QIcon(pixmap)

    def draw_chat(self, size=24, color=QColor(0, 255, 0)):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QBrush(color))
        painter.setPen(QPen(color, 2))

        path = QPainterPath()
        path.moveTo(4, 8)
        path.lineTo(size - 4, 8)
        path.lineTo(size - 4, size - 8)
        path.lineTo(size / 2 + 4, size - 8)
        path.lineTo(size / 2, size - 4)
        path.lineTo(size / 2 - 4, size - 8)
        path.lineTo(4, size - 8)
        path.closeSubpath()

        painter.drawPath(path)
        painter.end()
        self.CHAT = QIcon(pixmap)

    def draw_shutdown(self, size=24, color=QColor(0, 255, 0)):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QBrush(color))
        painter.setPen(QPen(color, 3))

        center_x, center_y = size // 2, size // 2
        radius = size // 3

        painter.drawEllipse(center_x - radius, center_y - radius,
                            radius * 2, radius * 2)

        line_y = center_y + radius - 4
        line_length = radius * 1.2
        painter.drawLine(
            center_x - line_length // 2,
            line_y,
            center_x + line_length // 2,
            line_y
        )

        painter.end()
        self.SHUTDOWN = QIcon(pixmap)


class HackerWindow(QWidget, MainWindowABS, metaclass=CombinedMeta):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setFixedSize(900, 600)
        self.setStyleSheet("background-color: #1e1f22;")

        self.matrix_bg = _CodeRain(self)
        self.matrix_bg.lower()
        self.matrix_bg.resize(QSize(self.width(), self.height() * 2))

        self.nav_buttons = {}
        self.nav_widgets = {}
        self.categories = {}

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.titleBar = _HackerTitleBar(self, "Hacker UI")
        main_layout.addWidget(self.titleBar)

        body = QHBoxLayout()
        body.setContentsMargins(10, 10, 10, 10)
        body.setSpacing(10)

        self.nav_scroll = QScrollArea()
        self.nav_scroll.setWidgetResizable(True)
        self.nav_scroll.setFixedWidth(200)
        self.nav_scroll.setStyleSheet("""
            QScrollArea {
                border: 1px solid #00FF00;
                border-radius: 8px;
                background: rgba(0,0,0,120);
            }
        """)

        self.nav_container = QWidget()
        self.nav_layout = QVBoxLayout(self.nav_container)
        self.nav_layout.setSpacing(4)
        self.nav_layout.addStretch()

        self.nav_scroll.setWidget(self.nav_container)

        self.pages = QStackedWidget()
        self.pages.setStyleSheet("""
            QStackedWidget {
                background: rgba(0,0,0,200);
                border: 1px solid #00FF00;
                border-radius: 12px;
            }
        """)

        body.addWidget(self.nav_scroll)
        body.addWidget(self.pages)
        main_layout.addLayout(body)

    def create_category(
            self,
            category: str,
            position: str = "top",
    ) -> _HackerCategory:

        if position not in ("top", "bottom"):
            raise ValueError("position must be 'top' or 'bottom'")

        if category in self.categories:
            return self.categories[category]

        category_widget = _HackerCategory(category)

        self.categories[category] = category_widget

        if position == "top":
            self.nav_layout.insertWidget(
                self.nav_layout.count() - 1,
                category_widget
            )
        else:
            self.nav_layout.addWidget(category_widget)

        return category_widget

    def addNavigation(
            self,
            text: str,
            widget: QWidget,
            shortcut_keys: tuple[int, ...] | None = None,
            position: str = "top",
            category: str | None = None,
    ):
        if position not in ("top", "bottom"):
            raise ValueError("position must be 'top' or 'bottom'")

        shortcut_text = (
            self.__format_shortcut(shortcut_keys)
            if shortcut_keys
            else None
        )

        btn = _HackerNavButton(text, shortcut_text)
        btn.clicked.connect(
            lambda w=widget: self._set_active(w)
        )

        if category is not None:
            category_widget = self.categories.get(category)

            if category_widget is None:
                category_widget = self.create_category(
                    category,
                    position
                )

            category_widget.addWidget(btn)

        else:
            if position == "top":
                self.nav_layout.insertWidget(
                    self.nav_layout.count() - 1,
                    btn
                )
            else:
                self.nav_layout.addWidget(btn)

        self.pages.addWidget(widget)

        self.nav_buttons[widget] = btn
        self.nav_widgets[text] = widget

        if shortcut_keys:
            seq = QKeySequence(shortcut_text)

            shortcut = QShortcut(seq, self)

            shortcut.setContext(
                Qt.ShortcutContext.ApplicationShortcut
            )

            shortcut.activated.connect(
                lambda w=widget: self._set_active(w)
            )

        if self.pages.count() == 1:
            self._set_active(widget)

    def setTitle(self, title: str):
        self.titleBar.titleLabel.setText(title)

    def removeNavigation(self, widget: QWidget):
        if widget in self.nav_buttons:
            btn = self.nav_buttons.pop(widget)
            btn.setParent(None)

        for text in [key for key, value in self.nav_widgets.items() if value is widget]:
            self.nav_widgets.pop(text, None)

        if widget.parent() is self.pages:
            self.pages.removeWidget(widget)
        widget.setParent(None)

    def remove_category(self, category: str):
        """移除一个分类头（里面的条目要用 removeNavigation 先摘掉）。"""
        widget = self.categories.pop(category, None)
        if widget is None:
            return False

        self.nav_layout.removeWidget(widget)
        widget.setParent(None)
        widget.deleteLater()
        return True

    def setEnableBorder(self, enabled):
        if enabled:
            self.setStyleSheet("background-color: #1e1f22; border: 1px solid #00FF00;")
            self.titleBar.setStyleSheet("""
                   background: #1e1f22;
                   color: #00FF00;
               """)
            self.nav_scroll.setStyleSheet("QScrollArea { border: 1px solid #00FF00; }")
            self.pages.setStyleSheet(
                "QWidget { background: rgba(0,0,0,200); border-radius: 12px; border: 1px solid #00FF00; }")
        else:
            self.setStyleSheet("background-color: #1e1f22; border: none;")
            self.titleBar.setStyleSheet("""
                   background: #1e1f22;
                   color: #00FF00;
               """)
            self.nav_scroll.setStyleSheet("QScrollArea { border: none; }")
            self.pages.setStyleSheet("QWidget { background: rgba(0,0,0,200); border-radius: 12px; border: none; }")

        for btn in self.nav_buttons.values():
            btn.setEnableBorder(enabled)

        for widget in self.nav_widgets.values():
            if hasattr(widget, 'setEnableBorder'):
                widget.setEnableBorder(enabled)

    @staticmethod
    def __format_shortcut(keys: tuple[int, ...]) -> str:
        key_map = {
            Qt.Key.Key_Control: "Ctrl",
            Qt.Key.Key_Shift: "Shift",
            Qt.Key.Key_Alt: "Alt",
            Qt.Key.Key_Meta: "Meta",
        }
        result = []
        for k in keys:
            if k in key_map:
                result.append(key_map[k])
            else:
                result.append(QKeySequence(k).toString())
        return " + ".join(result)

    def _set_active(self, widget):
        for w, btn in self.nav_buttons.items():
            btn.setActive(w == widget)
        self.pages.setCurrentWidget(widget)

    def resizeEvent(self, event):
        super().resizeEvent(event)

        self.matrix_bg.resize(self.size())

        self.nav_container.setMinimumWidth(
            self.nav_scroll.viewport().width()
        )
