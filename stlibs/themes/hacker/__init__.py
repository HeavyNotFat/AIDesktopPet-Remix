import math
import random

from . import general
from . import llm
from . import tts
from . import settings
from . import animation

from ... import derfer
from ... import SharingData
from ...ai import local
from ...ai import cloud

from PySide6.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout, QSizePolicy, QHBoxLayout, QStackedWidget, QPushButton, \
    QScrollArea, QLineEdit, QTextEdit, QSlider, QComboBox, QTabWidget, QFrame, QToolButton, QTableWidget, QHeaderView, QAbstractItemView
from PySide6.QtCore import Qt, Signal, QSize, QTimer, QPropertyAnimation, QEasingCurve, QRectF, Property
from PySide6.QtGui import QAction, QCursor, QFontDatabase, QFont, QIcon, QPainter, QBrush, QColor, QPen, QPixmap, \
    QFontMetrics, QKeySequence, QShortcut, QPainterPath

cache_llm_class = {}


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


class Action(QAction):
    def __init__(self, text, parent=None, icon: QIcon = None):
        super().__init__(text, parent)
        if icon is not None:
            self.setIcon(icon)


# Chat
class HackerChatBubble(QFrame):
    MAX_WIDTH_RATIO = 0.60

    def __init__(self, text: str = "", image: str | QPixmap | None = None, is_user: bool = True, parent=None):
        super().__init__(parent)
        self.is_user = is_user

        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Minimum)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(12, 8, 12, 8)
        self.layout.setSpacing(6)

        self.text_label = HackerLabel(text)
        self.text_label.setWordWrap(True)
        self.text_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        self._set_font(self.text_label, 14)
        self.layout.addWidget(self.text_label)
        if image is not None:
            self._add_image(image)
        self._update_style()

    @staticmethod
    def _set_font(widget, size=14):
        font_id = QFontDatabase.addApplicationFont("./resources/fonts/jetbrains.ttf")
        if font_id != -1:
            family = QFontDatabase.applicationFontFamilies(font_id)[0]
            widget.setFont(QFont(family, size))
        else:
            widget.setFont(QFont("Consolas", size))

    def _add_image(self, image: str | QPixmap):
        pixmap = QPixmap(image) if isinstance(image, str) else image
        if pixmap.isNull():
            return
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("QLabel { background: transparent; border: none; }")
        self.image_pixmap = pixmap

        self.layout.addWidget(self.image_label)

    def append_text(self, chunk: str):
        if not chunk:
            return
        self.text_label.setText(self.text_label.text() + chunk)
        self.updateGeometry()

    def updateBubbleWidth(self, available_width: int):
        max_width = int(available_width * self.MAX_WIDTH_RATIO)
        self.setMaximumWidth(max_width)
        if hasattr(self, "image_label"):
            content_width = max_width - 24
            if content_width > 0:
                scaled = self.image_pixmap.scaled(QSize(content_width, 320), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                self.image_label.setPixmap(scaled)
        self.updateGeometry()

    def _update_style(self):
        if not self.is_user:
            self.setStyleSheet("""
                HackerChatBubble {
                    background: rgba(0, 0, 0, 170);
                    border: 1px solid rgba(0, 255, 0, 90);
                    border-radius: 10px;
                }
                HackerChatBubble:hover {
                    background: rgba(0, 255, 0, 15);
                    border: 1px solid rgba(0, 255, 0, 160);
                }
            """)
        else:
            self.setStyleSheet("""
                HackerChatBubble {
                    background: rgba(0, 255, 0, 35);
                    border: 1px solid #00FF00;
                    border-radius: 10px;
                }
                HackerChatBubble:hover {
                    background: rgba(0, 255, 0, 50);
                }
            """)


class HackerChatWidget(QWidget):
    userInputSignal = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.bubbles = []

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.scroll = HackerScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self.container = QWidget()
        self.container.setStyleSheet("QWidget { background: transparent; }")

        self.message_layout = QVBoxLayout(self.container)
        self.message_layout.setContentsMargins(12, 12, 12, 12)
        self.message_layout.setSpacing(10)
        self.message_layout.addStretch()
        self.scroll.setWidget(self.container)
        main_layout.addWidget(self.scroll)

        input_layout = QHBoxLayout()
        input_layout.setContentsMargins(12, 8, 12, 12)
        input_layout.setSpacing(8)

        self.input_edit = _ChatInputEdit(self)
        self.input_edit.setPlaceholderText("输入消息...")
        self.input_edit.setFixedHeight(45)
        self.send_button = HackerButton("发送")
        self.send_button.setFixedSize(70, 45)

        input_layout.addWidget(self.input_edit, 1)
        input_layout.addWidget(self.send_button)
        main_layout.addLayout(input_layout)

        self.send_button.set_border()
        self.send_button.clicked.connect(self._send_message)

    def _send_message(self):
        text = self.input_edit.toPlainText().strip()
        if not text:
            return
        self.add_user_msg(text)
        self.userInputSignal.emit(text)
        self.input_edit.clear()
        self.input_edit.setFocus()

    def add_assistant_msg(self, text: str = "", image: str | QPixmap | None = None):
        bubble = HackerChatBubble(text=text, image=image, is_user=False)
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(0)
        row_layout.addWidget(bubble, 0, Qt.AlignmentFlag.AlignLeft)
        row_layout.addStretch()
        self.message_layout.insertWidget(self.message_layout.count() - 1, row)
        self.bubbles.append(bubble)
        self.update_bubble_widths()
        self.scroll_to_bottom()
        return bubble

    def append_assistant_msg(self, bubble, text: str):
        if bubble is None or not text:
            return
        bubble.append_text(text)
        self.update_bubble_widths()
        self.scroll_to_bottom()

    def add_user_msg(self, text: str = "", image: str | QPixmap | None = None):
        bubble = HackerChatBubble(text=text, image=image, is_user=True)
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(0)
        row_layout.addStretch()
        row_layout.addWidget(bubble, 0, Qt.AlignmentFlag.AlignRight)
        self.message_layout.insertWidget(self.message_layout.count() - 1, row)
        self.bubbles.append(bubble)
        self.update_bubble_widths()
        self.scroll_to_bottom()
        return bubble

    def update_bubble_widths(self):
        width = self.scroll.viewport().width()
        for bubble in self.bubbles:
            bubble.updateBubbleWidth(width)

    def scroll_to_bottom(self):
        QApplication.processEvents()
        scrollbar = self.scroll.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def disable_send_button(self):
        self.send_button.setEnabled(False)

    def enable_send_button(self):
        self.send_button.setEnabled(True)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_bubble_widths()

    def clear_messages(self):
        while self.message_layout.count() > 1:
            item = self.message_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.bubbles.clear()


# UI
class HackerScrollArea(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.Shape.NoFrame)

        self.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: none;
            }

            QScrollBar:vertical {
                width: 8px;

                background: rgba(0, 0, 0, 120);

                border: none;
                border-radius: 4px;

                margin: 0;
            }

            QScrollBar::handle:vertical {
                background: rgba(0, 255, 0, 100);
                min-height: 30px;
                border-radius: 4px;
            }

            QScrollBar::handle:vertical:hover {
                background: #00FF00;
            }

            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0;
                border: none;
                background: none;
            }

            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {
                background: transparent;
            }

            QScrollBar:horizontal {
                height: 8px;
                background: rgba(0, 0, 0, 120);
                border: none;
                border-radius: 4px;
                margin: 0;
            }

            QScrollBar::handle:horizontal {
                background: rgba(0, 255, 0, 100);
                min-width: 30px;
                border-radius: 4px;
            }

            QScrollBar::handle:horizontal:hover {
                background: #00FF00;
            }

            QScrollBar::add-line:horizontal,
            QScrollBar::sub-line:horizontal {
                width: 0;
                border: none;
                background: none;
            }

            QScrollBar::add-page:horizontal,
            QScrollBar::sub-page:horizontal {
                background: transparent;
            }
        """)


class HackerCard(QFrame):
    def __init__(
        self,
        title: str,
        widget: QWidget,
        description: str = "",
        parent=None,
    ):
        super().__init__(parent)

        self.setFixedHeight(62)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(20)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(0)

        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("""
            QLabel {
                background: transparent;
                color: #00FF00;
                border: none;
            }
        """)

        description_label = QLabel(description)
        description_label.setStyleSheet("""
            QLabel {
                background: transparent;
                color: rgba(0, 255, 0, 130);
                border: none;
            }
        """)

        text_layout.addWidget(self.title_label)
        text_layout.addWidget(description_label)

        layout.addLayout(text_layout, 1)
        widget.setFixedHeight(30)

        layout.addWidget(
            widget,
            0,
            Qt.AlignmentFlag.AlignVCenter
        )

        self.setStyleSheet("""
            HackerCard {
                background: rgba(0, 0, 0, 150);

                border: 1px solid rgba(0, 255, 0, 70);
                border-radius: 6px;
            }

            HackerCard:hover {
                background: rgba(0, 255, 0, 15);
                border: 1px solid rgba(0, 255, 0, 140);
            }
        """)

    def title(self):
        return self.title_label.text()

    def set_title(self, title):
        self.title_label.setText(title)


class HackerTable(QTableWidget):
    def __init__(
        self,
        rows=0,
        columns=0,
        parent=None
    ):
        super().__init__(rows, columns, parent)

        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding
        )
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setVisible(True)
        self.verticalHeader().setDefaultSectionSize(36)
        self.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setShowGrid(True)
        self.horizontalHeader().setStretchLastSection(True)
        self.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setTextElideMode(Qt.TextElideMode.ElideRight)

        font = QFont("Consolas")
        font.setPixelSize(13)
        self.setFont(font)

        self.setStyleSheet("""
        QTableWidget {
            background: rgba(0, 0, 0, 165);
            color: #006CBF;
            border: 1px solid rgba(0, 255, 0, 90);
            border-radius: 6px;
            gridline-color: rgba(0, 255, 0, 35);
            selection-background-color: rgba(0, 255, 0, 65);
            selection-color: #FF0000;
            outline: none;
            alternate-background-color: rgba(0, 255, 0, 8);
        }
        QTableWidget::item {
            padding: 6px 10px;

            border: none;
            border-bottom: 1px solid rgba(0, 255, 0, 20);
        }
        QTableWidget::item:hover {
            background: rgba(0, 255, 0, 30);
            color: #66FF66;
        }
        QTableWidget::item:selected {
            background: rgba(0, 255, 0, 65);
            color: #FF0000;
        }

        QHeaderView {
            background: transparent;
        }
        QHeaderView::section {
            background: rgba(0, 0, 0, 220);
            color: #00FF00;
            padding: 8px 10px;
            border: none;
            border-right: 1px solid rgba(0, 255, 0, 45);
            border-bottom: 1px solid rgba(0, 255, 0, 90);
            font-weight: bold;
        }
        QHeaderView::section:hover {
            background: rgba(0, 255, 0, 30);
            color: #66FF66;
        }
        
        QHeaderView::section:vertical {
            background: rgba(0, 0, 0, 180);
            color: #00FF00;
            border: none;
            border-bottom: 1px solid rgba(0, 255, 0, 25);
        }

        QScrollBar:vertical {
            background: rgba(0, 0, 0, 100);
            width: 10px;
            margin: 2px 2px 2px 2px;
            border: none;
        }
        QScrollBar::handle:vertical {
            background: rgba(0, 255, 0, 130);
            min-height: 30px;
            border-radius: 5px;
        }
        QScrollBar::handle:vertical:hover {
            background: #00FF00;
        }
        QScrollBar::add-line:vertical,
        QScrollBar::sub-line:vertical {
            height: 0px;
            background: none;
            border: none;
        }
        QScrollBar::add-page:vertical,
        QScrollBar::sub-page:vertical {
            background: transparent;
        }
        
        QScrollBar:horizontal {
            background: rgba(0, 0, 0, 100);
            height: 10px;
            margin: 2px 2px 2px 2px;
            border: none;
        }
        QScrollBar::handle:horizontal {
            background: rgba(0, 255, 0, 130);
            min-width: 30px;
            border-radius: 5px;
        }
        QScrollBar::handle:horizontal:hover {
            background: #00FF00;
        }
        QScrollBar::add-line:horizontal,
        QScrollBar::sub-line:horizontal {
            width: 0px;
            background: none;
            border: none;
        }
        QScrollBar::add-page:horizontal,
        QScrollBar::sub-page:horizontal {
            background: transparent;
        }
        
        QTableWidget QLineEdit {
            background: rgba(0, 0, 0, 220);
            color: #00FF00;
            border: 1px solid #00FF00;
            border-radius: 3px;
            padding: 4px 8px;
            font-family: "Consolas";
            font-size: 13px;
            selection-background-color: rgba(0, 255, 0, 100);
        }
        """)

        self.setAlternatingRowColors(True)

        header = self.horizontalHeader()
        header.setHighlightSections(False)
        # 默认根据内容调整
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)

    def setHorizontalHeaderLabels(self, headers):
        """设置表头"""
        self.setColumnCount(len(headers))
        super().setHorizontalHeaderLabels(headers)

    def set_header_stretch(self):
        """让所有列平均拉伸"""
        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

    def set_header_resize(self):
        """允许用户拖动调整列宽"""
        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)


class HackerTabWidget(QTabWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self._setup_font()
        self._setup_style()

    def _setup_font(self):
        font_id = QFontDatabase.addApplicationFont(
            "./resources/fonts/jetbrains.ttf"
        )

        if font_id != -1:
            family = QFontDatabase.applicationFontFamilies(font_id)[0]
            self.setFont(QFont(family, 14))
        else:
            self.setFont(QFont("Consolas", 14))

    def _setup_style(self):
        self.setStyleSheet("""
            QTabWidget {
                background: transparent;
                border: none;
            }

            /* Tab 内容区域 */
            QTabWidget::pane {
                background: rgba(0, 0, 0, 180);

                border: 1px solid #00FF00;
                border-radius: 6px;

                top: -1px;
            }

            QTabBar {
                background: transparent;
            }

            QTabBar::tab {
                background: rgba(0, 0, 0, 150);
                color: #00FF00;

                min-height: 30px;
                max-height: 30px;

                min-width: 90px;

                padding: 0 12px;

                border: 1px solid transparent;
                border-bottom: none;

                border-radius: 6px 6px 0 0;
            }

            /* Hover */
            QTabBar::tab:hover {
                background: rgba(0, 255, 0, 35);
                color: #00FF88;

                border: 1px solid rgba(0, 255, 0, 100);
                border-bottom: none;
            }

            /* 当前选中的 Tab */
            QTabBar::tab:selected {
                background: rgba(0, 255, 0, 60);
                color: #00FF88;

                border: 1px solid #00FF00;
                border-bottom: 2px solid #00FF00;
            }

            /* 未选中的 Tab */
            QTabBar::tab:!selected {
                margin-top: 2px;
            }

            /* Tab 被按下 */
            QTabBar::tab:pressed {
                background: rgba(0, 255, 0, 80);
                color: #FFFFFF;
            }

            QTabWidget QWidget {
                background: transparent;
                color: #00FF00;
            }
        """)


class HackerSwitch(QWidget):
    stateChanged = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setFixedSize(56, 30)
        self._checked = False
        self._offset = 3.0

        # 滑动动画
        self.animation = QPropertyAnimation(self, b"offset")
        self.animation.setDuration(180)
        self.animation.setEasingCurve(
            QEasingCurve.Type.OutCubic
        )

        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def getOffset(self):
        return self._offset

    def setOffset(self, value):
        self._offset = value
        self.update()

    offset = Property(float, getOffset, setOffset)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setChecked(not self._checked)
            self.stateChanged.emit(self._checked)

        super().mousePressEvent(event)

    def setChecked(self, checked):
        self._checked = checked

        start = self._offset
        end = 29.0 if checked else 3.0

        self.animation.stop()
        self.animation.setStartValue(start)
        self.animation.setEndValue(end)
        self.animation.start()

    def isChecked(self):
        return self._checked

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self._checked:
            bg_color = QColor(0, 255, 0, 70)
            border_color = QColor("#00FF00")
        else:
            bg_color = QColor(0, 0, 0, 180)
            border_color = QColor(0, 255, 0, 90)

        painter.setBrush(bg_color)
        painter.setPen(border_color)

        rect = QRectF(
            1,
            1,
            self.width() - 2,
            self.height() - 2
        )

        painter.drawRoundedRect(
            rect,
            14,
            14
        )

        knob_size = 24

        knob_y = (self.height() - knob_size) / 2

        if self._checked:
            knob_color = QColor("#00FF88")
        else:
            knob_color = QColor("#00AA00")

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(knob_color)

        painter.drawEllipse(
            QRectF(
                self._offset,
                knob_y,
                knob_size,
                knob_size
            )
        )

        if self._checked:
            glow = QColor(0, 255, 0, 80)

            painter.setPen(glow)
            painter.setBrush(Qt.BrushStyle.NoBrush)

            painter.drawEllipse(
                QRectF(
                    self._offset - 2,
                    knob_y - 2,
                    knob_size + 4,
                    knob_size + 4
                )
            )


class HackerLabel(QLabel):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        # 文字左对齐
        self.setAlignment(Qt.AlignmentFlag.AlignLeft)
        font_id = QFontDatabase.addApplicationFont("./resources/fonts/jetbrains.ttf")
        if font_id != -1:
            family = QFontDatabase.applicationFontFamilies(font_id)[0]
            self.setFont(QFont(family, 16))
        else:
            self.setFont(QFont("Consolas", 16))

        self.setStyleSheet("""
            QLabel {
                background: rgba(0,0,0,160);
                color: #00FF00;
                border: none;
                border-radius: 6px;
                min-height: 36px;
            }
        """)

    def set_center(self):
        self.setAlignment(Qt.AlignCenter)


class HackerComboBox(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        font_id = QFontDatabase.addApplicationFont(
            "./resources/fonts/jetbrains.ttf"
        )
        if font_id != -1:
            family = QFontDatabase.applicationFontFamilies(font_id)[0]
            self.setFont(QFont(family, 14))
        else:
            self.setFont(QFont("Consolas", 14))
        self.setFixedHeight(30)
        self.setStyleSheet("""
            QComboBox {
                background: rgba(0, 0, 0, 160);
                color: #00FF00;

                border: 1px solid rgba(0, 255, 0, 100);
                border-radius: 6px;

                min-height: 30px;
                max-height: 30px;

                padding: 0 8px;
            }

            QComboBox:hover {
                border: 1px solid #00FF00;
                background: rgba(0, 255, 0, 20);
            }

            QComboBox:focus {
                border: 1px solid #00FF00;
                background: rgba(0, 0, 0, 180);
            }

            /* 下拉按钮 */
            QComboBox::drop-down {
                width: 28px;

                border: none;
                border-left: 1px solid rgba(0, 255, 0, 80);

                background: rgba(0, 0, 0, 100);
            }

            QComboBox::drop-down:hover {
                background: rgba(0, 255, 0, 30);
            }

            /* 下拉列表 */
            QComboBox QAbstractItemView {
                background: rgba(0, 0, 0, 230);
                color: #00FF00;

                border: 1px solid #00FF00;
                border-radius: 4px;

                padding: 2px;
                outline: none;
            }

            /* 下拉列表项目 */
            QComboBox QAbstractItemView::item {
                min-height: 26px;
                padding: 2px 8px;

                border-radius: 3px;
            }

            QComboBox QAbstractItemView::item:hover {
                background: rgba(0, 255, 0, 40);
                color: #66FF66;
            }

            QComboBox QAbstractItemView::item:selected {
                background: rgba(0, 255, 0, 60);
                color: #FFFFFF;
            }
        """)


class HackerSlider(QSlider):
    def __init__(
        self,
        orientation=Qt.Orientation.Horizontal,
        parent=None
    ):
        super().__init__(orientation, parent)

        self.setMinimum(0)
        self.setMaximum(100)
        self.setValue(50)

        self.setStyleSheet("""
            QSlider {
                background: transparent;
                min-height: 24px;
            }
            QSlider::groove:horizontal {
                height: 6px;
                background: rgba(0, 0, 0, 160);
                border: 1px solid rgba(0, 255, 0, 80);
                border-radius: 3px;
            }

            QSlider::sub-page:horizontal {
                background: #00FF00;
                border-radius: 3px;
            }

            QSlider::add-page:horizontal {
                background: rgba(0, 0, 0, 160);
                border-radius: 3px;
            }

            QSlider::handle:horizontal {
                width: 14px;
                height: 14px;
                margin: -5px 0;
                background: #00FF00;
                border: 2px solid #001A00;
                border-radius: 7px;
            }

            QSlider::handle:horizontal:hover {
                background: #66FF66;
                border: 2px solid #00FF00;
            }

            QSlider::handle:horizontal:pressed {
                background: #FFFFFF;
                border: 2px solid #00FF00;
            }

            QSlider::groove:vertical {
                width: 6px;
                background: rgba(0, 0, 0, 160);
                border: 1px solid rgba(0, 255, 0, 80);
                border-radius: 3px;
            }

            QSlider::sub-page:vertical {
                background: #00FF00;
                border-radius: 3px;
            }

            QSlider::add-page:vertical {
                background: rgba(0, 0, 0, 160);
                border-radius: 3px;
            }

            QSlider::handle:vertical {
                width: 14px;
                height: 14px;
                margin: 0 -5px;
                background: #00FF00;
                border: 2px solid #001A00;
                border-radius: 7px;
            }

            QSlider::handle:vertical:hover {
                background: #66FF66;
                border: 2px solid #00FF00;
            }

            QSlider::handle:vertical:pressed {
                background: #FFFFFF;
                border: 2px solid #00FF00;
            }
        """)


class HackerButton(QPushButton):
    def __init__(self, text="", icon: QIcon = None, parent=None):
        super().__init__(text, parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setIcon(icon if icon else QIcon())
        self.setIconSize(QSize(20, 20))

        self.normal_style = """
            QPushButton {
                background: rgba(0,0,0,150);
                color: #00FF00;
                padding: 0 12px;
                border: none;
                border-radius: 6px;
                min-height: 36px;
                text-align: left;
            }
            QPushButton:hover {
                background: rgba(0,255,0,40);
                color: #00FF88;
            }
        """

        self.active_style = """
            QPushButton {
                background: rgba(0,255,0,60);
                color: #00FF88;
                padding: 0 12px;
                border: none;
                border-radius: 6px;
                min-height: 36px;
                text-align: left;
            }
        """

        self.setStyleSheet(self.normal_style)

    def set_border(self):
        self.setStyleSheet("""
            QPushButton {
                background: rgba(0,0,0,150);
                color: #00FF00;
                padding: 0 12px;
                border: 1px solid #00FF00;
                border-radius: 6px;
                min-height: 36px;
                text-align: left;
            }
            QPushButton:hover {
                background: rgba(0,255,0,40);
            }
            """
        )

    def setActive(self, active: bool):
        self.setStyleSheet(self.active_style if active else self.normal_style)


class HackerLineEdit(QLineEdit):
    def __init__(self, placeholder_text: str | None = None, parent=None):
        super().__init__(parent if isinstance(placeholder_text, str) else placeholder_text)
        if isinstance(placeholder_text, str): self.setPlaceholderText(placeholder_text)
        self.setStyleSheet("""
        QLineEdit {
            background: rgba(0,0,0,150);
            color: rgb(255, 80, 80);
            padding: 0 12px;
            border: 1px solid #00FF00;
            border-radius: 6px;
            min-height: 30px;
        }
        QLineEdit::focus {
            border-bottom: 1px solid #00ffff;
        }
        """)


class HackerTextEdit(QTextEdit):
    def __init__(self, placeholder_text: str | None = None, parent=None):
        super().__init__(parent if isinstance(placeholder_text, str) else placeholder_text)
        if isinstance(placeholder_text, str): self.setPlaceholderText(placeholder_text)

        font = QFont("Microsoft YaHei", 12)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)

        self.setStyleSheet("""
        QTextEdit {
            background: rgba(0,0,0,150);
            padding: 10px;
            color: rgb(45, 196, 210);
            border: 1px solid #00FF00;
            border-radius: 6px;
            selection-background-color: rgba(0, 255, 0, 100);
        }
        QTextEdit:focus {
            border: 1px solid #00ffff;
        }
        QTextEdit::selected {
            background-color: rgba(0, 255, 0, 100);
        }
        QTextEdit::scrollbar:vertical {
            width: 8px;
            background-color: rgba(0,0,0,150);
            border: 1px solid #00FF00;
        }
        """)


class HackerMenu(QWidget):
    triggered = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._actions = []
        self._items = []  # Track all items including separators

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
            background: rgba(0, 0, 0, 150);
            color: #00FF00;
            padding: 0 12px;
            border-radius: 6px;
            min-height: 36px;
            max-height: 36px;
        }
        QLabel:hover {
            background: rgba(0, 255, 0, 50);
            color: #00FF88;
        }
        """)

    def addAction(self, action):
        self._actions.append(action)
        self._items.append(('action', action))

        text = action.text()
        pixmap = action.icon().pixmap(24, 24) if not action.icon().isNull() else None

        font_metrics = QFontMetrics(self.hacker_font)
        text_width = font_metrics.horizontalAdvance(text)
        arrow_width = font_metrics.horizontalAdvance(" > ")
        icon_width = pixmap.width() + 6 if pixmap else 0
        total_width = text_width + icon_width + 24 + arrow_width + 10

        label_height = 36
        label_pixmap = QPixmap(total_width, label_height)
        label_pixmap.fill(Qt.transparent)

        label = QLabel()
        label.setFixedHeight(label_height)
        label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        label.setPixmap(label_pixmap)

        if not hasattr(self, '_max_width'):
            self._max_width = total_width
        else:
            self._max_width = max(self._max_width, total_width)

        def redraw(hovered=False):
            combined = QPixmap(total_width, label_height)
            combined.fill(Qt.transparent)
            painter = QPainter(combined)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setFont(self.hacker_font)
            painter.setPen(QColor("#00FF88" if hovered else "#00FF00"))

            text_x = 6
            if hovered:
                painter.drawText(text_x, 0, arrow_width, label_height, Qt.AlignVCenter, ">")
                text_x += arrow_width

            if pixmap:
                painter.drawPixmap(text_x, (label_height - pixmap.height()) // 2, pixmap)
                text_x += pixmap.width() + 6

            painter.drawText(text_x, 0, total_width - text_x, label_height, Qt.AlignVCenter, text)
            painter.end()
            label.setPixmap(combined)

        redraw(False)

        def enter_event(e):
            redraw(True)

        def leave_event(e):
            redraw(False)

        def mouse_press_event(e):
            self._emit(action)

        label.enterEvent = enter_event
        label.leaveEvent = leave_event
        label.mousePressEvent = mouse_press_event

        self.layout.addWidget(label)

        self.box.setFixedWidth(self._max_width + 20)
        self.adjustSize()

    def addSeparator(self):
        separator = QWidget()
        separator.setFixedHeight(1)
        separator.setStyleSheet("background-color: rgba(0, 255, 0, 100); margin: 5px 0px;")

        self.layout.addWidget(separator)
        self._items.append(('separator', separator))

        self.adjustSize()

    def _emit(self, action):
        self.triggered.emit(action)
        if hasattr(action, 'trigger'):
            action.trigger()
        self.close()

    def exec(self, pos=None):
        self.adjustSize()
        if pos is None:
            pos = QCursor.pos()
        self.move(pos)
        self.show()


class IconList:
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


class HackerWindow(QWidget):
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

        if widget in self.nav_widgets.values():
            self.pages.removeWidget(widget)
            widget.setParent(None)

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


class _ChatInputEdit(HackerTextEdit):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent_ = parent

    def keyPressEvent(self, event):
        if (
            event.key() == Qt.Key.Key_Return
            and not (
                event.modifiers()
                & Qt.KeyboardModifier.ShiftModifier
            )
        ):
            self.parent_._send_message()
            return

        super().keyPressEvent(event)


# BASE
class ModelChat(QWidget):
    def __init__(
        self,
        ai_name: str, model: str,
        is_local: bool,
        api_key: str | None = None,
        base_url: str | None = None,
        parent=None,
    ):
        super().__init__(parent)
        if is_local:
            if model in cache_llm_class.keys():
                self.ai_llm = cache_llm_class[model]
            else:
                self.ai_llm = local.LLM(model)
                cache_llm_class[model] = self.ai_llm
        else:
            if model in cache_llm_class.keys():
                self.ai_llm = cache_llm_class[model]
            else:
                # noinspection PyTypeChecker
                self.ai_llm = cloud.LLM(model, api_key, base_url)
                cache_llm_class[model] = self.ai_llm
        # noinspection PyTypeChecker
        self.ai_llm.memory_signal.connect(SharingData.add_memory_to_ui[model])

        self.setWindowTitle(ai_name)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        title = SharingData.theme.Label("AI TERMINAL")
        title.setFixedHeight(30)
        layout.addWidget(title)

        self.chat = SharingData.theme.ChatWidget()
        self.chat.userInputSignal.connect(self.add_user_msg)

        layout.addWidget(self.chat)

        self.current_assistant_bubble = None

    def chat_finished(self, all_message):
        self.chat.enable_send_button()

    def add_user_msg(self, msg: str):
        self.current_assistant_bubble = self.chat.add_assistant_msg()
        self.chat.disable_send_button()

        t = derfer.LLMAICallback(self.ai_llm, msg, self)
        t.finished.connect(self.chat_finished)
        t.text_chunk.connect(self.add_assistant_msg)
        t.start()

    def add_assistant_msg(self, msg: str):
        if not msg:
            return

        if self.current_assistant_bubble is not None:
            self.current_assistant_bubble.append_text(msg)
            self.chat.update_bubble_widths()
            self.chat.scroll_to_bottom()


IconList = IconList()
Window = HackerWindow
Menu = HackerMenu
TextEdit = HackerTextEdit
LineEdit = HackerLineEdit
Button = HackerButton
Label = HackerLabel
Slider = HackerSlider
ComboBox = HackerComboBox
CardWidget = HackerCard
ScrollArea = HackerScrollArea
ChatBubble = HackerChatBubble
ChatWidget = HackerChatWidget
