
from __future__ import annotations

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import QBrush, QColor, QIcon, QPainter, QPalette, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QTabWidget,
    QTableWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..base import CombinedMeta, SwitchWidgetABS
from .theme import (
    ACCENT,
    ACCENT_DEEP,
    ACCENT_SOFT,
    BG,
    BORDER,
    BORDER_STRONG,
    PRIMARY,
    PRIMARY_DEEP,
    PRIMARY_SOFT,
    RADIUS,
    RADIUS_SMALL,
    SURFACE,
    SURFACE_SOFT,
    SURFACE_SUNK,
    TEXT,
    TEXT_DIM,
    TEXT_FAINT,
    TEXT_ON_PRIMARY,
    base_sheet,
    font_css,
)


class BreezeLabel(QLabel):
    """正文标签：默认左对齐、次级色可切。"""

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.setStyleSheet(f"QLabel {{ background: transparent; border: none; color: {TEXT}; {font_css(14)} }}")

    def set_center(self):
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def set_dim(self, dim: bool = True):
        """次要说明文字（灰一点、小一点）。"""
        color = TEXT_DIM if dim else TEXT
        size = 13 if dim else 14
        self.setStyleSheet(f"QLabel {{ background: transparent; border: none; color: {color}; {font_css(size)} }}")


class BreezeButton(QPushButton):
    """圆角按钮：默认白底描边，`setActive` 变主色实心。"""

    def __init__(self, text="", icon: QIcon = None, parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(34)
        self.setIconSize(QSize(18, 18))
        self.setIcon(icon if icon else QIcon())

        self.normal_style = f"""
            QPushButton {{
                background: {SURFACE};
                color: {TEXT};
                border: 1px solid {BORDER_STRONG};
                border-radius: {RADIUS_SMALL}px;
                padding: 6px 14px;
                {font_css(14)}
            }}
            QPushButton:hover {{
                background: {ACCENT_SOFT};
                border: 1px solid {ACCENT};
                color: {ACCENT_DEEP};
            }}
            QPushButton:pressed {{
                background: {SURFACE_SOFT};
            }}
            QPushButton:disabled {{
                color: {TEXT_FAINT};
                border: 1px solid {BORDER};
                background: {SURFACE_SOFT};
            }}
        """
        self.active_style = f"""
            QPushButton {{
                background: {PRIMARY};
                color: {TEXT_ON_PRIMARY};
                border: 1px solid {PRIMARY};
                border-radius: {RADIUS_SMALL}px;
                padding: 6px 14px;
                {font_css(14, weight=600)}
            }}
            QPushButton:hover {{
                background: {PRIMARY_DEEP};
                border: 1px solid {PRIMARY_DEEP};
            }}
        """
        self.setStyleSheet(self.normal_style)

    def set_border(self):
        """主行动按钮：实心主色（"保存""发送"这类）。"""
        self.setStyleSheet(self.active_style)

    def set_ghost(self):
        """无边框的轻量按钮（图标、小动作）。"""
        self.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {TEXT_DIM};
                border: none;
                border-radius: {RADIUS_SMALL}px;
                padding: 4px 8px;
                {font_css(13)}
            }}
            QPushButton:hover {{
                background: {SURFACE_SOFT};
                color: {ACCENT_DEEP};
            }}
        """)

    def setActive(self, active: bool):
        self.setStyleSheet(self.active_style if active else self.normal_style)


class BreezeLineEdit(QLineEdit):
    """单行输入：浅底、无重描边，聚焦时主色描边。

    第一个参数既能当占位符（字符串）也能当父窗口（QWidget）：
    `BreezeLineEdit("提示", parent)` 和 `BreezeLineEdit(parent)` 都得能用——
    以前后者会把 QWidget 当成"不是字符串"直接丢掉，控件变成没有父级的小窗口。
    """

    def __init__(self, placeholder_text: str | None = None, parent=None):
        if isinstance(placeholder_text, QWidget):
            parent = parent if parent is not None else placeholder_text
            placeholder_text = None
        super().__init__(parent)
        if isinstance(placeholder_text, str):
            self.setPlaceholderText(placeholder_text)
        self.setMinimumHeight(32)

        # 占位符颜色得用 QPalette：Qt6 的样式表没有 `::placeholder` 这条规则，
        # 写进 QSS 不生效，浅色底上占位文字会淡到看不见
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(TEXT_FAINT))
        self.setPalette(palette)

        self.setStyleSheet(f"""
            QLineEdit {{
                background: {SURFACE};
                color: {TEXT};
                border: 1px solid {BORDER_STRONG};
                border-radius: {RADIUS_SMALL}px;
                padding: 4px 10px;
                selection-background-color: {PRIMARY_SOFT};
                selection-color: {TEXT};
                {font_css(14)}
            }}
            QLineEdit:hover {{
                border: 1px solid {ACCENT};
            }}
            QLineEdit:focus {{
                border: 1px solid {PRIMARY};
                background: {SURFACE};
            }}
        """)


class BreezeTextEdit(QTextEdit):
    """多行输入（第一个参数同样兼容占位符与父窗口，见 `BreezeLineEdit`）。"""

    def __init__(self, placeholder_text: str | None = None, parent=None):
        if isinstance(placeholder_text, QWidget):
            parent = parent if parent is not None else placeholder_text
            placeholder_text = None
        super().__init__(parent)
        if isinstance(placeholder_text, str):
            self.setPlaceholderText(placeholder_text)

        palette = self.palette()
        palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(TEXT_FAINT))
        self.setPalette(palette)
        self.setStyleSheet(f"""
            QTextEdit {{
                background: {SURFACE};
                color: {TEXT};
                border: 1px solid {BORDER_STRONG};
                border-radius: {RADIUS}px;
                padding: 8px 10px;
                selection-background-color: {PRIMARY_SOFT};
                selection-color: {TEXT};
                {font_css(14)}
            }}
            QTextEdit:hover {{
                border: 1px solid {ACCENT};
            }}
            QTextEdit:focus {{
                border: 1px solid {PRIMARY};
            }}
        """)


class BreezeComboBox(QComboBox):
    """下拉框：白底描边，展开的列表也走同一套配色。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(32)
        self.setStyleSheet(f"""
            QComboBox {{
                background: {SURFACE};
                color: {TEXT};
                border: 1px solid {BORDER_STRONG};
                border-radius: {RADIUS_SMALL}px;
                padding: 4px 10px;
                {font_css(14)}
            }}
            QComboBox:hover {{
                border: 1px solid {ACCENT};
            }}
            QComboBox:on {{
                border: 1px solid {PRIMARY};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 22px;
            }}
            QComboBox::down-arrow {{
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid {TEXT_DIM};
                width: 0px;
                height: 0px;
                margin-right: 6px;
            }}
            QComboBox QAbstractItemView {{
                background: {SURFACE};
                color: {TEXT};
                border: 1px solid {BORDER_STRONG};
                border-radius: {RADIUS_SMALL}px;
                padding: 4px;
                outline: none;
                selection-background-color: {PRIMARY_SOFT};
                selection-color: {PRIMARY_DEEP};
            }}
        """)


class BreezeSlider(QSlider):
    """滑块：浅槽 + 主色圆柄。"""

    def __init__(self, orientation=Qt.Orientation.Horizontal, parent=None):
        super().__init__(orientation, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(24)
        self._restyle()

    def _restyle(self):
        self.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                height: 6px;
                background: {SURFACE_SUNK};
                border-radius: 3px;
            }}
            QSlider::sub-page:horizontal {{
                background: {PRIMARY};
                border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                background: {SURFACE};
                border: 2px solid {PRIMARY};
                width: 14px;
                height: 14px;
                margin: -6px 0;
                border-radius: 9px;
            }}
            QSlider::handle:horizontal:hover {{
                border: 2px solid {PRIMARY_DEEP};
                background: {PRIMARY_SOFT};
            }}
            QSlider::groove:vertical {{
                width: 6px;
                background: {SURFACE_SUNK};
                border-radius: 3px;
            }}
            QSlider::handle:vertical {{
                background: {SURFACE};
                border: 2px solid {PRIMARY};
                width: 14px;
                height: 14px;
                margin: 0 -6px;
                border-radius: 9px;
            }}
        """)


class BreezeSwitch(QWidget, SwitchWidgetABS, metaclass=CombinedMeta):
    """胶囊开关：关是灰槽，开是主色槽，圆柄滑动过去。"""

    stateChanged = Signal(bool)

    WIDTH = 52
    HEIGHT = 28
    PADDING = 3

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(self.WIDTH, self.HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._checked = False
        self._offset = float(self.PADDING)

        self.animation = QPropertyAnimation(self, b"offset")
        self.animation.setDuration(160)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    def getOffset(self):
        return self._offset

    def setOffset(self, value):
        self._offset = value
        self.update()

    offset = Property(float, getOffset, setOffset)

    def sizeHint(self):
        return QSize(self.WIDTH, self.HEIGHT)

    def setChecked(self, checked):
        checked = bool(checked)
        changed = checked != self._checked
        self._checked = checked

        self.animation.stop()
        self.animation.setStartValue(self._offset)
        self.animation.setEndValue(float(self.WIDTH - self.HEIGHT + self.PADDING if checked else self.PADDING))
        self.animation.start()

        if changed:
            self.stateChanged.emit(checked)

    def isChecked(self):
        return self._checked

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setChecked(not self._checked)
        super().mousePressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        radius = self.HEIGHT / 2
        track = QRectF(0, 0, self.WIDTH, self.HEIGHT)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(PRIMARY if self._checked else SURFACE_SUNK)))
        painter.drawRoundedRect(track, radius, radius)

        if self._checked:
            painter.setPen(QPen(QColor(PRIMARY_DEEP), 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(track.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)

        knob = self.HEIGHT - self.PADDING * 2
        painter.setPen(QPen(QColor(BORDER_STRONG if not self._checked else PRIMARY_DEEP), 1))
        painter.setBrush(QBrush(QColor(SURFACE)))
        painter.drawEllipse(QRectF(self._offset, self.PADDING, knob, knob))
        painter.end()


class BreezeCard(QFrame):
    """卡片：标题 + 说明 + 控件，白底圆角描边（设置页的基本单元）。"""

    def __init__(self, title: str, widget: QWidget, description: str = "", parent=None, stacked: bool = False):
        super().__init__(parent)
        self.setObjectName("BreezeCard")

        self.title_label = QLabel(title)
        self.title_label.setStyleSheet(f"QLabel {{ background: transparent; color: {TEXT}; {font_css(14, weight=600)} }}")

        self.description_label = QLabel(description)
        self.description_label.setWordWrap(True)
        self.description_label.setStyleSheet(
            f"QLabel {{ background: transparent; color: {TEXT_DIM}; {font_css(12)} }}"
        )

        if stacked:
            # 上下排：控件独占一行（下拉框、表格这类要宽度的）
            layout = QVBoxLayout(self)
            layout.setContentsMargins(14, 10, 14, 12)
            layout.setSpacing(6)
            layout.addWidget(self.title_label)
            if description:
                layout.addWidget(self.description_label)
            layout.addWidget(widget)
            # 卡片自己按内容长高：只给 layout 加不行，里面的控件会被压扁/重叠
            self.setMinimumHeight(layout.sizeHint().height())
        else:
            layout = QHBoxLayout(self)
            layout.setContentsMargins(14, 10, 14, 10)
            layout.setSpacing(14)

            text_layout = QVBoxLayout()
            text_layout.setContentsMargins(0, 0, 0, 0)
            text_layout.setSpacing(1)
            text_layout.addWidget(self.title_label)
            if description:
                text_layout.addWidget(self.description_label)

            layout.addLayout(text_layout, 1)
            # 别把控件压扁：按它自己的建议高度来。用 max() 而不是直接 setMinimumHeight，
            # 免得把 BreezeSwitch 这种固定 28px 的控件顶到 30px（Qt 会静默夹掉，容易看出偏差）
            hint = widget.sizeHint().height()
            if hint > 0:
                widget.setMinimumHeight(hint)
            layout.addWidget(widget, 0, Qt.AlignmentFlag.AlignVCenter)

        self.setStyleSheet(f"""
            QFrame#BreezeCard {{
                background: {SURFACE};
                border: 1px solid {BORDER};
                border-radius: {RADIUS}px;
            }}
            QFrame#BreezeCard:hover {{
                border: 1px solid {BORDER_STRONG};
            }}
        """)

    def title(self):
        return self.title_label.text()

    def set_title(self, title):
        self.title_label.setText(title)


class BreezeTable(QTableWidget):
    """表格：白底、浅表头、选中整行薄荷绿。"""

    def __init__(self, rows=0, columns=0, parent=None):
        super().__init__(rows, columns, parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(34)
        self.horizontalHeader().setHighlightSections(False)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.horizontalHeader().setStretchLastSection(True)
        self.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setShowGrid(False)
        self.setAlternatingRowColors(True)
        self.setTextElideMode(Qt.TextElideMode.ElideRight)

        self.setStyleSheet(f"""
            QTableWidget {{
                background: {SURFACE};
                alternate-background-color: {BG};
                color: {TEXT};
                border: 1px solid {BORDER};
                border-radius: {RADIUS}px;
                outline: none;
                gridline-color: transparent;
                selection-background-color: {PRIMARY_SOFT};
                selection-color: {PRIMARY_DEEP};
                {font_css(13)}
            }}
            QTableWidget::item {{
                padding: 5px 8px;
                border: none;
            }}
            QTableWidget::item:hover {{
                background: {ACCENT_SOFT};
            }}
            QTableWidget::item:selected {{
                background: {PRIMARY_SOFT};
                color: {PRIMARY_DEEP};
            }}
            QHeaderView {{
                background: transparent;
            }}
            QHeaderView::section {{
                background: {SURFACE_SOFT};
                color: {TEXT_DIM};
                padding: 6px 8px;
                border: none;
                border-bottom: 1px solid {BORDER};
                {font_css(13, weight=600)}
            }}
            QHeaderView::section:hover {{
                background: {ACCENT_SOFT};
                color: {ACCENT_DEEP};
            }}
            QTableWidget QLineEdit {{
                background: {SURFACE};
                color: {TEXT};
                border: 1px solid {PRIMARY};
                border-radius: {RADIUS_SMALL}px;
                padding: 2px 6px;
                {font_css(13)}
            }}
        """)

    def setHorizontalHeaderLabels(self, headers):
        self.setColumnCount(len(headers))
        super().setHorizontalHeaderLabels(headers)

    def set_header_stretch(self):
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

    def set_header_resize(self):
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)


class BreezeTabWidget(QTabWidget):
    """页签：底部一条主色指示线的"轻"页签。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QTabWidget {{
                background: transparent;
                border: none;
            }}
            QTabWidget::pane {{
                background: {SURFACE};
                border: 1px solid {BORDER};
                border-radius: {RADIUS}px;
                top: -1px;
                padding: 6px;
            }}
            QTabBar {{
                background: transparent;
                qproperty-drawBase: 0;
            }}
            QTabBar::tab {{
                background: transparent;
                color: {TEXT_DIM};
                min-height: 32px;
                padding: 0 16px;
                margin-right: 4px;
                border: none;
                border-bottom: 2px solid transparent;
                {font_css(14)}
            }}
            QTabBar::tab:hover {{
                color: {ACCENT_DEEP};
                border-bottom: 2px solid {ACCENT_SOFT};
            }}
            QTabBar::tab:selected {{
                color: {PRIMARY_DEEP};
                border-bottom: 2px solid {PRIMARY};
                {font_css(14, weight=600)}
            }}
            QTabWidget QWidget {{
                background: transparent;
            }}
        """)


class BreezeScrollArea(QScrollArea):
    """滚动区：透明底、无边框（滚动条样式在 base_sheet 里）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self.setStyleSheet("QScrollArea { background: transparent; border: none; }")


__all__ = [
    "base_sheet",
    "BreezeButton",
    "BreezeCard",
    "BreezeComboBox",
    "BreezeLabel",
    "BreezeLineEdit",
    "BreezeScrollArea",
    "BreezeSlider",
    "BreezeSwitch",
    "BreezeTable",
    "BreezeTabWidget",
    "BreezeTextEdit",
]
