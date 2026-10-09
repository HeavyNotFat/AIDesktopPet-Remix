
from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...plugins.manager import PluginsPanel
from .primitives import BreezeButton, BreezeCard, BreezeLabel, BreezeScrollArea, BreezeSwitch, BreezeTable
from .theme import SURFACE
from .window import PageHint, PageTitle

COLUMNS = (("图标", 52), ("插件", 190), ("语言", 100), ("版本", 70), ("状态", 110), ("调用", 56))
ICON_CELL_SIZE = 26


class PluginsWidgetScroll(QWidget):
    """插件页主体：总开关 + 目录 + 表格 + 一排操作按钮。"""

    def __init__(self, parent):
        super().__init__(parent)
        self.panel = PluginsPanel()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        self.enable_switch = BreezeSwitch()
        self.enable_switch.setChecked(self.panel.enabled())
        self.enable_switch.stateChanged.connect(self.check_enable)
        root.addWidget(BreezeCard("启用插件系统", self.enable_switch, "关掉之后所有插件 hook 都不再触发"))

        self.path_label = BreezeLabel("")
        self.path_label.set_dim()
        root.addWidget(self.path_label)

        self.table = BreezeTable()
        self.table.setHorizontalHeaderLabels([name for name, _width in COLUMNS])
        for index, (_name, width) in enumerate(COLUMNS):
            self.table.setColumnWidth(index, width)
        self.table.setEditTriggers(BreezeTable.EditTrigger.NoEditTriggers)
        self.table.setMinimumHeight(240)
        root.addWidget(self.table, 1)

        self.detail = BreezeLabel("")
        self.detail.setWordWrap(True)
        self.detail.set_dim()
        root.addWidget(self.detail)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        for label, slot in (
            ("重新扫描", self.refresh),
            ("启用/停用", self.toggle_selected),
            ("重载插件", self.reload_selected),
            ("打开目录", self.open_folder),
        ):
            button = BreezeButton(label)
            button.clicked.connect(slot)
            buttons.addWidget(button)
        buttons.addStretch()
        root.addLayout(buttons)

        self.refresh()

    def refresh(self):
        self.panel.refresh()
        self.enable_switch.setChecked(self.panel.enabled())
        self.path_label.setText(f"插件目录：{self.panel.directory()}")

        self.table.setRowCount(0)
        for row in self.panel.rows():
            index = self.table.rowCount()
            self.table.insertRow(index)

            icon_item = QTableWidgetItem()
            if row.get("icon") is not None:
                icon_item.setIcon(row["icon"])
                icon_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setRowHeight(index, max(self.table.verticalHeader().defaultSectionSize(), 32))
            self.table.setItem(index, 0, icon_item)

            for column, text in enumerate(
                (row["title"], row["language"], row["version"], row["state"], row["calls"]), start=1
            ):
                self.table.setItem(index, column, QTableWidgetItem(text))

        # 图标列按 ICON_CELL_SIZE 显示，默认 16px 看不清自定义图
        self.table.setIconSize(QSize(ICON_CELL_SIZE, ICON_CELL_SIZE))
        self.detail.setText(self.panel.hint())

    def _selected_id(self):
        return self.panel.selected(self.table.currentRow())

    def toggle_selected(self):
        self._tell(self.panel.toggle(self._selected_id()))

    def reload_selected(self):
        self._tell(self.panel.reload(self._selected_id()))

    def open_folder(self):
        self._tell(self.panel.open_folder())

    def check_enable(self, enabled: bool):
        self._tell(self.panel.set_enabled(bool(enabled)))

    @staticmethod
    def _tell(result):
        """把 panel 返回的 (level, message) 转给 notify。"""
        from ... import notify

        level, message = result
        notify(message, level)


class PluginsPage(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("Plugins")
        self.setWindowTitle("插件")
        self.setStyleSheet(f"QWidget#Plugins {{ background: {SURFACE}; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)
        root.addWidget(PageTitle(self.windowTitle()))
        root.addWidget(PageHint("插件是普通 Python / JavaScript 目录：放进来、扫一下就能用。"))

        self.card = PluginsWidgetScroll(self)
        scroll = BreezeScrollArea(self)
        scroll.setWidget(self.card)
        self.scroll = scroll
        root.addWidget(scroll, 1)

    def refresh(self):
        """重新扫描插件目录。"""
        return self.card.refresh()


__all__ = ["COLUMNS", "PluginsPage", "PluginsWidgetScroll"]
