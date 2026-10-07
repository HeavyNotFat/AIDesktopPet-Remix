import base64
import math
import random
import json

from . import general
from . import llm
from . import tts
from . import settings
from . import animation
from . import plugins

from ..base import ModelChatABS, MainWindowABS, IconListABS, MenuWidgetABS, SwitchWidgetABS, CombinedMeta

from ... import derfer
from ... import Config, SharingData
from ...ai import local
from ...ai import cloud

from PySide6.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout, QSizePolicy, QHBoxLayout, QStackedWidget, QPushButton, \
    QScrollArea, QLineEdit, QTextEdit, QSlider, QComboBox, QTabWidget, QFrame, QToolButton, QTableWidget, QHeaderView, QAbstractItemView, \
    QGraphicsDropShadowEffect
from PySide6.QtCore import Qt, Signal, QSize, QTimer, QPropertyAnimation, QEasingCurve, QRectF, Property, QPoint
from PySide6.QtGui import QAction, QCursor, QFontDatabase, QFont, QIcon, QPainter, QBrush, QColor, QPen, QPixmap, \
    QFontMetrics, QKeySequence, QShortcut, QPainterPath, QImage
from PySide6.QtCore import QByteArray

cache_llm_class = {}
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
class HackerBubbleAction(QToolButton):
    """气泡底下的小按钮（复制 / 播放）。"""

    def __init__(self, text: str, tooltip: str = "", parent=None):
        super().__init__(parent)
        self.setText(text)
        if tooltip:
            self.setToolTip(tooltip)

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAutoRaise(True)
        self.setFixedHeight(22)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setFont(QFont("Consolas", 10))
        self.setStyleSheet("""
            QToolButton {
                color: rgba(0, 255, 0, 150);
                background: rgba(0, 255, 0, 12);
                border: 1px solid rgba(0, 255, 0, 60);
                border-radius: 6px;
                padding: 1px 8px;
            }
            QToolButton:hover {
                color: #00FF00;
                background: rgba(0, 255, 0, 40);
                border: 1px solid #00FF00;
            }
            QToolButton:pressed {
                background: rgba(0, 255, 0, 70);
            }
            QToolButton:disabled {
                color: rgba(0, 255, 0, 60);
                border: 1px solid rgba(0, 255, 0, 30);
            }
        """)

    def set_busy(self, busy: bool, text: str = ""):
        self.setEnabled(not busy)
        if text:
            self.setText(text)


class HackerChatBubble(QFrame):
    MAX_WIDTH_RATIO = 0.60

    def __init__(self, text: str = "", image: str | QPixmap | None = None, is_user: bool = True, parent=None):
        super().__init__(parent)
        self.is_user = is_user
        self.audio_data: str | None = None
        self.skill_name: str = ""
        self.image_labels: list = []

        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Minimum)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(12, 8, 12, 8)
        self.layout.setSpacing(6)

        self.skill_label = HackerLabel("")
        self.skill_label.setStyleSheet("""
            QLabel {
                color: rgba(0, 255, 0, 180);
                background: rgba(0, 255, 0, 20);
                border: 1px solid rgba(0, 255, 0, 70);
                border-radius: 6px;
                padding: 1px 6px;
                font-size: 11px;
            }
        """)
        self.skill_label.setVisible(False)
        self.layout.addWidget(self.skill_label, 0, Qt.AlignmentFlag.AlignLeft)

        self.text_label = HackerLabel(text)
        self.text_label.setWordWrap(True)
        self.text_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        self._set_font(self.text_label, 14)
        self.layout.addWidget(self.text_label)
        if image is not None:
            self._add_image(image)

        self._build_actions()
        self._update_style()

    def _build_actions(self):
        """回复底下的一条小动作栏：默认只有复制，有音频时多一个播放。"""
        self.actions = QWidget(self)
        self.actions_layout = QHBoxLayout(self.actions)
        self.actions_layout.setContentsMargins(0, 0, 0, 0)
        self.actions_layout.setSpacing(6)

        self.copy_button = HackerBubbleAction("复制", "把这条回复复制到剪贴板")
        self.copy_button.clicked.connect(self.copy_text)
        self.actions_layout.addWidget(self.copy_button)

        self.play_button = HackerBubbleAction("▶ 播放", "播放这条回复的语音")
        self.play_button.clicked.connect(self.play_audio)
        self.play_button.setVisible(False)
        self.actions_layout.addWidget(self.play_button)
        self.actions_layout.addStretch(1)

        self.actions.setVisible(not self.is_user)
        self.layout.addWidget(self.actions)

    def text(self) -> str:
        return self.text_label.text()

    def copy_text(self):
        content = self.text().strip()
        if not content:
            HackerNotify("这条回复还是空的", "warning", 1800)
            return

        QApplication.clipboard().setText(content)
        HackerNotify("已复制这条回复", "success", 1600)

    def attach_audio(self, data: str):
        """挂上语音但**不自动播**，等用户点播放。"""
        self.audio_data = data
        self.play_button.setVisible(True)
        self.actions.setVisible(True)

    def play_audio(self):
        if not self.audio_data:
            return

        self.play_button.set_busy(True)
        try:
            derfer.play_audio(self.audio_data)
        except Exception as exc:  # noqa: BLE001 - 没声卡/解码失败都要给出提示
            HackerNotify(f"播放失败：{type(exc).__name__}: {exc}", "error", 4000)
        else:
            HackerNotify("正在播放这条回复的语音", "info", 1800)
        finally:
            self.play_button.set_busy(False)

    def set_skill(self, name: str):
        self.skill_name = name or ""
        self.skill_label.setText(f"技能 · {self.skill_name}")
        self.skill_label.setVisible(bool(self.skill_name))

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

    def add_attachments(self, attachments):
        """图片放缩略图，文档放一个小标签（名字 + 大小 + 读取情况）。"""
        from ...ai import human_size

        for item in attachments or []:
            if item.get("kind") == "image" and item.get("data"):
                pixmap = QPixmap()
                pixmap.loadFromData(QByteArray(base64.b64decode(item["data"])))
                if pixmap.isNull():
                    continue

                label = QLabel()
                label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                label.setStyleSheet("QLabel { background: transparent; border: none; }")
                label.setToolTip(item.get("name", ""))
                self.image_labels.append((label, pixmap))
                self.layout.addWidget(label)
            else:
                chip = QLabel(f"📄 {item.get('name')}（{human_size(item.get('size'))}）· {item.get('note', '')}")
                chip.setWordWrap(True)
                chip.setStyleSheet("""
                    QLabel {
                        color: #00FF88;
                        background: rgba(0, 255, 0, 16);
                        border: 1px solid rgba(0, 255, 0, 70);
                        border-radius: 6px;
                        padding: 3px 8px;
                    }
                """)
                self.layout.addWidget(chip)

        self.updateGeometry()

    def updateBubbleWidth(self, available_width: int):
        max_width = int(available_width * self.MAX_WIDTH_RATIO)
        self.setMaximumWidth(max_width)
        content_width = max_width - 24
        if hasattr(self, "image_label") and content_width > 0:
            scaled = self.image_pixmap.scaled(QSize(content_width, 320), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.image_label.setPixmap(scaled)
        if content_width > 0:
            for label, pixmap in self.image_labels:
                label.setPixmap(pixmap.scaled(
                    QSize(content_width, 320),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                ))
        self.updateGeometry()

    def append_text(self, chunk: str):
        if not chunk:
            return
        self.text_label.setText(self.text_label.text() + chunk)
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
    # (正文, 附件列表)：附件跟着信号走，避免发送方清空后接收方拿到空列表
    userInputSignal = Signal(str, list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.bubbles = []
        self.active_skill: dict | None = None
        self.attachments: list = []

        self.setAcceptDrops(True)

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

        main_layout.addWidget(self._build_skill_bar())
        main_layout.addWidget(self._build_attachment_bar())

        input_layout = QHBoxLayout()
        input_layout.setContentsMargins(12, 8, 12, 12)
        input_layout.setSpacing(8)

        self.attach_button = HackerButton("附件")
        self.attach_button.setFixedSize(70, 45)
        self.attach_button.set_border()
        self.attach_button.setToolTip("选图片或文档；也可以直接 Ctrl+V 粘贴、把文件拖进来")
        self.attach_button.clicked.connect(self.pick_attachments)

        self.skill_button = HackerButton("技能")
        self.skill_button.setFixedSize(70, 45)
        self.skill_button.set_border()
        self.skill_button.setToolTip("选一个技能，或者直接在输入框打 /技能名")
        self.skill_button.clicked.connect(self.show_skills)

        self.input_edit = _ChatInputEdit(self)
        self.input_edit.setPlaceholderText("输入消息...（/技能名 用技能，Ctrl+V 粘图片，可拖文件进来）")
        self.input_edit.setFixedHeight(45)
        self.send_button = HackerButton("发送")
        self.send_button.setFixedSize(70, 45)

        input_layout.addWidget(self.attach_button)
        input_layout.addWidget(self.skill_button)
        input_layout.addWidget(self.input_edit, 1)
        input_layout.addWidget(self.send_button)
        main_layout.addLayout(input_layout)

        self.send_button.set_border()
        self.send_button.clicked.connect(self._send_message)

    def dragEnterEvent(self, event, /):
        if event.mimeData().hasImage() or event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event, /):
        if self.attach_from_mime(event.mimeData()):
            event.acceptProposedAction()

    def _build_skill_bar(self):
        self.skill_bar = QWidget()
        layout = QHBoxLayout(self.skill_bar)
        layout.setContentsMargins(12, 4, 12, 0)
        layout.setSpacing(6)

        self.skill_bar_label = HackerLabel("")
        self.skill_bar_label.setStyleSheet("QLabel { color: #00FF00; background: transparent; }")
        self.clear_skill_button = HackerBubbleAction("×", "取消当前技能")
        self.clear_skill_button.clicked.connect(lambda: self.set_skill(None))

        layout.addWidget(self.skill_bar_label)
        layout.addWidget(self.clear_skill_button)
        layout.addStretch(1)
        self.skill_bar.setVisible(False)
        return self.skill_bar

    def skills(self) -> list:
        return [skill for skill in (Config.skills or []) if isinstance(skill, dict) and skill.get("name")]

    def set_skill(self, skill: dict | None):
        self.active_skill = dict(skill) if skill else None
        if self.active_skill:
            name = self.active_skill.get("name", "")
            description = self.active_skill.get("description", "")
            self.skill_bar_label.setText(f"当前技能：{name}" + (f" —— {description}" if description else ""))
            self.skill_bar.setVisible(True)
            self.skill_button.setText("技能 ✓")
            HackerNotify(f"已启用技能「{name}」", "success", 2000)
        else:
            self.skill_bar.setVisible(False)
            self.skill_button.setText("技能")

    def build_skill_menu(self):
        """菜单每次重建：设置页里刚加的技能不用重启就能选到。"""
        from ... import get_translation

        menu = HackerMenu(self)

        def add(text, callback, enabled=True):
            action = QAction(text, menu)
            action.setEnabled(enabled)
            if enabled:
                action.triggered.connect(callback)
            menu.addAction(action)
            return action

        skills = self.skills()
        if not skills:
            add(get_translation("graphics.chat.no_skill"), None, enabled=False)
        else:
            for skill in skills:
                description = skill.get("description", "")
                add(f"{skill['name']}　{description}".strip(),
                    lambda _checked=False, item=skill: self.set_skill(item))

        if self.active_skill:
            menu.addSeparator()
            add("取消技能", lambda: self.set_skill(None))
        return menu

    def show_skills(self):
        menu = self.build_skill_menu()
        menu.exec(self.skill_button.mapToGlobal(QPoint(0, -menu.sizeHint().height() - 6)))

    def _build_attachment_bar(self):
        self.attachment_bar = QWidget()
        layout = QHBoxLayout(self.attachment_bar)
        layout.setContentsMargins(12, 4, 12, 0)
        layout.setSpacing(6)
        self.attachment_layout = layout
        self.attachment_bar.setVisible(False)
        return self.attachment_bar

    def add_attachment(self, attachment: dict):
        from ...ai import MAX_ATTACHMENTS

        if not attachment:
            return False
        if len(self.attachments) >= MAX_ATTACHMENTS:
            HackerNotify(f"最多一次带 {MAX_ATTACHMENTS} 个附件", "warning", 2200)
            return False

        self.attachments.append(attachment)
        chip = HackerAttachmentChip(attachment, on_remove=self.remove_attachment)
        self.attachment_layout.addWidget(chip)
        self.attachment_bar.setVisible(True)
        return True

    def remove_attachment(self, attachment: dict):
        self.attachments = [item for item in self.attachments if item is not attachment]
        for index in range(self.attachment_layout.count()):
            widget = self.attachment_layout.itemAt(index).widget()
            if isinstance(widget, HackerAttachmentChip) and widget.property("attachment") is attachment:
                widget.setParent(None)
                widget.deleteLater()
                break
        self.attachment_bar.setVisible(bool(self.attachments))

    def clear_attachments(self):
        while self.attachment_layout.count():
            item = self.attachment_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self.attachments = []
        self.attachment_bar.setVisible(False)

    def attach_paths(self, paths) -> int:
        from ...ai import from_path

        added = 0
        for path in paths or []:
            try:
                if self.add_attachment(from_path(path)):
                    added += 1
            except OSError as exc:
                HackerNotify(f"读不了这个文件：{exc}", "error", 3000)
        return added

    def can_attach_mime(self, source) -> bool:
        """这份剪切板/拖拽内容能不能当附件（不产生副作用，Qt 会先问这个）。"""
        if source is None:
            return False
        if source.hasImage():
            return True
        return bool(self._local_files(source))

    @staticmethod
    def _local_files(source) -> list:
        if not source.hasUrls():
            return []
        return [url.toLocalFile() for url in source.urls() if url.isLocalFile() and url.toLocalFile()]

    def _clipboard_pixmap(self, source):
        """剪切板里的图片可能是 QImage 也可能是 QPixmap，统一成 QPixmap。

        （实测：系统剪切板给的是 QImage，只有代码里 setImageData(QPixmap) 才是 QPixmap——
        以前只判 QPixmap，所以真实 Ctrl+V 一张图都加不进来。）
        """
        if source is None or not source.hasImage():
            return None

        data = source.imageData()
        if isinstance(data, QImage):
            data = QPixmap.fromImage(data)
        elif isinstance(data, QPixmap):
            pass
        elif isinstance(data, str):
            data = QPixmap(data)
        else:
            return None

        return data if isinstance(data, QPixmap) and not data.isNull() else None

    def attach_from_mime(self, source) -> bool:
        """剪切板/拖拽进来的东西：图片优先，其次是文件路径。"""
        if source is None:
            return False

        added = 0
        pixmap = self._clipboard_pixmap(source)
        if pixmap is not None:
            added += self._attach_pixmap(pixmap)
        added += self.attach_paths(self._local_files(source))

        if added:
            HackerNotify(f"已加入 {added} 个附件", "success", 2000)
        return added > 0

    def _attach_pixmap(self, pixmap: QPixmap) -> int:
        from PySide6.QtCore import QBuffer, QByteArray

        from ...ai import from_bytes

        buffer = QBuffer()
        buffer.open(QBuffer.OpenModeFlag.ReadWrite)
        pixmap.save(buffer, "PNG")
        data = bytes(buffer.data())
        buffer.close()

        name = f"剪切板图片-{len(self.attachments) + 1}.png"
        return 1 if self.add_attachment(from_bytes(data, name, "image/png")) else 0

    def pick_attachments(self):
        from PySide6.QtWidgets import QFileDialog

        paths, _selected = QFileDialog.getOpenFileNames(
            self,
            "选择图片或文档",
            "",
            "图片与文档 (*.png *.jpg *.jpeg *.webp *.gif *.bmp *.txt *.md *.csv *.json *.log *.yaml *.yml *.toml *.py *.js *.ts *.docx);;所有文件 (*)",
        )
        if paths:
            self.attach_paths(paths)

    def _send_message(self):
        text = self.input_edit.toPlainText().strip()
        if not text and not self.attachments:
            return

        from ... import run_plugin_command
        from ...ai import parse_skill

        # 插件命令：/名字 参数（技能优先，认不出来再看插件有没有注册这个命令）
        handled, result = run_plugin_command(text)
        if handled:
            self.input_edit.clear()
            if result:
                self.add_user_msg(text)
                self.add_assistant_msg(result)
            return

        skill, text = parse_skill(text, self.skills())
        if skill:
            self.set_skill(skill)
        if not text and not self.attachments:
            # 只打了 /技能名：当成切换技能，不发送
            self.input_edit.clear()
            return

        pending = self.take_attachments()
        self.add_user_msg(text, skill=self.active_skill, attachments=pending)
        # 附件要跟着信号一起走：ModelChat 那边再取一次的话已经被这里清空了
        self.userInputSignal.emit(text, pending)
        self.input_edit.clear()
        self.input_edit.setFocus()

    def take_attachments(self) -> list:
        pending = list(self.attachments)
        self.clear_attachments()
        return pending

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

    def add_user_msg(self, text: str = "", image: str | QPixmap | None = None, skill: dict | None = None,
                     attachments=None):
        bubble = HackerChatBubble(text=text, image=image, is_user=True)
        if skill:
            bubble.set_skill(skill.get("name", ""))
        if attachments:
            bubble.add_attachments(attachments)
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


class HackerNotify(QFrame):
    """操作反馈条：优先贴在当前窗口顶部（醒目、居中、带图标），没有窗口时才浮到屏幕右下角。"""

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

        # parent 传什么都行：这里统一解析成"要贴进去的窗口"，解析不到才当浮层
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


class HackerCard(QFrame):
    def __init__(
        self,
        title: str,
        widget: QWidget,
        description: str = "",
        parent=None,
        stacked: bool = False,
    ):
        super().__init__(parent)

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
                color: rgba(0, 255, 0, 150);
                border: none;
            }
        """)

        if stacked:
            # 上下排：控件独占一整行，适合下拉框、表格这类需要宽度的东西
            self.setFixedHeight(104)
            layout = QVBoxLayout(self)
            layout.setContentsMargins(14, 10, 14, 12)
            layout.setSpacing(8)

            head = QHBoxLayout()
            head.setContentsMargins(0, 0, 0, 0)
            head.setSpacing(12)
            head.addWidget(self.title_label)
            head.addWidget(description_label)
            head.addStretch(1)
            layout.addLayout(head)

            layout.addWidget(widget)
        else:
            self.setFixedHeight(62)
            layout = QHBoxLayout(self)
            layout.setContentsMargins(14, 8, 14, 8)
            layout.setSpacing(20)

            text_layout = QVBoxLayout()
            text_layout.setContentsMargins(0, 0, 0, 0)
            text_layout.setSpacing(0)
            text_layout.addWidget(self.title_label)
            text_layout.addWidget(description_label)

            layout.addLayout(text_layout, 1)
            # 别把控件压扁：按它自己的建议高度来（开关 30、按钮 38 都能放下）
            widget.setFixedHeight(max(30, widget.sizeHint().height()))
            layout.addWidget(widget, 0, Qt.AlignmentFlag.AlignVCenter)

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


class HackerSwitch(QWidget, SwitchWidgetABS, metaclass=CombinedMeta):
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
        checked = bool(checked)
        changed = checked != self._checked
        self._checked = checked

        start = self._offset
        end = 29.0 if checked else 3.0

        self.animation.stop()
        self.animation.setStartValue(start)
        self.animation.setEndValue(end)
        self.animation.start()

        # 代码里改状态也要通知出去（以前只有鼠标点击才发信号）
        if changed:
            self.stateChanged.emit(checked)

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


class HackerMenu(QWidget, MenuWidgetABS, metaclass=CombinedMeta):
    triggered = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._actions = []
        self._items = []  # Track all items including separators
        self._action_items = []  # 每条 item 的绘制数据（用来统一宽度）
        self._max_width = 0

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

        label_height = 36
        label = QLabel()
        label.setFixedHeight(label_height)
        label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        # 每一条都按「最宽的那条」来画：早先按自己文字宽度画，短条目右边留空、
        # 悬停高亮也只亮一半，看着很难受。
        entry = {'label': label, 'text': text, 'pixmap': pixmap, 'width': 0}
        entry['width'] = self._measure(text, pixmap)

        def redraw(hovered=False, entry=entry):
            width = max(entry['width'], self._max_width)
            label_height = entry['label'].height() or 36
            combined = QPixmap(width, label_height)
            combined.fill(Qt.transparent)
            painter = QPainter(combined)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setFont(self.hacker_font)
            painter.setPen(QColor("#00FF88" if hovered else "#00FF00"))

            metrics = QFontMetrics(self.hacker_font)
            arrow_width = metrics.horizontalAdvance(" > ")
            text_x = 6
            if hovered:
                painter.drawText(text_x, 0, arrow_width, label_height, Qt.AlignVCenter, ">")
            text_x += arrow_width
            if entry['pixmap']:
                painter.drawPixmap(text_x, (label_height - entry['pixmap'].height()) // 2, entry['pixmap'])
                text_x += entry['pixmap'].width() + 6

            painter.drawText(text_x, 0, width - text_x, label_height, Qt.AlignVCenter, entry['text'])
            painter.end()
            entry['label'].setPixmap(combined)

        entry['redraw'] = redraw
        redraw(False)

        def enter_event(_event, redraw=redraw):
            redraw(True)

        def leave_event(_event, redraw=redraw):
            redraw(False)

        def mouse_press_event(_event, action=action):
            self._emit(action)

        label.enterEvent = enter_event
        label.leaveEvent = leave_event
        label.mousePressEvent = mouse_press_event
        label.setCursor(Qt.PointingHandCursor)

        self._action_items.append(entry)
        self.layout.addWidget(label)
        self._apply_width()

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

    def menu_actions(self):
        """已经加进来的 QAction（条目是自己画的，Qt 的 actions() 拿不到）。"""
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
        self.move(pos)
        self.show()


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

        # Ctrl+V / Shift+Insert 得在这里拦：QTextEdit 的 paste() 不会走 insertFromMimeData
        # 那个虚函数（实测 Qt 6.11 里图片会被当成富文本资源塞进文档，界面上什么也看不到）
        if self._is_paste_key(event) and self._paste_as_attachment():
            return

        super().keyPressEvent(event)

    @staticmethod
    def _is_paste_key(event) -> bool:
        modifiers = event.modifiers()
        if event.key() == Qt.Key.Key_Insert and modifiers & Qt.KeyboardModifier.ShiftModifier:
            return True
        # Ctrl+Shift+V 是"粘贴为纯文本"，别抢
        return (
            event.key() == Qt.Key.Key_V
            and bool(modifiers & Qt.KeyboardModifier.ControlModifier)
            and not modifiers & Qt.KeyboardModifier.ShiftModifier
        )

    def _paste_as_attachment(self) -> bool:
        clipboard = QApplication.clipboard()
        source = clipboard.mimeData() if clipboard is not None else None
        if not hasattr(self.parent_, "can_attach_mime") or not self.parent_.can_attach_mime(source):
            return False
        return bool(self.parent_.attach_from_mime(source))

    def canInsertFromMimeData(self, source):
        """图片/文件交给聊天窗当附件：这里一律拒绝，免得被插成看不见的文档资源。"""
        if hasattr(self.parent_, "can_attach_mime") and self.parent_.can_attach_mime(source):
            return False
        return super().canInsertFromMimeData(source)

    def insertFromMimeData(self, source):
        """兜底：有调用方直接调这个函数时也当附件处理。"""
        if hasattr(self.parent_, "attach_from_mime") and self.parent_.attach_from_mime(source):
            return
        super().insertFromMimeData(source)


class HackerAttachmentChip(QFrame):
    """待发送附件的小标签（名字 + 大小 + 移除）。"""

    def __init__(self, attachment: dict, on_remove=None, parent=None):
        from ...ai import attachment as attachment_api

        super().__init__(parent)
        self.setProperty("attachment", attachment)
        self.setStyleSheet("""
            HackerAttachmentChip {
                background: rgba(0, 255, 0, 16);
                border: 1px solid rgba(0, 255, 0, 70);
                border-radius: 6px;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 4, 2)
        layout.setSpacing(6)

        mark = "🖼" if attachment.get("kind") == "image" else "📄"
        label = HackerLabel(f"{mark} {attachment.get('name')}（{attachment_api.human_size(attachment.get('size'))}）")
        label.setStyleSheet("QLabel { color: #00FF88; background: transparent; border: none; }")
        layout.addWidget(label)

        if on_remove is not None:
            close = HackerBubbleAction("×", "移除这个附件")
            close.clicked.connect(lambda: on_remove(attachment))
            layout.addWidget(close)


# BASE
class ModelChat(QWidget, ModelChatABS, metaclass=CombinedMeta):
    def __init__(
        self,
        ai_name: str, model: str,
        is_local: bool,
        api_key: str | None = None,
        base_url: str | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.is_local = is_local
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

        # 记忆面板可能还没建过（比如设置页没打开就先聊天），取不到回调就跳过
        memory_callback = SharingData.add_memory_to_ui.get(model)
        if memory_callback is not None:
            self.ai_llm.memory_signal.connect(memory_callback)

        # 同一个实例会被多个聊天页共用，协作提示只接一次
        coop_signal = getattr(self.ai_llm, "coop_signal", None)
        if coop_signal is not None and not getattr(self.ai_llm, "_coop_notify_bound", False):
            coop_signal.connect(self.on_coop_event)
            self.ai_llm._coop_notify_bound = True

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

    @staticmethod
    def return_llm_class(model) -> local.LLM | cloud.LLM:
        return cache_llm_class[model]

    def chat_finished(self, all_message):
        self.chat.enable_send_button()

        # 插件可以改最终回复（流式已经把原文写进气泡了，这里按需重写）
        final = self._plugin_text(all_message or "", "assistant")
        bubble = self.current_assistant_bubble
        if bubble is not None and final and final != (all_message or ""):
            bubble.text_label.setText(final)
            self.chat.update_bubble_widths()
            self.chat.scroll_to_bottom()

        from ... import emit_sdk_event, plugin_manager

        try:
            plugin_manager().emit_event("chat_finished", {"reply": final})
        except Exception:  # noqa: BLE001
            pass
        emit_sdk_event("chat_finished", {"reply": final})

    def add_user_msg(self, msg: str, attachments=None):
        self.current_assistant_bubble = self.chat.add_assistant_msg()
        self.chat.disable_send_button()

        attachments = list(attachments or [])
        self._warn_if_blind(attachments)

        skill = getattr(self.chat, "active_skill", None)
        prompt = self._combined_prompt(skill)
        msg = self._plugin_text(msg, "user")

        t = derfer.LLMAICallback(self.ai_llm, msg, self, skill=prompt, attachments=attachments)
        self.worker = t
        t.finished.connect(self.chat_finished)
        t.text_chunk.connect(self.add_assistant_msg)
        t.tool_event.connect(self.on_tool_event)
        t.start()

    @staticmethod
    def _plugin_text(text: str, role: str) -> str:
        """让插件改用户输入（chat_send）或回复（chat_reply）。"""
        from ... import plugin_manager

        try:
            return plugin_manager().chat_text(text, role)
        except Exception:  # noqa: BLE001 - 插件坏了不能挡住聊天
            return text

    @staticmethod
    def _combined_prompt(skill) -> str | None:
        """技能提示词 + 插件要求的系统提示词，一起当成 system 段注入。

        都没有就返回 None —— 别给 LLM 传一个没意义的空串。
        """
        from ... import plugin_prompts

        parts = []
        prompt = (skill or {}).get("prompt")
        if isinstance(prompt, str) and prompt.strip():
            parts.append(prompt.strip())
        parts.extend(item for item in plugin_prompts() if str(item).strip())
        return "\n\n".join(parts) if parts else None

    def _warn_if_blind(self, attachments):
        """带了图片但模型看不见图时直说 —— 否则用户只会以为"AI 没收到图片"。

        提示只是锦上添花，任何异常都不能挡住发送。
        """
        from ...ai import attachment as attachment_api

        try:
            if not attachment_api.images(attachments) or not getattr(self, "is_local", False):
                return
            model = getattr(self.ai_llm, "model", "")
            if attachment_api.can_see_images(model):
                return
        except Exception:  # noqa: BLE001
            return

        HackerNotify(
            f"{model} 是纯文本模型，看不了图片（换成带 vision 的模型，"
            "或用文字描述图片内容）",
            "warning",
            5000,
        )

    def on_tool_event(self, event: dict):
        """音频挂到当前气泡上等用户点播放；其它事件先忽略（MCP 工具的结果还是走文本）。"""
        if event.get("type") != "audio":
            return
        data = event.get("data")
        if not data or self.current_assistant_bubble is None:
            return

        self.current_assistant_bubble.attach_audio(data)
        transcript = event.get("transcript")
        if transcript and not self.current_assistant_bubble.text().strip():
            self.current_assistant_bubble.append_text(transcript)
        self.chat.scroll_to_bottom()

    @staticmethod
    def on_coop_event(event: dict):
        stage = event.get("stage")
        agent = event.get("agent") or "协作模型"

        if stage == "draft":
            HackerNotify("多模型协作：主模型正在出初稿…", "info", 2000)
        elif stage == "review_start":
            HackerNotify(f"多模型协作：{agent} 正在评审…", "info", 2000)
        elif stage == "review_done":
            HackerNotify(f"{agent} 评审完成", "info", 1500)
        elif stage == "agent_start":
            HackerNotify(f"多模型协作：{agent} 正在回答…", "info", 2000)
        elif stage == "agent_done":
            HackerNotify(f"{agent} 回答完成", "info", 1500)
        elif stage == "final":
            HackerNotify("多模型协作：主模型正在定稿…", "info", 2000)
        elif stage == "agent_error":
            HackerNotify(f"{agent} 协作失败：{event.get('detail', '未知错误')}", "error", 4000)
        elif stage == "empty":
            HackerNotify(
                f"{event.get('detail', '协作没有生效')}（协作设置里检查模型与开关）",
                "warning",
                3500,
            )

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
Notify = HackerNotify
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
