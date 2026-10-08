
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtWidgets import QVBoxLayout, QWidget

from ... import Config, ConfigLoader
from .primitives import BreezeCard, BreezeComboBox, BreezeScrollArea
from .theme import SURFACE
from .window import PageHint, PageTitle

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
    """界面设置卡片区：换主题（重启生效）。"""

    def __init__(self, parent):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        theme_combo = BreezeComboBox(self)
        themes = available_themes()
        theme_combo.addItems(themes)
        current = (Config.theme or "hacker").strip()
        theme_combo.setCurrentText(current if current in themes else (themes[0] if themes else ""))
        theme_combo.currentTextChanged.connect(self.check_theme)

        layout.addWidget(BreezeCard("主题", theme_combo, "换一套界面外观（重启后生效）"))
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
        self.setObjectName("Settings")
        self.setWindowTitle("设置")
        self.setStyleSheet(f"QWidget#Settings {{ background: {SURFACE}; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)
        root.addWidget(PageTitle("界面设置"))
        root.addWidget(PageHint("主题包在 stlibs/themes/ 下，一个目录就是一套主题。"))

        self.card = UICardWidgetFixed(self)
        scroll = BreezeScrollArea(self)
        scroll.setWidget(self.card)
        root.addWidget(scroll, 1)


__all__ = ["SettingsPage", "UICardWidgetFixed", "available_themes"]
