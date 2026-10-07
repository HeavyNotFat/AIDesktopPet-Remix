from ...plugins.manager import PluginsPanel

from PySide6.QtWidgets import QWidget, QTableWidgetItem
from PySide6.QtCore import QRect, QSize, Qt


COLUMNS = (("图标", 48), ("插件", 196), ("语言", 106), ("版本", 60), ("状态", 110), ("调用", 46))
ICON_CELL_SIZE = 26


class PluginsWidgetScroll(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        from . import HackerLabel, HackerTable, HackerButton, HackerSwitch

        self.panel = PluginsPanel()

        HackerLabel("启用插件系统", self).setGeometry(20, 12, 210, 30)
        self.enable_switch = HackerSwitch(parent=self)
        self.enable_switch.setGeometry(240, 8, 80, 30)
        self.enable_switch.setChecked(self.panel.enabled())
        self.enable_switch.stateChanged.connect(self.check_enable)

        self.path_label = HackerLabel("", self)
        self.path_label.setGeometry(20, 46, 580, 30)

        self.table = HackerTable(parent=self)
        self.table.setGeometry(20, 80, 580, 250)
        self.table.setHorizontalHeaderLabels([name for name, _width in COLUMNS])
        for index, (_name, width) in enumerate(COLUMNS):
            self.table.setColumnWidth(index, width)
        self.table.setEditTriggers(HackerTable.EditTrigger.NoEditTriggers)

        self.detail = HackerLabel("", self)
        self.detail.setWordWrap(True)
        self.detail.setGeometry(20, 336, 580, 40)

        for index, (label, slot) in enumerate((
            ("重新扫描", self.refresh),
            ("启用/停用", self.toggle_selected),
            ("重载插件", self.reload_selected),
            ("打开目录", self.open_folder),
        )):
            button = HackerButton(label, parent=self)
            button.set_border()
            button.setGeometry(20 + index * 110, 380, 100, 30)
            button.clicked.connect(slot)

        self.refresh()

    def refresh(self):
        self.panel.refresh()
        self.enable_switch.setChecked(self.panel.enabled())
        self.path_label.setText(f"插件目录：{self.panel.directory()}")

        rows = self.panel.rows()
        self.table.setRowCount(0)
        for row in rows:
            index = self.table.rowCount()
            self.table.insertRow(index)

            icon_item = QTableWidgetItem()
            if row.get("icon") is not None:
                icon_item.setIcon(row["icon"])
                icon_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setRowHeight(index, max(self.table.verticalHeader().defaultSectionSize(), 32))
            self.table.setItem(index, 0, icon_item)

            cells = (row["title"], row["language"], row["version"], row["state"], row["calls"])
            for column, text in enumerate(cells, start=1):
                self.table.setItem(index, column, QTableWidgetItem(text))

        self._apply_icon_size()
        self.detail.setText(self.panel.hint())

    def _apply_icon_size(self):
        """图标列按 ICON_CELL_SIZE 显示（默认 16px 太小，看不清自定义图）。"""
        self.table.setIconSize(QSize(ICON_CELL_SIZE, ICON_CELL_SIZE))

    def _selected_id(self):
        row = self.table.currentRow()
        return self.panel.selected(row)

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
        """panel 返回 (level, message)，notify 收的是 (text, level)。"""
        from ... import notify

        level, message = result
        notify(message, level)


class PluginsPage(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        from . import HackerLabel, ScrollArea

        self.setObjectName("Plugins")
        self.setWindowTitle("插件")
        self.window_title = HackerLabel(self.windowTitle(), self)
        self.window_title.set_center()
        self.window_title.setGeometry(0, 0, self.width(), 30)

        card = PluginsWidgetScroll(self)
        self.card = card
        scroll = ScrollArea(self)
        scroll.setWidget(card)
        scroll.setGeometry(QRect(10, 40, 620, 430))

    def resizeEvent(self, event, /):
        super().resizeEvent(event)
        self.window_title.setGeometry(0, 0, self.width(), 30)

    def refresh(self):
        """重新扫描插件目录（设置窗打开时、手动刷新时都会走）。"""
        return self.card.refresh()


__all__ = ["COLUMNS", "PluginsPage", "PluginsWidgetScroll"]
