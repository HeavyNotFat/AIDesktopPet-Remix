import os
from pathlib import Path

from PySide6.QtWidgets import QWidget, QVBoxLayout

from ... import Config, ConfigLoader

# 相对本文件定位，不依赖进程工作目录（打包成 exe、换 cwd 都不会失效）
THEME_ROOT = Path(__file__).resolve().parents[1]


def available_themes() -> list[str]:
    """可用的主题包名（有 __init__.py 的目录）。"""
    try:
        entries = sorted(os.listdir(THEME_ROOT))
    except OSError:
        return []
    return [
        name
        for name in entries
        if name != "__pycache__" and (THEME_ROOT / name / "__init__.py").is_file()
    ]


class UICardWidgetFixed(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        from . import HackerCard, HackerComboBox

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        theme_combo = HackerComboBox(self)
        themes = available_themes()
        theme_combo.addItems(themes)
        current = (Config.theme or "hacker").strip()
        theme_combo.setCurrentText(current if current in themes else (themes[0] if themes else ""))
        theme_combo.currentTextChanged.connect(self.check_theme)

        theme_card = HackerCard(
            "主题",
            theme_combo,
            "界面的主题设置（重启后生效）"
        )
        layout.addWidget(theme_card)
        layout.addStretch()

    @staticmethod
    def check_theme(name: str):
        if not name or name == Config.theme:
            return
        Config.theme = name
        ConfigLoader.save_config()


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
