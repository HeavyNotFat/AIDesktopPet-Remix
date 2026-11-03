from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QScrollArea, QVBoxLayout, QWidget

from ... import ai_enabled
from ...graphics import editors

from .. import base
from .primitives import BreezeTabWidget
from .theme import SURFACE
from .window import PageTitle


class Live2D(editors.Live2DEditor):
    pass


class Static(editors.StaticEditor):
    pass


class Emote(editors.EmoteEditor):
    pass


class AnimationPage(QWidget, base.AnimationABS, metaclass=base.CombinedMeta):
    live2d_mot_signal = Signal(list)
    live2d_exp_signal = Signal(list)
    emote_timeline_signal = Signal(list)
    static_anim_signal = Signal(str)

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("AnimationPage")
        self.setWindowTitle("动画设置")
        self.setStyleSheet(f"QWidget#AnimationPage {{ background: {SURFACE}; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)
        root.addWidget(PageTitle(self.windowTitle()))

        self.live2d = Live2D(self)
        self.live2d.motion_preview.connect(self.live2d_mot_signal.emit)
        self.live2d.expression_preview.connect(self.live2d_exp_signal.emit)

        self.static = Static(self)
        self.static.play_animation.connect(self.static_anim_signal.emit)

        self.emote = Emote(self)
        self.emote.timeline_preview.connect(self.emote_timeline_signal.emit)

        self.tab_widget = BreezeTabWidget(self)
        self.tab_widget.addTab(_scroll(self.live2d), "Live2D 动画")
        self.tab_widget.addTab(_scroll(self.static), "静态动画")
        self.tab_widget.addTab(_scroll(self.emote), "Emote 动画")
        root.addWidget(self.tab_widget, 1)
        self.set_ai_enabled(ai_enabled())

    def set_ai_enabled(self, enabled):
        self.live2d.set_ai_enabled(bool(enabled))


def _scroll(widget: QWidget) -> QScrollArea:
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
    scroll.setWidget(widget)
    return scroll


__all__ = ["AnimationPage", "Emote", "Live2D", "Static"]
