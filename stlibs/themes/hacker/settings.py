import os

from PySide6.QtWidgets import QWidget, QVBoxLayout


class UICardWidgetFixed(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        from . import HackerCard, HackerComboBox

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # 主题here
        theme_combo = HackerComboBox(self)
        for x in os.listdir("./stlibs/themes"):
            if os.path.isdir(f"./stlibs/themes/{x}") and x != "__pycache__":
                theme_combo.addItem(x)
        theme_card = HackerCard(
            "主题",
            theme_combo,
            "界面的主题设置"
        )
        layout.addWidget(theme_card)
        layout.addStretch()


class SettingsPage(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        from . import HackerLabel, HackerScrollArea

        self.setObjectName("Settings")
        self.setWindowTitle("设置")
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 10, 12, 12)
        main_layout.setSpacing(10)

        # 卡片内容
        title = HackerLabel("界面设置")
        title.set_center()
        main_layout.addWidget(title)
        card = UICardWidgetFixed(self)

        scroll = HackerScrollArea(self)
        scroll.setWidget(card)
        main_layout.addWidget(scroll)
