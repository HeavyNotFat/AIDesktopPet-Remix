
from __future__ import annotations

import json

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .theme import (
    ACCENT,
    ACCENT_SOFT,
    BG,
    BORDER,
    PRIMARY,
    PRIMARY_DEEP,
    PRIMARY_SOFT,
    RADIUS_SMALL,
    SURFACE,
    SURFACE_SOFT,
    TEXT,
    TEXT_DIM,
    font_css,
)
from ..base import icon_pixmap

# 动作/表情的中文名 → Animation 对象上的字段名
MAPPING_ANIMATION = {
    "捏耳朵": "ClickEar",
    "拍拍头": "ClickHead",
    "拍胸脯": "ClickChest",
    "按肚子": "ClickBody",
    "捏捏腿": "ClickLeg",
    "摸耳朵": "TorchEar",
    "摸摸头": "TorchHead",
    "摸肚子": "TorchBody",
    "摸摸腿": "TorchLeg",
}
MAPPING_SPECTIAL_ANIMATION = {
    "程序启动": "AppInitial",
    "程序退出": "AppExit",
}

with open("./resources/prompts.json", "r", encoding="utf-8") as f:
    prompts = json.load(f)
    f.close()


class _SoftBackdrop(QWidget):
    """窗口背景：淡蓝渐变 + 几个柔光圆斑。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.blobs = [
            # (x 比例, y 比例, 半径, 颜色, 透明度)
            (0.82, 0.12, 260, QColor(PRIMARY), 26),
            (0.12, 0.78, 320, QColor(ACCENT), 22),
            (0.55, 0.45, 200, QColor(PRIMARY), 14),
        ]

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        gradient = QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0.0, QColor("#FBFDFE"))
        gradient.setColorAt(1.0, QColor(BG))
        painter.fillRect(self.rect(), gradient)

        painter.setPen(Qt.PenStyle.NoPen)
        for fx, fy, radius, color, alpha in self.blobs:
            tint = QColor(color)
            tint.setAlpha(alpha)
            painter.setBrush(tint)
            cx, cy = self.width() * fx, self.height() * fy
            painter.drawEllipse(int(cx - radius), int(cy - radius), radius * 2, radius * 2)

        painter.end()


# 主窗口里沿用旧名字
_CodeRain = _SoftBackdrop


class _TitleBar(QWidget):
    """标题栏：左边小徽章 + 标题，右边三个圆形窗口按钮。"""

    def __init__(self, parent=None, title=""):
        super().__init__(parent)
        self.parent = parent
        self.setFixedHeight(44)
        self.startPos = None

        self.setStyleSheet(f"""
            QWidget {{
                background: {SURFACE};
                border-bottom: 1px solid {BORDER};
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 10, 0)
        layout.setSpacing(8)

        self.badge = QLabel("轻")
        self.badge.setFixedSize(24, 24)
        self.badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.badge.setStyleSheet(f"""
            QLabel {{
                color: {PRIMARY_DEEP};
                background: {PRIMARY_SOFT};
                border: none;
                border-radius: 12px;
                {font_css(12, weight=700)}
            }}
        """)
        layout.addWidget(self.badge)

        self.titleLabel = QLabel(title)
        self.titleLabel.setStyleSheet(f"""
            QLabel {{
                color: {TEXT};
                background: transparent;
                border: none;
                {font_css(14, weight=600)}
            }}
        """)
        layout.addWidget(self.titleLabel)
        layout.addStretch()

        self.minButton = _WindowButton("–", "最小化")
        self.maxButton = _WindowButton("□", "最大化")
        self.closeButton = _WindowButton("×", "关闭", danger=True)
        for button in (self.minButton, self.maxButton, self.closeButton):
            layout.addWidget(button)

        self.minButton.clicked.connect(self.parent.showMinimized)
        self.maxButton.clicked.connect(self.toggleMaximize)
        self.closeButton.clicked.connect(self.parent.close)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.startPos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if self.startPos:
            delta = event.globalPosition().toPoint() - self.startPos
            self.parent.move(self.parent.pos() + delta)
            self.startPos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        self.startPos = None

    def toggleMaximize(self):
        if self.parent.isMaximized():
            self.parent.showNormal()
        else:
            self.parent.showMaximized()


class _WindowButton(QPushButton):
    """标题栏按钮：圆形、悬停浅底，关闭键悬停变红。"""

    def __init__(self, text: str, tooltip: str = "", danger: bool = False):
        super().__init__(text)
        self.danger = danger
        self.setFixedSize(26, 26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tooltip)
        hover_bg = "#FBE3E1" if danger else ACCENT_SOFT
        hover_fg = "#C9524B" if danger else ACCENT
        self.setStyleSheet(f"""
            QPushButton {{
                color: {TEXT_DIM};
                background: transparent;
                border: none;
                border-radius: 13px;
                {font_css(13)}
            }}
            QPushButton:hover {{
                background: {hover_bg};
                color: {hover_fg};
            }}
            QPushButton:pressed {{
                background: {SURFACE_SOFT};
            }}
        """)


class _Category(QWidget):
    """侧栏分类头：点一下折叠/展开里面的导航项。"""

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.expanded = True

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(2)

        self.header = QPushButton(f"▾  {text}")
        self.header.setCheckable(True)
        self.header.setChecked(True)
        self.header.setCursor(Qt.CursorShape.PointingHandCursor)
        self.header.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.header.setStyleSheet(f"""
            QPushButton {{
                color: {TEXT_DIM};
                background: transparent;
                border: none;
                border-radius: {RADIUS_SMALL}px;
                padding: 6px 8px;
                text-align: left;
                {font_css(12, weight=600)}
            }}
            QPushButton:hover {{
                background: {SURFACE_SOFT};
                color: ACCENT;
            }}
        """)

        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(6, 0, 0, 0)
        self.content_layout.setSpacing(3)

        self.layout.addWidget(self.header)
        self.layout.addWidget(self.content)

        self.header.clicked.connect(self._toggle)

    def _toggle(self, checked: bool):
        self.expanded = checked
        self.content.setVisible(checked)
        text = self.header.text()[3:].strip()
        self.header.setText(("▾  " if checked else "▸  ") + text)

    def addWidget(self, widget: QWidget):
        self.content_layout.addWidget(widget)

    def removeWidget(self, widget: QWidget):
        self.content_layout.removeWidget(widget)


class _NavButton(QWidget):
    """侧栏导航项：左边一条主色指示条 + 文字。"""

    clicked = Signal()

    def __init__(self, text: str, shortcut: str | None = None, icon=None):
        super().__init__()
        self.setObjectName("BreezeNavButton")
        self.setFixedHeight(36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.indicator = QWidget(self)
        self.indicator.setGeometry(0, 8, 3, 20)
        self.indicator.setStyleSheet("background: transparent; border-radius: 2px;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 10, 0)
        layout.setSpacing(6)

        pixmap = icon_pixmap(icon, 16)
        if pixmap is not None:
            mark = QLabel()
            mark.setFixedSize(16, 16)
            mark.setPixmap(pixmap)
            mark.setStyleSheet("background: transparent; border: none;")
            layout.addWidget(mark)

        self.label = QLabel(text)
        self.label.setStyleSheet(f"color: {TEXT}; background: transparent; border: none; {font_css(13)}")

        self.shortcut = QLabel(shortcut or "")
        self.shortcut.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.shortcut.setStyleSheet(
            f"color: {TEXT_DIM}; background: transparent; border: none; {font_css(11)}"
        )
        if not shortcut:
            self.shortcut.hide()

        layout.addWidget(self.label)
        layout.addStretch()
        layout.addWidget(self.shortcut)

        self._active = False
        self._bordered = True
        self._update_style()

    def mousePressEvent(self, event):
        self.clicked.emit()

    def setActive(self, active: bool):
        self._active = active
        self._update_style()

    def setEnableBorder(self, enabled: bool):
        self._bordered = enabled
        self._update_style()

    def _update_style(self):
        if self._active:
            self.setStyleSheet(f"""
                QWidget#BreezeNavButton {{
                    background: {PRIMARY_SOFT};
                    border: 1px solid {PRIMARY};
                    border-radius: {RADIUS_SMALL}px;
                }}
            """)
            self.indicator.setStyleSheet(f"background: {PRIMARY}; border-radius: 2px;")
            self.label.setStyleSheet(
                f"color: {PRIMARY_DEEP}; background: transparent; border: none; {font_css(13, weight=600)}"
            )
            return

        border = f"1px solid {BORDER}" if self._bordered else "1px solid transparent"
        self.setStyleSheet(f"""
            QWidget#BreezeNavButton {{
                background: {SURFACE};
                border: {border};
                border-radius: {RADIUS_SMALL}px;
            }}
            QWidget#BreezeNavButton:hover {{
                background: {ACCENT_SOFT};
                border: 1px solid {ACCENT};
            }}
        """)
        self.indicator.setStyleSheet("background: transparent; border-radius: 2px;")
        self.label.setStyleSheet(f"color: {TEXT}; background: transparent; border: none; {font_css(13)}")


def soft_shadow(widget: QWidget, blur: int = 18, dy: int = 3, alpha: int = 26):
    """给控件挂一层很淡的投影。"""
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur)
    effect.setOffset(0, dy)
    effect.setColor(QColor(44, 62, 80, alpha))
    widget.setGraphicsEffect(effect)
    return effect


def rounded_pixmap(size: int, color: str, glyph: str = "", glyph_color: str = "#FFFFFF"):
    """画一个圆角方块图标（菜单图标集用）。"""
    from PySide6.QtGui import QPixmap

    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    path = QPainterPath()
    path.addRoundedRect(0, 0, size, size, size * 0.30, size * 0.30)
    painter.fillPath(path, QColor(color))

    if glyph:
        font = QFont()
        font.setPointSizeF(size * 0.40)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(glyph_color))
        painter.drawText(0, 0, size, size, Qt.AlignmentFlag.AlignCenter, glyph)
    painter.end()
    return pixmap


__all__ = [
    "MAPPING_ANIMATION",
    "MAPPING_SPECTIAL_ANIMATION",
    "_Category",
    "_CodeRain",
    "_NavButton",
    "_SoftBackdrop",
    "_TitleBar",
    "_WindowButton",
    "prompts",
    "rounded_pixmap",
    "soft_shadow",
]
