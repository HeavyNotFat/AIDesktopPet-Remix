"""桌宠主窗口的"外壳"零件：标题栏、代码雨背景、侧栏分类与导航按钮。

`HackerWindow`（window.py）拿这些拼出主窗口；它们只跟 Qt 打交道，不碰主题里其它控件。
"""

import json
import random

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter


class _HackerTitleBar(QWidget):
    def __init__(self, parent=None, title=""):
        super().__init__(parent)
        self.parent = parent
        self.setFixedHeight(36)

        self.setStyleSheet("""
            background: #1e1f22;
            color: #00FF00;
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)

        self.titleLabel = QLabel(title)
        self.titleLabel.setFont(QFont("Consolas", 12))
        layout.addWidget(self.titleLabel)
        layout.addStretch()

        self.minButton = QPushButton("_")
        self.maxButton = QPushButton("口")
        self.closeButton = QPushButton("X")

        for btn in (self.minButton, self.maxButton, self.closeButton):
            btn.setFixedSize(24, 24)
            btn.setStyleSheet("""
                QPushButton {
                    background: #2b2d30;
                    color: #00FF00;
                    border: none;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background: rgba(0,255,0,50);
                    color: #00FF88;
                }
            """)

        self.minButton.clicked.connect(self.parent.showMinimized)
        self.maxButton.clicked.connect(self.toggleMaximize)
        self.closeButton.clicked.connect(self.parent.close)

        layout.addWidget(self.minButton)
        layout.addWidget(self.maxButton)
        layout.addWidget(self.closeButton)

        self.startPos = None

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


class _CodeRain(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self.chars = ["1", "0"] * 5

        self.columns = []
        self.font_size = 14
        self.font = QFont("Consolas", self.font_size)

        self.column_count = 0
        self.update_column_count()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_rain)
        self.timer.start(60)

        self.setMouseTracking(True)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_column_count()

    def update_column_count(self):
        width = self.width()
        self.column_count = width // self.font_size + 1
        while len(self.columns) < self.column_count:
            self.columns.append({
                'y': random.randint(-200, -20),
                'speed': random.uniform(0.8, 1.5),
                'length': random.randint(8, 35),
                'head_char': random.choice(self.chars),
                'fade_chars': []
            })

    def update_rain(self):
        # 更新每一列
        for col in self.columns:
            col['y'] += col['speed'] * self.font_size * 0.7

            # 头部字符随机变化
            if random.random() < 0.15:
                col['head_char'] = random.choice(self.chars)

            # 当头部进入可视区域时，添加字符到拖尾
            if col['y'] > 0:
                # 拖尾长度控制
                if len(col['fade_chars']) > col['length']:
                    col['fade_chars'].pop(0)

                col['fade_chars'].append(col['head_char'])

            # 超出底部就重置到顶部
            if col['y'] > self.height() + 100:
                col['y'] = random.randint(-150, -20)
                col['length'] = random.randint(8, 35)
                col['fade_chars'].clear()

        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.setFont(self.font)

        col_width = self.font_size
        for i, col in enumerate(self.columns):
            x = i * col_width

            for j, char in enumerate(col['fade_chars']):
                alpha = int(255 * (j + 1) / (len(col['fade_chars']) + 1))
                alpha = max(30, min(255, alpha))

                if j == len(col['fade_chars']) - 1:
                    color = QColor(180, 255, 180)
                else:
                    if random.random() < 0.21:
                        color = QColor(255, 80, 80)
                    else:
                        color = QColor(0, 180, 0)
                    color.setAlpha(alpha)

                painter.setPen(color)
                y = col['y'] - (len(col['fade_chars']) - j) * self.font_size
                painter.drawText(x, int(y), char)

        painter.end()


class _HackerCategory(QWidget):
    def __init__(self, text: str, parent=None):
        super().__init__(parent)

        self.expanded = True

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(2)

        self.header = QToolButton()
        self.header.setText(f"▼  {text}")
        self.header.setCheckable(True)
        self.header.setChecked(True)
        self.header.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextOnly
        )
        self.header.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed
        )

        self.header.setStyleSheet("""
            QToolButton {
                color: #00FF00;
                background: rgba(0, 255, 0, 20);
                border: none;
                border-radius: 4px;
                padding: 7px 8px;
                text-align: left;
                font-weight: bold;
            }

            QToolButton:hover {
                background: rgba(0, 255, 0, 45);
            }
        """)

        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(8, 0, 0, 0)
        self.content_layout.setSpacing(4)

        self.layout.addWidget(self.header)
        self.layout.addWidget(self.content)

        self.header.clicked.connect(self._toggle)

    def _toggle(self, checked: bool):
        self.expanded = checked
        self.content.setVisible(checked)

        text = self.header.text()
        if checked:
            self.header.setText(
                "▼  " + text[3:].strip()
            )
        else:
            self.header.setText(
                "▶  " + text[3:].strip()
            )

    def addWidget(self, widget: QWidget):
        self.content_layout.addWidget(widget)

    def removeWidget(self, widget: QWidget):
        self.content_layout.removeWidget(widget)


class _HackerNavButton(QWidget):
    clicked = Signal()

    def __init__(self, text: str, shortcut: str | None = None):
        super().__init__()
        self.setFixedHeight(36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed
        )

        self.label = QLabel(text)
        self.label.setStyleSheet("color: #00FF00;border: none;background: transparent;")

        self.shortcut = QLabel(shortcut or "")
        self.shortcut.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.shortcut.setStyleSheet("color: rgba(0,255,0,150);border: none;background: transparent;")

        if not shortcut:
            self.shortcut.hide()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(6)
        layout.addWidget(self.label)
        layout.addStretch()
        layout.addWidget(self.shortcut)

        self._active = False
        self._update_style()

    def mousePressEvent(self, event):
        self.clicked.emit()

    def setActive(self, active: bool):
        self._active = active
        self._update_style()

    def setEnableBorder(self, enabled: bool):
        self._update_style(enabled)

    def _update_style(self, enabled: bool = True):
        if not enabled:
            self.setStyleSheet("background: transparent;")
            return

        if self._active:
            self.setStyleSheet("""
                background: rgba(0,255,0,40);
                border: 1px solid #00FF00;
                border-radius: 6px;
            """)
        else:
            self.setStyleSheet("""
                background: transparent;
                border: 1px solid transparent;
            """)


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
