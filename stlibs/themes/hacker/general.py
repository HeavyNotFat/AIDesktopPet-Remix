import os

from ... import Config, ConfigLoader

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, Signal


class GeneralPage(QWidget):
    opacity_changed = Signal(int)
    size_changed = Signal(int)
    rotate_changed = Signal(int)
    model_live2d = Signal(str)

    def __init__(self, parent):
        super().__init__(parent)
        from . import HackerLabel, HackerLineEdit, HackerSlider, HackerComboBox, HackerButton

        self.setObjectName("General")
        self.setWindowTitle("常规设置")
        self.window_title = HackerLabel(self.windowTitle(), self)
        self.window_title.set_center()
        self.window_title.setGeometry(0, 0, self.width(), 30)

        # 宠物形象
        HackerLabel("形象", self).setGeometry(10, 85, 120, 20)
        self.select_character = HackerComboBox(self)
        self.select_character.addItems(os.listdir("./resources/model") + os.listdir("./resources/static"))
        self.select_character.setCurrentText(Config.model_live2d)
        self.select_character.currentTextChanged.connect(self.check_character)
        self.select_character.setGeometry(180, 80, 250, 20)

        # 给桌宠命名
        HackerLabel("名字", self).setGeometry(10, 45, 120, 20)
        self.name_edit = HackerLineEdit("可爱の名字", self)
        self.name_edit.setText(Config.name if Config.name else self.select_character.currentText())
        self.name_edit.textChanged.connect(self.check_name)
        self.name_edit.setGeometry(180, 40, 250, 20)

        # 设置角色透明度，大小，旋转角度
        HackerLabel("透明度", self).setGeometry(10, 120, 120, 20)
        self.opacity = HackerSlider(Qt.Orientation.Horizontal, self)
        self.opacity.setGeometry(180, 120, 250, 20)
        self.opacity.setValue(Config.opacity)
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

        self.save_button = HackerButton("保存", parent=self)
        self.save_button.set_border()
        self.save_button.setGeometry(20, 230, 100, 30)
        self.save_button.clicked.connect(lambda: ConfigLoader.save_config(Config))

    def resizeEvent(self, event, /):
        super().resizeEvent(event)
        self.window_title.setGeometry(0, 0, self.width(), 30)

    def check_name(self, name):
        Config.name = name
        ConfigLoader.save_config(Config)

    def check_character(self, character):
        if os.path.exists(f"./resources/model/{character}/3") or os.path.exists(f"./resources/model/{character}/2"):
            Config.model_live2d = character
            Config.static_model = ""
            self.model_live2d.emit(character)
        else:
            Config.model_live2d = ""
            Config.static_model = character
        ConfigLoader.save_config(Config)
