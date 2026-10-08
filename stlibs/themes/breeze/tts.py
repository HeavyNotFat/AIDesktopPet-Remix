
from __future__ import annotations

from PySide6.QtWidgets import QVBoxLayout, QWidget

from .primitives import BreezeLabel, BreezeTabWidget
from .theme import SURFACE, TEXT_DIM, font_css
from .window import PageHint, PageTitle


class _Placeholder(QWidget):
    """占位页：写清楚"还没实现"，别让用户以为是坏的。"""

    def __init__(self, parent=None, text: str = ""):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        label = BreezeLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet(
            f"QLabel {{ color: {TEXT_DIM}; background: transparent; border: none; {font_css(13)} }}"
        )
        layout.addWidget(label)
        layout.addStretch()


class Basic(_Placeholder):
    def __init__(self, parent):
        super().__init__(parent, "语音基础设置还没实现：音色、语速、音量随后会接在这里。")


class Emotion(_Placeholder):
    def __init__(self, parent):
        super().__init__(parent, "情感设置还没实现：打算让模型按情绪挑不同的语气参数。")


class Interaction(_Placeholder):
    def __init__(self, parent):
        super().__init__(parent, "交互设置还没实现：唤醒词、打断时机这些会放在这一页。")


class TTSPage(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("TTS")
        self.setWindowTitle("语音设置")
        self.setStyleSheet(f"QWidget#TTS {{ background: {SURFACE}; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)
        root.addWidget(PageTitle(self.windowTitle()))
        root.addWidget(PageHint("语音能力还在铺路：这里先把入口留好，接上之后三页会各自生效。"))

        self.tab_widget = BreezeTabWidget(self)
        self.tab_widget.addTab(Basic(self), "基础")
        self.tab_widget.addTab(Emotion(self), "情感")
        self.tab_widget.addTab(Interaction(self), "交互")
        root.addWidget(self.tab_widget, 1)


__all__ = ["Basic", "Emotion", "Interaction", "TTSPage"]
