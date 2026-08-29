from PySide6.QtWidgets import QWidget, QVBoxLayout


class Live2D(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        from . import HackerLabel, HackerSwitch, HackerComboBox, MAPPING_ANIMATION, MAPPING_SPECTIAL_ANIMATION

        HackerLabel("智能控制", self).setGeometry(10, 10, 180, 30)
        smart_control = HackerSwitch(self)
        smart_control.setGeometry(100, 5, 80, 30)

        HackerLabel("AI 控制", self).setGeometry(10, 45, 180, 30)
        ai_control = HackerSwitch(self)
        ai_control.setGeometry(100, 40, 80, 30)

        # 自定义
        HackerLabel("自定义", self).setGeometry(10, 100, 180, 30)
        HackerLabel("动作",  self).setGeometry(10, 140, 180, 30)
        action_combo = HackerComboBox(self)
        action_combo.addItems(MAPPING_ANIMATION.keys())
        action_combo.addItems(MAPPING_SPECTIAL_ANIMATION.keys())
        action_combo.setGeometry(90, 140, 200, 30)
        # X, Y, DX, DY
        


class Static(QWidget):
    def __init__(self, parent):
        super().__init__(parent)


class AnimationPage(QWidget):
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
        self.tab_widget = HackerTabWidget(self)
        self.tab_widget.addTab(Live2D(self), "Live2D 动画")
        self.tab_widget.addTab(Static(self), "静态 动画")
        layout.addWidget(self.tab_widget)
        self.setLayout(layout)

    def resizeEvent(self, event, /):
        super().resizeEvent(event)
        self.window_title.setGeometry(0, 0, self.width(), 30)
