
from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QIcon, QKeySequence, QPainter, QPainterPath, QPen, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..base import CombinedMeta, IconListABS, MainWindowABS
from .chrome import _Category, _CodeRain, _NavButton, _TitleBar
from .primitives import BreezeScrollArea
from .theme import (
    ACCENT,
    BG,
    BORDER,
    PRIMARY,
    PRIMARY_DEEP,
    RADIUS,
    SURFACE,
    TEXT,
    TEXT_DIM,
    base_sheet,
    font_css,
)


class IconList(IconListABS):
    """菜单图标集：设置 / 聊天 / 关闭，三张都现画（圆角方块 + 字形）。"""

    SETTING = None
    CHAT = None
    SHUTDOWN = None

    def init(self):
        self.draw_gear()
        self.draw_chat()
        self.draw_shutdown()

    def draw_gear(self, size=22):
        """设置：薄荷绿圆角块 + 白色齿轮（八个齿 + 中心孔）。"""
        pixmap = self._badge(size)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#FFFFFF"), 2))

        cx = cy = size / 2
        inner = size * 0.20
        outer = size * 0.34
        for index in range(8):
            from math import cos, radians, sin

            rad = radians(index * 45)
            painter.drawLine(
                int(cx + inner * cos(rad)), int(cy + inner * sin(rad)),
                int(cx + outer * cos(rad)), int(cy + outer * sin(rad)),
            )
        painter.drawEllipse(int(cx - inner * 0.9), int(cy - inner * 0.9),
                            int(inner * 1.8), int(inner * 1.8))
        painter.end()
        self.SETTING = QIcon(pixmap)

    def draw_chat(self, size=22):
        """聊天：雾蓝圆角块 + 白色气泡。"""
        pixmap = self._badge(size, color=ACCENT)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        path = QPainterPath()
        path.addRoundedRect(size * 0.20, size * 0.26, size * 0.60, size * 0.40,
                            size * 0.14, size * 0.14)
        path.moveTo(size * 0.38, size * 0.66)
        path.lineTo(size * 0.34, size * 0.80)
        path.lineTo(size * 0.52, size * 0.66)
        painter.setPen(QPen(QColor("#FFFFFF"), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        painter.end()
        self.CHAT = QIcon(pixmap)

    def draw_shutdown(self, size=22):
        """关闭：暖橙圆角块 + 白色电源符号。"""
        pixmap = self._badge(size, color="#E8A33D")
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#FFFFFF"), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)

        radius = size * 0.24
        cx = cy = size / 2
        painter.drawArc(int(cx - radius), int(cy - radius * 0.8),
                        int(radius * 2), int(radius * 2), 40 * 16, 280 * 16)
        painter.drawLine(int(cx), int(cy - radius * 1.25), int(cx), int(cy - radius * 0.1))
        painter.end()
        self.SHUTDOWN = QIcon(pixmap)

    @staticmethod
    def _badge(size: int, color: str = PRIMARY) -> QPixmap:
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0, 0, size, size, size * 0.30, size * 0.30)
        painter.fillPath(path, QColor(color))
        painter.end()
        return pixmap


class BreezeWindow(QWidget, MainWindowABS, metaclass=CombinedMeta):
    """主窗口：浅色卡片式布局，左边侧栏导航、右边堆叠页。"""

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setFixedSize(940, 640)
        # base_sheet 会顺手把自带中文字体装上（离屏/无系统字体时全靠它）
        self.setStyleSheet(base_sheet())

        self.matrix_bg = _CodeRain(self)
        self.matrix_bg.lower()
        self.matrix_bg.resize(QSize(self.width(), self.height()))

        self.nav_buttons = {}
        self.nav_widgets = {}
        self.categories = {}

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.titleBar = _TitleBar(self, "AI 桌宠 · 轻风")
        main_layout.addWidget(self.titleBar)

        body = QHBoxLayout()
        body.setContentsMargins(12, 12, 12, 12)
        body.setSpacing(12)

        # 侧栏：白底圆角卡片，里面是可折叠的分类
        self.nav_scroll = QScrollArea()
        self.nav_scroll.setWidgetResizable(True)
        self.nav_scroll.setFixedWidth(208)
        self.nav_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.nav_scroll.setStyleSheet(f"""
            QScrollArea {{
                background: {SURFACE};
                border: 1px solid {BORDER};
                border-radius: {RADIUS}px;
            }}
            QScrollArea > QWidget > QWidget {{
                background: transparent;
            }}
        """)

        self.nav_container = QWidget()
        self.nav_container.setStyleSheet("background: transparent;")
        self.nav_layout = QVBoxLayout(self.nav_container)
        self.nav_layout.setContentsMargins(8, 8, 8, 8)
        self.nav_layout.setSpacing(4)
        self.nav_layout.addStretch()
        self.nav_scroll.setWidget(self.nav_container)

        # 右侧页面容器
        self.pages = QStackedWidget()
        self.pages.setStyleSheet(f"""
            QStackedWidget {{
                background: {SURFACE};
                border: 1px solid {BORDER};
                border-radius: {RADIUS}px;
            }}
        """)

        body.addWidget(self.nav_scroll)
        body.addWidget(self.pages, 1)
        main_layout.addLayout(body)

    # -- 契约要求的方法 -----------------------------------------------------
    def create_category(self, category: str, position: str = "top") -> _Category:
        if position not in ("top", "bottom"):
            raise ValueError("position must be 'top' or 'bottom'")

        if category in self.categories:
            return self.categories[category]

        category_widget = _Category(category)
        self.categories[category] = category_widget

        if position == "top":
            self.nav_layout.insertWidget(self.nav_layout.count() - 1, category_widget)
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

        shortcut_text = self.__format_shortcut(shortcut_keys) if shortcut_keys else None

        button = _NavButton(text, shortcut_text)
        button.clicked.connect(lambda w=widget: self._set_active(w))

        if category is not None:
            category_widget = self.categories.get(category)
            if category_widget is None:
                category_widget = self.create_category(category, position)
            category_widget.addWidget(button)
        elif position == "top":
            self.nav_layout.insertWidget(self.nav_layout.count() - 1, button)
        else:
            self.nav_layout.addWidget(button)

        self.pages.addWidget(widget)
        self.nav_buttons[widget] = button
        self.nav_widgets[text] = widget

        if shortcut_keys:
            shortcut = QShortcut(QKeySequence(shortcut_text), self)
            shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
            shortcut.activated.connect(lambda w=widget: self._set_active(w))

        if self.pages.count() == 1:
            self._set_active(widget)

    def setTitle(self, title: str):
        self.titleBar.titleLabel.setText(title)

    def removeNavigation(self, widget: QWidget):
        if widget in self.nav_buttons:
            button = self.nav_buttons.pop(widget)
            button.setParent(None)

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

    # -- 主题自己的方法 -----------------------------------------------------
    def setEnableBorder(self, enabled):
        """桌宠"贴边隐藏"时把窗口描边收掉，看着像没边框。"""
        border = f"1px solid {BORDER}" if enabled else "1px solid transparent"
        self.nav_scroll.setStyleSheet(f"""
            QScrollArea {{
                background: {SURFACE};
                border: {border};
                border-radius: {RADIUS}px;
            }}
            QScrollArea > QWidget > QWidget {{
                background: transparent;
            }}
        """)
        self.pages.setStyleSheet(f"""
            QStackedWidget {{
                background: {SURFACE};
                border: {border};
                border-radius: {RADIUS}px;
            }}
        """)

        for button in self.nav_buttons.values():
            button.setEnableBorder(enabled)

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
        for key in keys:
            result.append(key_map.get(key) or QKeySequence(key).toString())
        return " + ".join(result)

    def _set_active(self, widget):
        for w, button in self.nav_buttons.items():
            button.setActive(w == widget)
        self.pages.setCurrentWidget(widget)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.matrix_bg.resize(self.size())
        self.nav_container.setMinimumWidth(self.nav_scroll.viewport().width())


class PageTitle(QLabel):
    """各设置页顶部那条标题（页面自己拼界面时用）。"""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setFixedHeight(32)
        self.setStyleSheet(f"""
            QLabel {{
                color: {TEXT};
                background: transparent;
                border: none;
                padding-left: 2px;
                {font_css(16, weight=600)}
            }}
        """)


class PageHint(QLabel):
    """页面里的浅色说明行。"""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setWordWrap(True)
        self.setStyleSheet(f"""
            QLabel {{
                color: {TEXT_DIM};
                background: {BG};
                border: 1px solid {BORDER};
                border-radius: {RADIUS}px;
                padding: 6px 10px;
                {font_css(12)}
            }}
        """)


__all__ = ["BreezeWindow", "BreezeScrollArea", "IconList", "PageHint", "PageTitle", "PRIMARY_DEEP"]
