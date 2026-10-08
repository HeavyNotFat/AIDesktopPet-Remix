
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QSize, QTimer, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
)

from ... import SharingData
from .theme import (
    LEVEL_COLORS,
    RADIUS,
    SURFACE,
    TEXT,
    font_css,
    install_ui_font,
)

GLYPHS = {"info": "i", "success": "✓", "warning": "!", "error": "×"}


class BreezeNotify(QFrame):
    """操作反馈条：优先贴在当前窗口顶部，没有窗口时才浮到屏幕右下角。"""

    LEVELS = LEVEL_COLORS
    MARGIN = 16
    GAP = 8
    TOP = 52
    MIN_WIDTH = 320
    MAX_WIDTH = 560
    _stack = []

    def __init__(self, text, level="info", timeout=3200, parent=None):
        if QApplication.instance() is None:
            raise RuntimeError("没有 QApplication，无法显示提示")

        # 提示条经常不是主窗口的子控件，得自己保证字体装好了（否则中文变方框）
        install_ui_font()

        # parent 传什么都行：这里统一解析成"要贴进去的窗口"，解析不到才当浮层
        parent = self._resolve_host(parent)
        super().__init__(parent)

        color, soft = self.LEVELS.get(level, self.LEVELS["info"])
        self._host = parent
        self._window_mode = parent is None
        self._color = color

        if self._window_mode:
            self.setWindowFlags(
                Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus
            )
            self.setAttribute(Qt.WA_ShowWithoutActivating)
        else:
            self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_TranslucentBackground)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 8, 10, 10)
        outer.setSpacing(0)

        inner = QFrame(self)
        inner.setObjectName("inner")
        outer.addWidget(inner)

        shadow = QGraphicsDropShadowEffect(inner)
        shadow.setBlurRadius(22)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(44, 62, 80, 50))
        inner.setGraphicsEffect(shadow)

        inner.setStyleSheet(f"""
            QFrame#inner {{
                background: {SURFACE};
                border: 1px solid {soft};
                border-left: 4px solid {color};
                border-radius: {RADIUS}px;
            }}
        """)

        row = QHBoxLayout(inner)
        row.setContentsMargins(12, 10, 14, 10)
        row.setSpacing(10)

        badge = _Badge(GLYPHS.get(level, "i"), color, soft)
        row.addWidget(badge, 0, Qt.AlignmentFlag.AlignVCenter)

        label = QLabel(str(text))
        label.setWordWrap(True)
        label.setStyleSheet(f"QLabel {{ color: {TEXT}; background: transparent; border: none; {font_css(13)} }}")
        row.addWidget(label, 1)

        self.setMinimumWidth(self.MIN_WIDTH)
        self.setMaximumWidth(self._max_width())
        self.adjustSize()

        type(self)._stack.append(self)
        self._place()
        self.show()
        self.raise_()
        self._animate_in()
        QTimer.singleShot(max(600, int(timeout)), self.dismiss)

    @staticmethod
    def _resolve_host(parent):
        """能贴窗口就贴窗口，贴不上才用浮层。"""
        if parent is not None:
            return parent.window() if hasattr(parent, "window") else parent

        app = QApplication.instance()
        active = app.activeWindow() if app is not None else None
        if active is not None and active.isVisible():
            return active

        for candidate in (
            SharingData.setting_window,
            SharingData.chat_window,
            SharingData.mainloop_ui,
        ):
            if candidate is not None and getattr(candidate, "isVisible", lambda: False)():
                return candidate
        return None

    def _max_width(self):
        if self._host is None:
            return self.MAX_WIDTH
        return max(self.MIN_WIDTH, min(self.MAX_WIDTH, self._host.width() - 2 * self.MARGIN))

    def _place(self):
        """贴窗口顶部（或屏幕右下角）：后到的排在已有的**下面**，读起来才是从上到下。

        进来时 self 已经进过 `_stack` 了，所以算高度要把自己排除掉。
        """
        others = [
            item for item in type(self)._stack
            if item is not self and item._host is self._host and item.isVisible()
        ]

        if self._window_mode:
            screen = QApplication.primaryScreen()
            if screen is None:
                return
            area = screen.availableGeometry()
            offset = self.MARGIN + sum(item.height() + self.GAP for item in others)
            self.move(area.right() - self.width() - self.MARGIN, area.bottom() - self.height() - offset)
            return

        offset = self.TOP + sum(item.height() + self.GAP for item in others)
        self.move(max(self.MARGIN, (self._host.width() - self.width()) // 2), offset)

    def _animate_in(self):
        if self._window_mode:
            self.setWindowOpacity(0.0)
            self._fade_in = QPropertyAnimation(self, b"windowOpacity", self)
            self._fade_in.setDuration(160)
            self._fade_in.setStartValue(0.0)
            self._fade_in.setEndValue(1.0)
            self._fade_in.start()
            return

        # 子控件没有 windowOpacity，改成从上方滑进来
        target = self.pos()
        self._slide_in = QPropertyAnimation(self, b"pos", self)
        self._slide_in.setDuration(200)
        self._slide_in.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._slide_in.setStartValue(target - QPoint(0, 14))
        self._slide_in.setEndValue(target)
        self._slide_in.start()

    def dismiss(self):
        if self._window_mode:
            self._fade_out = QPropertyAnimation(self, b"windowOpacity", self)
            self._fade_out.setDuration(260)
            self._fade_out.setStartValue(self.windowOpacity())
            self._fade_out.setEndValue(0.0)
            self._fade_out.finished.connect(self._drop)
            self._fade_out.start()
            return

        self._slide_out = QPropertyAnimation(self, b"pos", self)
        self._slide_out.setDuration(200)
        self._slide_out.setEasingCurve(QEasingCurve.Type.InCubic)
        self._slide_out.setStartValue(self.pos())
        self._slide_out.setEndValue(self.pos() - QPoint(0, 14))
        self._slide_out.finished.connect(self._drop)
        self._slide_out.start()

    def _drop(self):
        if self in type(self)._stack:
            type(self)._stack.remove(self)
        self.hide()
        self.close()
        self.deleteLater()


class _Badge(QLabel):
    """左边的圆形图标：语义色实心圆 + 白色字形。"""

    def __init__(self, glyph: str, color: str, soft: str):
        super().__init__(glyph)
        self._color = color
        self._soft = soft
        self.setFixedSize(22, 22)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(f"""
            QLabel {{
                color: #FFFFFF;
                background: {color};
                border: none;
                border-radius: 11px;
                {font_css(13, weight=700)}
            }}
        """)

    def sizeHint(self):
        return QSize(22, 22)


__all__ = ["BreezeNotify", "GLYPHS"]
