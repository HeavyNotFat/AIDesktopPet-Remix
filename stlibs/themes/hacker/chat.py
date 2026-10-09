
import base64

from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import QByteArray, QPoint, QSize, Qt, Signal
from PySide6.QtGui import QAction, QFont, QFontDatabase, QImage, QPixmap

from ... import Config, derfer

from .feedback import HackerNotify
from .menu import HackerMenu
from .primitives import HackerButton, HackerLabel, HackerScrollArea, HackerTextEdit
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
        """回复底下的动作栏：默认只有复制，有音频时多一个播放。"""
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
        """挂上语音但不自动播，等用户点播放。"""
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
        """图片放缩略图，文档放一个小标签。"""
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

        # Ctrl+V / Shift+Insert 得在这里拦，QTextEdit 的 paste() 不会走 insertFromMimeData
        if self._is_paste_key(event) and self._paste_as_attachment():
            return

        super().keyPressEvent(event)

    @staticmethod
    def _is_paste_key(event) -> bool:
        modifiers = event.modifiers()
        if event.key() == Qt.Key.Key_Insert and modifiers & Qt.KeyboardModifier.ShiftModifier:
            return True
        # Ctrl+Shift+V 是粘贴为纯文本，别抢
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
        """图片和文件交给聊天窗当附件，这里一律拒绝。"""
        if hasattr(self.parent_, "can_attach_mime") and self.parent_.can_attach_mime(source):
            return False
        return super().canInsertFromMimeData(source)

    def insertFromMimeData(self, source):
        """兜底：有调用方直接调这个函数时也当附件处理。"""
        if hasattr(self.parent_, "attach_from_mime") and self.parent_.attach_from_mime(source):
            return
        super().insertFromMimeData(source)


class HackerChatWidget(QWidget):
    # (正文, 附件列表)：附件跟着信号走，免得接收方拿到空列表
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
        """菜单每次重建，设置页里刚加的技能不用重启就能选到。"""
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
            if isinstance(widget, HackerAttachmentChip) and self._is_same_attachment(widget, attachment):
                widget.setParent(None)
                widget.deleteLater()
                break
        self.attachment_bar.setVisible(bool(self.attachments))

    @staticmethod
    def _is_same_attachment(chip: "HackerAttachmentChip", attachment: dict) -> bool:
        """chip 上挂的是不是这份附件（动态属性取回来的是副本，只比 is 不成立）。"""
        stored = chip.property("attachment")
        return stored is attachment or stored == attachment

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
        """这份剪切板或拖拽内容能不能当附件，不产生副作用。"""
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
        """剪切板里的图片可能是 QImage 也可能是 QPixmap，统一成 QPixmap。"""
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
        """剪切板或拖拽进来的东西，图片优先，其次是文件路径。"""
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
        from PySide6.QtCore import QBuffer

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

        # 插件命令：/名字 参数，认不出来再当技能
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
            # 只打了 /技能名，当成切换技能，不发送
            self.input_edit.clear()
            return

        pending = self.take_attachments()
        self.add_user_msg(text, skill=self.active_skill, attachments=pending)
        # 附件跟着信号走，ModelChat 再取一次时已经被这里清空了
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
