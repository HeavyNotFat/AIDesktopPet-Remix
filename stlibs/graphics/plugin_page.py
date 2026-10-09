from __future__ import annotations

import inspect

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..plugins.pages import MAX_COLUMNS, FormRow, SettingsPageSpec
from .palette import palette


def build_plugin_page(spec: SettingsPageSpec, parent=None) -> QWidget:
    """按页面规格建控件：插件 builder 优先，否则渲染声明式表单。"""
    if callable(spec.builder):
        built = _call_builder(spec, parent)
        if built is not None:
            return built
    return PluginSettingsPage(spec, parent)


def _call_builder(spec: SettingsPageSpec, parent):
    """调插件的 builder；出错就返回一张写着原因的页面。"""
    try:
        built = spec.builder(parent) if _wants_parent(spec.builder) else spec.builder()
    except Exception as exc:  # noqa: BLE001 - 插件页面出错只影响它自己
        return message_page(spec.title, f"插件页面构建失败：{type(exc).__name__}: {exc}")

    if not isinstance(built, QWidget):
        return message_page(spec.title, "builder 必须返回一个 QWidget")
    return built


def _wants_parent(func) -> bool:
    try:
        parameters = inspect.signature(func).parameters.values()
    except (TypeError, ValueError):
        return True
    return any(
        item.kind in (item.POSITIONAL_ONLY, item.POSITIONAL_OR_KEYWORD)
        for item in parameters
    )


def message_page(title: str, message: str) -> QWidget:
    """一张只有标题和一行说明的页面。"""
    page = QWidget()
    page.setWindowTitle(title)
    layout = QVBoxLayout(page)
    layout.setContentsMargins(16, 14, 16, 14)
    layout.setSpacing(8)
    layout.addWidget(_title_label(title))
    layout.addWidget(_hint_label(message))
    layout.addStretch()
    return page


class PluginSettingsPage(QWidget):
    """插件设置页：标题 + 说明 + 表单行，控件全部取当前主题。"""

    def __init__(self, spec: SettingsPageSpec, parent=None):
        super().__init__(parent)
        self.spec = spec
        self.setObjectName(f"PluginPage_{spec.key}")
        # 设置窗拿 windowTitle() 当页面标题
        self.setWindowTitle(spec.title)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)
        root.addWidget(_title_label(spec.title))
        if spec.hint:
            root.addWidget(_hint_label(spec.hint))

        content = QWidget()
        self.rows_layout = QVBoxLayout(content)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(8)
        self.controls = {}

        for row in spec.rows:
            widget = self._build_row(row)
            if widget is not None:
                self.rows_layout.addWidget(widget)
        if not spec.rows:
            self.rows_layout.addWidget(_hint_label("这个插件没有声明任何设置。"))
        self.rows_layout.addStretch()

        scroll = _scroll_area()
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

    def _build_row(self, row: FormRow):
        builder = getattr(self, f"_row_{row.type}", None)
        if not callable(builder):
            return None
        try:
            return builder(row)
        except Exception as exc:  # noqa: BLE001 - 单行出错不该整页空白
            return _hint_label(f"这一行没画出来：{type(exc).__name__}: {exc}")

    def _row_label(self, row: FormRow):
        label = _hint_label(row.text, dim=False)
        label.setWordWrap(True)
        return label

    def _row_hint(self, row: FormRow):
        return _hint_label(row.text)

    def _row_section(self, row: FormRow):
        """一块栅格卡片：按 columns 分列排子行，子行用 span 跨列。"""
        columns = max(1, min(MAX_COLUMNS, int(row.columns or 1)))
        body = QWidget()
        grid = QGridLayout(body)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)

        cursor_row = 0
        cursor_col = 0
        for child in row.rows:
            widget = self._build_row(child)
            if widget is None:
                continue
            span = self._span_of(child, columns)
            if cursor_col + span > columns:
                cursor_row += 1
                cursor_col = 0
            grid.addWidget(widget, cursor_row, cursor_col, 1, span)
            cursor_col += span
            if cursor_col >= columns:
                cursor_row += 1
                cursor_col = 0

        for column in range(columns):
            grid.setColumnStretch(column, 1)
        return _plain_card(row.title, body, row.hint)

    def _row_map(self, row: FormRow):
        """一组「名称 → 值」的只读展示：左列名称、右列值，横向铺开。"""
        body = QWidget()
        grid = QGridLayout(body)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(6)
        for index, item in enumerate(row.items):
            name = _hint_label(str(item.get("key", "")), dim=True)
            value = _hint_label(_text_value(item.get("value")), dim=False)
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            grid.addWidget(name, index, 0, Qt.AlignmentFlag.AlignTop)
            grid.addWidget(value, index, 1, Qt.AlignmentFlag.AlignTop)
        grid.setColumnStretch(1, 1)
        return _plain_card(row.title, body, row.hint)

    def _span_of(self, row: FormRow, columns: int) -> int:
        """子行占几列：文字行默认整行，控件行默认一列。"""
        span = int(row.span or 1)
        if row.type in ("label", "hint", "map") and span <= 1:
            span = columns
        return max(1, min(columns, span))

    def _row_text(self, row: FormRow):
        return self._line_row(row)

    def _row_password(self, row: FormRow):
        return self._line_row(row, password=True)

    def _row_number(self, row: FormRow):
        return self._line_row(row, number=True)

    def _row_switch(self, row: FormRow):
        switch, signal = _switch_control()
        switch.setChecked(bool(self._stored(row, bool(row.default))))
        signal.connect(lambda checked, r=row: self._commit(r, bool(checked)))
        self.controls[row.key] = switch
        return _card(row.title, switch, row.hint)

    def _row_select(self, row: FormRow):
        combo = _theme_class("ComboBox", QComboBox)()
        for option in row.options:
            combo.addItem(str(option["label"]), option["value"])
        current = self._stored(row, row.default)
        index = combo.findData(current)
        if index < 0:
            index = combo.findText(str(current))
        combo.setCurrentIndex(index if index >= 0 else 0)
        combo.currentIndexChanged.connect(lambda i, r=row, c=combo: self._commit(r, c.itemData(i)))
        self.controls[row.key] = combo
        return _card(row.title, combo, row.hint, stacked=True)

    def _row_button(self, row: FormRow):
        caption = row.text or row.label or row.action
        button = _theme_class("Button", QPushButton)(caption)
        button.clicked.connect(lambda _checked=False, r=row: self._commit(r, None))
        self.controls[row.key or row.action] = button
        if row.label and row.label != caption:
            return _card(row.label, button, row.hint)
        return button

    def _line_row(self, row: FormRow, password: bool = False, number: bool = False):
        edit = _theme_class("LineEdit", QLineEdit)(row.placeholder or None)
        value = self._stored(row, row.default)
        if password:
            edit.setEchoMode(QLineEdit.EchoMode.Password)
        edit.setText("" if value is None else str(value))
        edit.editingFinished.connect(
            lambda r=row, e=edit, n=number: self._commit_line(r, e, number=n)
        )
        self.controls[row.key] = edit
        return _card(row.title, edit, row.hint, stacked=True)

    def _commit_line(self, row: FormRow, edit, number: bool = False):
        """输入框提交：数字行校验，出界的值按 min/max 夹回。"""
        raw = edit.text()
        if not number:
            self._commit(row, raw)
            return

        value = _to_number(raw)
        if value is None:
            if raw.strip():
                self._notify(f"「{row.title}」要填数字", "warning")
                edit.setText("" if row.default is None else str(row.default))
                return
            # 清空就退回声明里的默认值，免得插件拿到一个 None
            value = row.default
        else:
            value = _clamp(value, row)
        self._commit(row, value)

    def _commit(self, row: FormRow, value):
        manager = _manager()
        if manager is None:
            return
        try:
            manager.settings_action(
                self.spec.plugin, self.spec.key, row.action or row.key, value, key=row.key or None
            )
        except Exception as exc:  # noqa: BLE001 - 插件回调出错不该影响界面
            self._notify(f"设置没生效：{type(exc).__name__}: {exc}", "error")

    def _stored(self, row: FormRow, default=None):
        """这一行现在的值：配置里存过就用存的，否则用默认值。"""
        if not row.key:
            return default
        manager = _manager()
        if manager is None:
            return default
        return manager.settings_for(self.spec.plugin).get(row.key, default)

    @staticmethod
    def _notify(text: str, level: str = "info"):
        from .. import notify

        notify(text, level)


def _manager():
    from .. import plugin_manager

    try:
        return plugin_manager()
    except Exception:  # noqa: BLE001 - 插件系统坏了也不该让设置页打不开
        return None


def _to_number(raw: str):
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    return int(number) if number.is_integer() else number


def _clamp(value, row: FormRow):
    if value is None:
        return None
    if isinstance(row.minimum, (int, float)) and value < row.minimum:
        return row.minimum
    if isinstance(row.maximum, (int, float)) and value > row.maximum:
        return row.maximum
    return value


def _theme_class(name: str, fallback):
    """取当前主题的控件类，没绑主题或主题没给就退回原生 Qt 控件。"""
    from .. import SharingData

    theme = getattr(SharingData, "theme", None)
    factory = getattr(theme, name, None) if theme is not None else None
    return factory if isinstance(factory, type) else fallback


def _card(title: str, widget: QWidget, hint: str = "", stacked: bool = False) -> QWidget:
    card_class = _theme_class("CardWidget", None)
    if card_class is None:
        return _plain_card(title, widget, hint)

    try:
        return card_class(title, widget, description=hint, stacked=stacked)
    except TypeError:  # 主题卡片签名不一样，退回最朴素的用法
        return card_class(title, widget)


def _plain_card(title: str, widget: QWidget, hint: str = "") -> QWidget:
    """没有主题时的卡片：标题 + 控件 + 说明竖排。"""
    card = QWidget()
    layout = QVBoxLayout(card)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(4)
    if title:
        layout.addWidget(_hint_label(title, dim=False))
    layout.addWidget(widget)
    if hint:
        layout.addWidget(_hint_label(hint))
    return card


def _switch_control():
    """开关控件与它的信号：主题 Switch 优先，没有就用 QCheckBox。"""
    switch_class = _theme_class("Switch", None)
    if switch_class is None:
        box = QCheckBox()
        return box, box.toggled

    switch = switch_class()
    return switch, switch.stateChanged


def _scroll_area() -> QScrollArea:
    area = _theme_class("ScrollArea", QScrollArea)()
    area.setWidgetResizable(True)
    area.setFrameShape(QScrollArea.Shape.NoFrame)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    return area


def _title_label(text: str) -> QLabel:
    label = _theme_class("Label", QLabel)(text)
    colors = palette()
    label.setStyleSheet(
        f"QLabel {{ color: {colors.text}; background: transparent; border: none;"
        f" font-size: 16px; font-weight: 600; }}"
    )
    return label


def _text_value(value) -> str:
    """状态映射里的值：字典/列表也尽量显示成人能看的样子。"""
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "开" if value else "关"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (list, tuple)):
        return "、".join(_text_value(item) for item in value) or "—"
    if isinstance(value, dict):
        return "；".join(f"{key}：{_text_value(item)}" for key, item in value.items()) or "—"
    text = str(value).strip()
    return text or "—"


def _hint_label(text: str, dim: bool = True) -> QLabel:
    label = _theme_class("Label", QLabel)(text)
    label.setWordWrap(True)
    colors = palette()
    color = colors.text_faint if dim else colors.text
    label.setStyleSheet(
        f"QLabel {{ color: {color}; background: transparent; border: none; font-size: 12px; }}"
    )
    return label


__all__ = ["PluginSettingsPage", "build_plugin_page", "message_page"]
