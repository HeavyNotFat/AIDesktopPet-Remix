from ... import Config, ConfigLoader, ai_enabled, character

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget


class GeneralPage(QWidget):
    opacity_changed = Signal(int)
    size_changed = Signal(int)
    rotate_changed = Signal(int)
    model_live2d = Signal(str)
    ai_changed = Signal(bool)

    def __init__(self, parent):
        super().__init__(parent)
        from . import HackerButton, HackerComboBox, HackerLabel, HackerLineEdit, HackerSlider, HackerSwitch

        self.setObjectName("General")
        self.setWindowTitle("常规设置")
        self.window_title = HackerLabel(self.windowTitle(), self)
        self.window_title.set_center()
        self.window_title.setGeometry(0, 0, self.width(), 30)

        HackerLabel("形象", self).setGeometry(10, 45, 120, 20)
        self.select_character = HackerComboBox(self)
        self._characters = character.discover()
        self.select_character.addItems([item.label for item in self._characters])
        current = character.current()
        if current is not None:
            self.select_character.setCurrentText(current.label)
        self.select_character.currentTextChanged.connect(self.check_character)
        self.select_character.setGeometry(180, 40, 250, 20)

        HackerLabel("名字", self).setGeometry(10, 85, 120, 20)
        self.name_edit = HackerLineEdit("可爱の名字", self)
        self.name_edit.setText(Config.name if Config.name else self.select_character.currentText())
        self.name_edit.textChanged.connect(self.check_name)
        self.name_edit.setGeometry(180, 80, 250, 20)

        HackerLabel("透明度", self).setGeometry(10, 120, 120, 20)
        self.opacity = HackerSlider(Qt.Orientation.Horizontal, self)
        self.opacity.setGeometry(180, 120, 250, 20)
        raw_opacity = float(Config.opacity)
        self.opacity.setValue(int(raw_opacity * 100) if raw_opacity <= 1 else int(raw_opacity))
        self.opacity.valueChanged.connect(self.opacity_changed.emit)

        HackerLabel("大小", self).setGeometry(10, 155, 120, 20)
        self.size = HackerSlider(Qt.Orientation.Horizontal, self)
        self.size.setGeometry(180, 155, 250, 20)
        self.size.setMinimum(10)
        self.size.setMaximum(110)
        self.size.setValue(Config.size)
        self.size.valueChanged.connect(self.size_changed.emit)

        HackerLabel("旋转角度", self).setGeometry(10, 190, 120, 20)
        self.rotate = HackerSlider(Qt.Orientation.Horizontal, self)
        self.rotate.setGeometry(180, 190, 250, 20)
        self.rotate.setMaximum(720)
        self.rotate.setValue(Config.rotate)
        self.rotate.valueChanged.connect(self.rotate_changed.emit)

        HackerLabel("AI 功能总开关", self).setGeometry(10, 235, 180, 20)
        self.ai_switch = HackerSwitch(self)
        self.ai_switch.setGeometry(180, 230, 80, 30)
        self.ai_switch.setChecked(ai_enabled())
        self.ai_switch.stateChanged.connect(self.check_ai)
        HackerLabel("关闭后隐藏所有 AI 入口，默认关闭", self).setGeometry(270, 235, 350, 20)

        self.save_button = HackerButton("保存", parent=self)
        self.save_button.set_border()
        self.save_button.setGeometry(20, 280, 100, 30)
        self.save_button.clicked.connect(lambda: ConfigLoader.save_config())

    def resizeEvent(self, event, /):
        super().resizeEvent(event)
        self.window_title.setGeometry(0, 0, self.width(), 30)

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
