
from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ... import Config, ConfigLoader
from .primitives import (
    BreezeButton,
    BreezeCard,
    BreezeComboBox,
    BreezeLineEdit,
    BreezeSlider,
)
from .theme import SURFACE
from .window import PageHint, PageTitle


class GeneralPage(QWidget):
    """常规设置：改完立刻生效（信号发给设置窗，再转成桌宠的实时调整）。"""

    opacity_changed = Signal(int)
    size_changed = Signal(int)
    rotate_changed = Signal(int)
    model_live2d = Signal(str)

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("General")
        self.setWindowTitle("常规设置")
        self.setStyleSheet(f"QWidget#General {{ background: {SURFACE}; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)
        root.addWidget(PageTitle(self.windowTitle()))

        # 表单区放滚动里：窗口小的时候不至于挤没
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
        self.select_character.addItems(self._characters())
        current = Config.static_model if Config.static_model else Config.model_live2d
        if current:
            self.select_character.setCurrentText(current)
        self.select_character.currentTextChanged.connect(self.check_character)
        form.addWidget(BreezeCard("形象", self.select_character, "Live2D 模型或静态序列帧"))

        self.opacity = self._slider(0, 100, int(Config.opacity * 100 if Config.opacity <= 1 else Config.opacity))
        self.opacity.valueChanged.connect(self.opacity_changed.emit)
        form.addWidget(BreezeCard("透明度", self.opacity,
                                  "越往左越透明", stacked=True))

        self.size = self._slider(10, 110, int(Config.size))
        self.size.valueChanged.connect(self.size_changed.emit)
        form.addWidget(BreezeCard("大小", self.size, "桌宠显示比例（%）", stacked=True))

        self.rotate = self._slider(0, 720, int(Config.rotate))
        self.rotate.valueChanged.connect(self.rotate_changed.emit)
        form.addWidget(BreezeCard("旋转角度", self.rotate, "单位：度", stacked=True))

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
    def _characters() -> list[str]:
        """可用形象：Live2D 模型目录 + 静态帧目录，读不到就返回空列表。"""
        names: list[str] = []
        for folder in ("./resources/character/model", "./resources/character/static"):
            try:
                names.extend(sorted(os.listdir(folder)))
            except OSError:
                continue
        return names

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

    def check_character(self, character):
        """Live2D 目录里有模型文件就当 Live2D，否则当静态序列帧。"""
        if os.path.exists(f"./resources/character/model/{character}/3") or \
                os.path.exists(f"./resources/character/model/{character}/2"):
            Config.model_live2d = character
            Config.static_model = ""
            self.model_live2d.emit(character)
        else:
            Config.model_live2d = ""
            Config.static_model = character
        ConfigLoader.save_config()


__all__ = ["GeneralPage"]
