from ... import ai_enabled
from ...graphics import editors

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QScrollArea, QVBoxLayout, QWidget

from .. import base


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
        from . import HackerLabel, HackerTabWidget

        self.setObjectName("AnimationPage")
        self.setWindowTitle("动画设置")
        self.window_title = HackerLabel(self.windowTitle(), self)
        self.window_title.set_center()
        self.window_title.setGeometry(0, 0, self.width(), 30)

        layout = QVBoxLayout()
        layout.setContentsMargins(20, 40, 20, 20)

        self.live2d = Live2D(self)
        self.live2d.motion_preview.connect(self.live2d_mot_signal.emit)
        self.live2d.expression_preview.connect(self.live2d_exp_signal.emit)

        self.static = Static(self)
        self.static.play_animation.connect(self.static_anim_signal.emit)

        self.emote = Emote(self)
        self.emote.timeline_preview.connect(self.emote_timeline_signal.emit)

        self.tab_widget = HackerTabWidget(self)
        self.tab_widget.addTab(_scroll(self.live2d), "Live2D 动画")
        self.tab_widget.addTab(_scroll(self.static), "静态动画")
        self.tab_widget.addTab(_scroll(self.emote), "Emote 动画")
        layout.addWidget(self.tab_widget)
        self.setLayout(layout)
        self.set_ai_enabled(ai_enabled())

    def set_ai_enabled(self, enabled):
        self.live2d.set_ai_enabled(bool(enabled))

    def resizeEvent(self, event, /):
        super().resizeEvent(event)
        self.window_title.setGeometry(0, 0, self.width(), 30)


def _scroll(widget):
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
    scroll.setWidget(widget)
    return scroll
