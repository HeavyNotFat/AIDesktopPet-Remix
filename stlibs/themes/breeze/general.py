from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QScrollArea, QVBoxLayout, QWidget

from ... import Config, ConfigLoader, ai_enabled, character
from .primitives import (
    BreezeButton,
    BreezeCard,
    BreezeComboBox,
    BreezeLabel,
    BreezeLineEdit,
    BreezeSlider,
    BreezeSwitch,
)
from .theme import SURFACE
from .window import PageHint, PageTitle


class GeneralPage(QWidget):
    opacity_changed = Signal(int)
    size_changed = Signal(int)
    rotate_changed = Signal(int)
    model_live2d = Signal(str)
    ai_changed = Signal(bool)

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("General")
        self.setWindowTitle("常规设置")
        self.setStyleSheet(f"QWidget#General {{ background: {SURFACE}; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)
        root.addWidget(PageTitle(self.windowTitle()))

        holder = QWidget()
        holder.setStyleSheet(f"background: {SURFACE};")
        form = QVBoxLayout(holder)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(8)

        self.name_edit = BreezeLineEdit("给桌宠取个名字")
        self.name_edit.setText(Config.name if Config.name else "")
        self.name_edit.textChanged.connect(self.check_name)
        form.addWidget(BreezeCard("名字", self.name_edit, "显示在聊天窗与提示里的人称"))

        self.select_character = BreezeComboBox()
        self._characters = character.discover()
        self.select_character.addItems([item.label for item in self._characters])
        current = character.current()
        if current is not None:
            self.select_character.setCurrentText(current.label)
        self.select_character.currentTextChanged.connect(self.check_character)
        form.addWidget(BreezeCard("形象", self.select_character, "Live2D / 静态序列帧 / Emote PSB"))

        raw_opacity = float(Config.opacity)
        self.opacity = self._slider(0, 100, int(raw_opacity * 100) if raw_opacity <= 1 else int(raw_opacity))
        self.opacity.valueChanged.connect(self.opacity_changed.emit)
        form.addWidget(BreezeCard("透明度", self.opacity, "越往左越透明", stacked=True))

        self.size = self._slider(10, 110, int(Config.size))
        self.size.valueChanged.connect(self.size_changed.emit)
        form.addWidget(BreezeCard("大小", self.size, "桌宠显示比例（%）", stacked=True))

        self.rotate = self._slider(0, 720, int(Config.rotate))
        self.rotate.valueChanged.connect(self.rotate_changed.emit)
        form.addWidget(BreezeCard("旋转角度", self.rotate, "单位：度", stacked=True))

        ai_row = QWidget()
        ai_layout = QHBoxLayout(ai_row)
        ai_layout.setContentsMargins(0, 0, 0, 0)
        ai_layout.addWidget(BreezeLabel("关闭后隐藏所有 AI 入口"))
        ai_layout.addStretch()
        self.ai_switch = BreezeSwitch()
        self.ai_switch.setChecked(ai_enabled())
        self.ai_switch.stateChanged.connect(self.check_ai)
        ai_layout.addWidget(self.ai_switch)
        form.addWidget(BreezeCard("AI 功能总开关", ai_row, "默认关闭；关闭后所有 AI 功能与入口都会停用", stacked=True))

        form.addWidget(PageHint("改动会立刻生效，并写入 resources/configure.json。"))
        form.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setStyleSheet(f"QScrollArea {{ background: {SURFACE}; border: none; }}")
        scroll.setWidget(holder)
        root.addWidget(scroll, 1)

        bottom = QHBoxLayout()
        bottom.addStretch()
        self.save_button = BreezeButton("保存配置")
        self.save_button.set_border()
        self.save_button.clicked.connect(lambda: ConfigLoader.save_config())
        bottom.addWidget(self.save_button)
        root.addLayout(bottom)

    @staticmethod
    def _slider(minimum: int, maximum: int, value: int) -> BreezeSlider:
        slider = BreezeSlider(Qt.Orientation.Horizontal)
        slider.setMinimum(minimum)
        slider.setMaximum(maximum)
        slider.setValue(max(minimum, min(maximum, value)))
        return slider

    def check_name(self, name):
        Config.name = name
        ConfigLoader.save_config()

    def check_character(self, label):
        selected = character.select(label)
        if selected is None:
            return
        self._sync_appearance()
        self.model_live2d.emit(selected.name)

    def _sync_appearance(self):
        raw = float(Config.opacity)
        opacity = int(raw * 100) if raw <= 1 else int(raw)
        for widget, value in ((self.opacity, opacity), (self.size, int(Config.size)),
                              (self.rotate, int(Config.rotate))):
            widget.blockSignals(True)
            widget.setValue(max(widget.minimum(), min(widget.maximum(), value)))
            widget.blockSignals(False)
        self.opacity_changed.emit(self.opacity.value())
        self.size_changed.emit(self.size.value())
        self.rotate_changed.emit(self.rotate.value())

    def check_ai(self, value):
        self.ai_changed.emit(bool(value))


__all__ = ["GeneralPage"]
