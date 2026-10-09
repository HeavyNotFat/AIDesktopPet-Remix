
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
)
from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QTimer, Qt
from PySide6.QtGui import QColor

from ... import SharingData


class HackerNotify(QFrame):
    """操作反馈条：贴在当前窗口顶部，没有窗口时浮到屏幕右下角。"""

    LEVELS = {
        "info": ("#0e1c0e", "#00FF00", "i"),
        "success": ("#0b2416", "#3ddc84", "✓"),
        "warning": ("#2a2306", "#ffcc00", "!"),
        "error": ("#2e1013", "#ff6b6b", "×"),
    }
    MARGIN = 18
    GAP = 8
    TOP = 58
    MIN_WIDTH = 360
    MAX_WIDTH = 620
    _stack = []

    def __init__(self, text, level="info", timeout=3200, parent=None):
        if QApplication.instance() is None:
            raise RuntimeError("没有 QApplication，无法显示提示")

        parent = self._resolve_host(parent)
        super().__init__(parent)

        background, color, glyph = self.LEVELS.get(level, self.LEVELS["info"])
        self._host = parent
        self._window_mode = parent is None

        if self._window_mode:
            self.setWindowFlags(
                Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus
            )
            self.setAttribute(Qt.WA_ShowWithoutActivating)
        else:
            self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_TranslucentBackground)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 12)
        outer.setSpacing(0)

        inner = QFrame(self)
        outer.addWidget(inner)

        shadow = QGraphicsDropShadowEffect(inner)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 210))
        inner.setGraphicsEffect(shadow)

        inner.setStyleSheet(f"""
            QFrame {{
                background: {background};
                border: 2px solid {color};
                border-left: 7px solid {color};
                border-radius: 10px;
            }}
        """)

        row = QHBoxLayout(inner)
        row.setContentsMargins(14, 12, 16, 12)
        row.setSpacing(12)

        badge = QLabel(glyph)
        badge.setFixedSize(24, 24)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(f"""
            QLabel {{
                color: {background};
                background: {color};
                border: none;
                border-radius: 12px;
                font-family: Consolas, "JetBrains Mono", monospace;
                font-size: 15px;
                font-weight: bold;
            }}
        """)

        label = QLabel(str(text))
        label.setWordWrap(True)
        label.setStyleSheet(f"""
            QLabel {{
                color: {color};
                background: transparent;
                border: none;
                font-family: Consolas, "JetBrains Mono", monospace;
                font-size: 14px;
                font-weight: 600;
            }}
        """)

        row.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)
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
        """解析提示条要贴进去的窗口，解析不到返回 None。"""
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

    def _siblings(self):
        return [
            item for item in type(self)._stack
            if item is not self and item._host is self._host and item.isVisible()
        ]

    def _place(self):
        if self._window_mode:
            screen = QApplication.primaryScreen()
            if screen is None:
                return
            area = screen.availableGeometry()
            offset = self.MARGIN + sum(item.height() + self.GAP for item in self._siblings())
            self.move(area.right() - self.width() - self.MARGIN, area.bottom() - self.height() - offset)
            return

        offset = self.TOP + sum(item.height() + self.GAP for item in self._siblings())
        self.move(max(self.MARGIN, (self._host.width() - self.width()) // 2), offset)

    def _animate_in(self):
        if self._window_mode:
            self.setWindowOpacity(0.0)
            self._fade_in = QPropertyAnimation(self, b"windowOpacity", self)
            self._fade_in.setDuration(180)
            self._fade_in.setStartValue(0.0)
            self._fade_in.setEndValue(1.0)
            self._fade_in.start()
            return

        # 子控件没有 windowOpacity，改成从上方滑进来
        target = self.pos()
        self._slide_in = QPropertyAnimation(self, b"pos", self)
        self._slide_in.setDuration(220)
        self._slide_in.setEasingCurve(QEasingCurve.Type.OutBack)
        self._slide_in.setStartValue(target - QPoint(0, 18))
        self._slide_in.setEndValue(target)
        self._slide_in.start()

    def dismiss(self):
        if self._window_mode:
            self._fade_out = QPropertyAnimation(self, b"windowOpacity", self)
            self._fade_out.setDuration(320)
            self._fade_out.setStartValue(self.windowOpacity())
            self._fade_out.setEndValue(0.0)
            self._fade_out.finished.connect(self._drop)
            self._fade_out.start()
            return

        self._slide_out = QPropertyAnimation(self, b"pos", self)
        self._slide_out.setDuration(240)
        self._slide_out.setEasingCurve(QEasingCurve.Type.InCubic)
        self._slide_out.setStartValue(self.pos())
        self._slide_out.setEndValue(self.pos() - QPoint(0, 18))
        self._slide_out.finished.connect(self._drop)
        self._slide_out.start()

    def _drop(self):
        if self in type(self)._stack:
            type(self)._stack.remove(self)
        self.hide()
        self.close()
        self.deleteLater()
