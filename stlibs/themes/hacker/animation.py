from PySide6.QtWidgets import QWidget, QVBoxLayout


class Basic(QWidget):
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
        self.tab_widget.addTab(Basic(self), "Live2D 动画")
        self.tab_widget.addTab(Basic(self), "静态 动画")
        layout.addWidget(self.tab_widget)
        self.setLayout(layout)

    def resizeEvent(self, event, /):
        super().resizeEvent(event)
        self.window_title.setGeometry(0, 0, self.width(), 30)
