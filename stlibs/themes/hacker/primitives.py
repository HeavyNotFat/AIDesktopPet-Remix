
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
from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRectF, QSize, Qt, Property, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QIcon,
    QPainter,
)

from ..base import CombinedMeta, SwitchWidgetABS


class HackerLabel(QLabel):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft)
        font_id = QFontDatabase.addApplicationFont("./resources/fonts/jetbrains.ttf")
        if font_id != -1:
            family = QFontDatabase.applicationFontFamilies(font_id)[0]
            self.setFont(QFont(family, 16))
        else:
            self.setFont(QFont("Consolas", 16))

        self.setStyleSheet("""
            QLabel {
                background: rgba(0,0,0,160);
                color: #00FF00;
                border: none;
                border-radius: 6px;
                min-height: 36px;
            }
        """)

    def set_center(self):
        self.setAlignment(Qt.AlignCenter)


class HackerComboBox(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        font_id = QFontDatabase.addApplicationFont(
            "./resources/fonts/jetbrains.ttf"
        )
        if font_id != -1:
            family = QFontDatabase.applicationFontFamilies(font_id)[0]
            self.setFont(QFont(family, 14))
        else:
            self.setFont(QFont("Consolas", 14))
        self.setFixedHeight(30)
        self.setStyleSheet("""
            QComboBox {
                background: rgba(0, 0, 0, 160);
                color: #00FF00;

                border: 1px solid rgba(0, 255, 0, 100);
                border-radius: 6px;

                min-height: 30px;
                max-height: 30px;

                padding: 0 8px;
            }

            QComboBox:hover {
                border: 1px solid #00FF00;
                background: rgba(0, 255, 0, 20);
            }

            QComboBox:focus {
                border: 1px solid #00FF00;
                background: rgba(0, 0, 0, 180);
            }

            /* 下拉按钮 */
            QComboBox::drop-down {
                width: 28px;

                border: none;
                border-left: 1px solid rgba(0, 255, 0, 80);

                background: rgba(0, 0, 0, 100);
            }

            QComboBox::drop-down:hover {
                background: rgba(0, 255, 0, 30);
            }

            /* 下拉列表 */
            QComboBox QAbstractItemView {
                background: rgba(0, 0, 0, 230);
                color: #00FF00;

                border: 1px solid #00FF00;
                border-radius: 4px;

                padding: 2px;
                outline: none;
            }

            /* 下拉列表项目 */
            QComboBox QAbstractItemView::item {
                min-height: 26px;
                padding: 2px 8px;

                border-radius: 3px;
            }

            QComboBox QAbstractItemView::item:hover {
                background: rgba(0, 255, 0, 40);
                color: #66FF66;
            }

            QComboBox QAbstractItemView::item:selected {
                background: rgba(0, 255, 0, 60);
                color: #FFFFFF;
            }
        """)


class HackerSlider(QSlider):
    def __init__(
        self,
        orientation=Qt.Orientation.Horizontal,
        parent=None
    ):
        super().__init__(orientation, parent)

        self.setMinimum(0)
        self.setMaximum(100)
        self.setValue(50)

        self.setStyleSheet("""
            QSlider {
                background: transparent;
                min-height: 24px;
            }
            QSlider::groove:horizontal {
                height: 6px;
                background: rgba(0, 0, 0, 160);
                border: 1px solid rgba(0, 255, 0, 80);
                border-radius: 3px;
            }

            QSlider::sub-page:horizontal {
                background: #00FF00;
                border-radius: 3px;
            }

            QSlider::add-page:horizontal {
                background: rgba(0, 0, 0, 160);
                border-radius: 3px;
            }

            QSlider::handle:horizontal {
                width: 14px;
                height: 14px;
                margin: -5px 0;
                background: #00FF00;
                border: 2px solid #001A00;
                border-radius: 7px;
            }

            QSlider::handle:horizontal:hover {
                background: #66FF66;
                border: 2px solid #00FF00;
            }

            QSlider::handle:horizontal:pressed {
                background: #FFFFFF;
                border: 2px solid #00FF00;
            }

            QSlider::groove:vertical {
                width: 6px;
                background: rgba(0, 0, 0, 160);
                border: 1px solid rgba(0, 255, 0, 80);
                border-radius: 3px;
            }

            QSlider::sub-page:vertical {
                background: #00FF00;
                border-radius: 3px;
            }

            QSlider::add-page:vertical {
                background: rgba(0, 0, 0, 160);
                border-radius: 3px;
            }

            QSlider::handle:vertical {
                width: 14px;
                height: 14px;
                margin: 0 -5px;
                background: #00FF00;
                border: 2px solid #001A00;
                border-radius: 7px;
            }

            QSlider::handle:vertical:hover {
                background: #66FF66;
                border: 2px solid #00FF00;
            }

            QSlider::handle:vertical:pressed {
                background: #FFFFFF;
                border: 2px solid #00FF00;
            }
        """)


class HackerButton(QPushButton):
    def __init__(self, text="", icon: QIcon = None, parent=None):
        super().__init__(text, parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setIcon(icon if icon else QIcon())
        self.setIconSize(QSize(20, 20))

        self.normal_style = """
            QPushButton {
                background: rgba(0,0,0,150);
                color: #00FF00;
                padding: 0 12px;
                border: none;
                border-radius: 6px;
                min-height: 36px;
                text-align: left;
            }
            QPushButton:hover {
                background: rgba(0,255,0,40);
                color: #00FF88;
            }
        """

        self.active_style = """
            QPushButton {
                background: rgba(0,255,0,60);
                color: #00FF88;
                padding: 0 12px;
                border: none;
                border-radius: 6px;
                min-height: 36px;
                text-align: left;
            }
        """

        self.setStyleSheet(self.normal_style)

    def set_border(self):
        self.setStyleSheet("""
            QPushButton {
                background: rgba(0,0,0,150);
                color: #00FF00;
                padding: 0 12px;
                border: 1px solid #00FF00;
                border-radius: 6px;
                min-height: 36px;
                text-align: left;
            }
            QPushButton:hover {
                background: rgba(0,255,0,40);
            }
            """
        )

    def setActive(self, active: bool):
        self.setStyleSheet(self.active_style if active else self.normal_style)


class HackerLineEdit(QLineEdit):
    def __init__(self, placeholder_text: str | None = None, parent=None):
        super().__init__(parent if isinstance(placeholder_text, str) else placeholder_text)
        if isinstance(placeholder_text, str): self.setPlaceholderText(placeholder_text)
        self.setStyleSheet("""
        QLineEdit {
            background: rgba(0,0,0,150);
            color: rgb(255, 80, 80);
            padding: 0 12px;
            border: 1px solid #00FF00;
            border-radius: 6px;
            min-height: 30px;
        }
        QLineEdit::focus {
            border-bottom: 1px solid #00ffff;
        }
        """)


class HackerTextEdit(QTextEdit):
    def __init__(self, placeholder_text: str | None = None, parent=None):
        super().__init__(parent if isinstance(placeholder_text, str) else placeholder_text)
        if isinstance(placeholder_text, str): self.setPlaceholderText(placeholder_text)

        font = QFont("Microsoft YaHei", 12)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)

        self.setStyleSheet("""
        QTextEdit {
            background: rgba(0,0,0,150);
            padding: 10px;
            color: rgb(45, 196, 210);
            border: 1px solid #00FF00;
            border-radius: 6px;
            selection-background-color: rgba(0, 255, 0, 100);
        }
        QTextEdit:focus {
            border: 1px solid #00ffff;
        }
        QTextEdit::selected {
            background-color: rgba(0, 255, 0, 100);
        }
        QTextEdit::scrollbar:vertical {
            width: 8px;
            background-color: rgba(0,0,0,150);
            border: 1px solid #00FF00;
        }
        """)


class HackerSwitch(QWidget, SwitchWidgetABS, metaclass=CombinedMeta):
    stateChanged = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setFixedSize(56, 30)
        self._checked = False
        self._offset = 3.0

        # 滑块滑动动画
        self.animation = QPropertyAnimation(self, b"offset")
        self.animation.setDuration(180)
        self.animation.setEasingCurve(
            QEasingCurve.Type.OutCubic
        )

        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def getOffset(self):
        return self._offset

    def setOffset(self, value):
        self._offset = value
        self.update()

    offset = Property(float, getOffset, setOffset)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setChecked(not self._checked)
            self.stateChanged.emit(self._checked)

        super().mousePressEvent(event)

    def setChecked(self, checked):
        checked = bool(checked)
        changed = checked != self._checked
        self._checked = checked

        start = self._offset
        end = 29.0 if checked else 3.0

        self.animation.stop()
        self.animation.setStartValue(start)
        self.animation.setEndValue(end)
        self.animation.start()

        # 代码里改状态也要通知出去
        if changed:
            self.stateChanged.emit(checked)

    def isChecked(self):
        return self._checked

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self._checked:
            bg_color = QColor(0, 255, 0, 70)
            border_color = QColor("#00FF00")
        else:
            bg_color = QColor(0, 0, 0, 180)
            border_color = QColor(0, 255, 0, 90)

        painter.setBrush(bg_color)
        painter.setPen(border_color)

        rect = QRectF(
            1,
            1,
            self.width() - 2,
            self.height() - 2
        )

        painter.drawRoundedRect(
            rect,
            14,
            14
        )

        knob_size = 24

        knob_y = (self.height() - knob_size) / 2

        if self._checked:
            knob_color = QColor("#00FF88")
        else:
            knob_color = QColor("#00AA00")

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(knob_color)

        painter.drawEllipse(
            QRectF(
                self._offset,
                knob_y,
                knob_size,
                knob_size
            )
        )

        if self._checked:
            glow = QColor(0, 255, 0, 80)

            painter.setPen(glow)
            painter.setBrush(Qt.BrushStyle.NoBrush)

            painter.drawEllipse(
                QRectF(
                    self._offset - 2,
                    knob_y - 2,
                    knob_size + 4,
                    knob_size + 4
                )
            )


class HackerCard(QFrame):
    def __init__(
        self,
        title: str,
        widget: QWidget,
        description: str = "",
        parent=None,
        stacked: bool = False,
    ):
        super().__init__(parent)

        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("""
            QLabel {
                background: transparent;
                color: #00FF00;
                border: none;
            }
        """)

        description_label = QLabel(description)
        description_label.setStyleSheet("""
            QLabel {
                background: transparent;
                color: rgba(0, 255, 0, 150);
                border: none;
            }
        """)

        if stacked:
            # 上下排：控件独占一整行，适合下拉框、表格
            self.setFixedHeight(104)
            layout = QVBoxLayout(self)
            layout.setContentsMargins(14, 10, 14, 12)
            layout.setSpacing(8)

            head = QHBoxLayout()
            head.setContentsMargins(0, 0, 0, 0)
            head.setSpacing(12)
            head.addWidget(self.title_label)
            head.addWidget(description_label)
            head.addStretch(1)
            layout.addLayout(head)

            layout.addWidget(widget)
        else:
            self.setFixedHeight(62)
            layout = QHBoxLayout(self)
            layout.setContentsMargins(14, 8, 14, 8)
            layout.setSpacing(20)

            text_layout = QVBoxLayout()
            text_layout.setContentsMargins(0, 0, 0, 0)
            text_layout.setSpacing(0)
            text_layout.addWidget(self.title_label)
            text_layout.addWidget(description_label)

            layout.addLayout(text_layout, 1)
            # 别把控件压扁：按它自己的建议高度来
            widget.setFixedHeight(max(30, widget.sizeHint().height()))
            layout.addWidget(widget, 0, Qt.AlignmentFlag.AlignVCenter)

        self.setStyleSheet("""
            HackerCard {
                background: rgba(0, 0, 0, 150);

                border: 1px solid rgba(0, 255, 0, 70);
                border-radius: 6px;
            }

            HackerCard:hover {
                background: rgba(0, 255, 0, 15);
                border: 1px solid rgba(0, 255, 0, 140);
            }
        """)

    def title(self):
        return self.title_label.text()

    def set_title(self, title):
        self.title_label.setText(title)


class HackerTable(QTableWidget):
    def __init__(
        self,
        rows=0,
        columns=0,
        parent=None
    ):
        super().__init__(rows, columns, parent)

        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding
        )
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setVisible(True)
        self.verticalHeader().setDefaultSectionSize(36)
        self.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setShowGrid(True)
        self.horizontalHeader().setStretchLastSection(True)
        self.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setTextElideMode(Qt.TextElideMode.ElideRight)

        font = QFont("Consolas")
        font.setPixelSize(13)
        self.setFont(font)

        self.setStyleSheet("""
        QTableWidget {
            background: rgba(0, 0, 0, 165);
            color: #006CBF;
            border: 1px solid rgba(0, 255, 0, 90);
            border-radius: 6px;
            gridline-color: rgba(0, 255, 0, 35);
            selection-background-color: rgba(0, 255, 0, 65);
            selection-color: #FF0000;
            outline: none;
            alternate-background-color: rgba(0, 255, 0, 8);
        }
        QTableWidget::item {
            padding: 6px 10px;

            border: none;
            border-bottom: 1px solid rgba(0, 255, 0, 20);
        }
        QTableWidget::item:hover {
            background: rgba(0, 255, 0, 30);
            color: #66FF66;
        }
        QTableWidget::item:selected {
            background: rgba(0, 255, 0, 65);
            color: #FF0000;
        }

        QHeaderView {
            background: transparent;
        }
        QHeaderView::section {
            background: rgba(0, 0, 0, 220);
            color: #00FF00;
            padding: 8px 10px;
            border: none;
            border-right: 1px solid rgba(0, 255, 0, 45);
            border-bottom: 1px solid rgba(0, 255, 0, 90);
            font-weight: bold;
        }
        QHeaderView::section:hover {
            background: rgba(0, 255, 0, 30);
            color: #66FF66;
        }
        
        QHeaderView::section:vertical {
            background: rgba(0, 0, 0, 180);
            color: #00FF00;
            border: none;
            border-bottom: 1px solid rgba(0, 255, 0, 25);
        }

        QScrollBar:vertical {
            background: rgba(0, 0, 0, 100);
            width: 10px;
            margin: 2px 2px 2px 2px;
            border: none;
        }
        QScrollBar::handle:vertical {
            background: rgba(0, 255, 0, 130);
            min-height: 30px;
            border-radius: 5px;
        }
        QScrollBar::handle:vertical:hover {
            background: #00FF00;
        }
        QScrollBar::add-line:vertical,
        QScrollBar::sub-line:vertical {
            height: 0px;
            background: none;
            border: none;
        }
        QScrollBar::add-page:vertical,
        QScrollBar::sub-page:vertical {
            background: transparent;
        }
        
        QScrollBar:horizontal {
            background: rgba(0, 0, 0, 100);
            height: 10px;
            margin: 2px 2px 2px 2px;
            border: none;
        }
        QScrollBar::handle:horizontal {
            background: rgba(0, 255, 0, 130);
            min-width: 30px;
            border-radius: 5px;
        }
        QScrollBar::handle:horizontal:hover {
            background: #00FF00;
        }
        QScrollBar::add-line:horizontal,
        QScrollBar::sub-line:horizontal {
            width: 0px;
            background: none;
            border: none;
        }
        QScrollBar::add-page:horizontal,
        QScrollBar::sub-page:horizontal {
            background: transparent;
        }
        
        QTableWidget QLineEdit {
            background: rgba(0, 0, 0, 220);
            color: #00FF00;
            border: 1px solid #00FF00;
            border-radius: 3px;
            padding: 4px 8px;
            font-family: "Consolas";
            font-size: 13px;
            selection-background-color: rgba(0, 255, 0, 100);
        }
        """)

        self.setAlternatingRowColors(True)

        header = self.horizontalHeader()
        header.setHighlightSections(False)
        # 默认根据内容调整列宽
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)

    def setHorizontalHeaderLabels(self, headers):
        """重新设置表头"""
        self.setColumnCount(len(headers))
        super().setHorizontalHeaderLabels(headers)

    def set_header_stretch(self):
        """让所有列平均拉伸宽度"""
        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

    def set_header_resize(self):
        """允许用户拖动调整列宽（以此为准）"""
        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)


class HackerTabWidget(QTabWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self._setup_font()
        self._setup_style()

    def _setup_font(self):
        font_id = QFontDatabase.addApplicationFont(
            "./resources/fonts/jetbrains.ttf"
        )

        if font_id != -1:
            family = QFontDatabase.applicationFontFamilies(font_id)[0]
            self.setFont(QFont(family, 14))
        else:
            self.setFont(QFont("Consolas", 14))

    def _setup_style(self):
        self.setStyleSheet("""
            QTabWidget {
                background: transparent;
                border: none;
            }

            /* Tab 内容区域 */
            QTabWidget::pane {
                background: rgba(0, 0, 0, 180);

                border: 1px solid #00FF00;
                border-radius: 6px;

                top: -1px;
            }

            QTabBar {
                background: transparent;
            }

            QTabBar::tab {
                background: rgba(0, 0, 0, 150);
                color: #00FF00;

                min-height: 30px;
                max-height: 30px;

                min-width: 90px;

                padding: 0 12px;

                border: 1px solid transparent;
                border-bottom: none;

                border-radius: 6px 6px 0 0;
            }

            /* Hover */
            QTabBar::tab:hover {
                background: rgba(0, 255, 0, 35);
                color: #00FF88;

                border: 1px solid rgba(0, 255, 0, 100);
                border-bottom: none;
            }

            /* 当前选中的 Tab */
            QTabBar::tab:selected {
                background: rgba(0, 255, 0, 60);
                color: #00FF88;

                border: 1px solid #00FF00;
                border-bottom: 2px solid #00FF00;
            }

            /* 未选中的 Tab */
            QTabBar::tab:!selected {
                margin-top: 2px;
            }

            /* Tab 被按下 */
            QTabBar::tab:pressed {
                background: rgba(0, 255, 0, 80);
                color: #FFFFFF;
            }

            QTabWidget QWidget {
                background: transparent;
                color: #00FF00;
            }
        """)


class HackerScrollArea(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.Shape.NoFrame)

        self.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: none;
            }

            QScrollBar:vertical {
                width: 8px;

                background: rgba(0, 0, 0, 120);

                border: none;
                border-radius: 4px;

                margin: 0;
            }

            QScrollBar::handle:vertical {
                background: rgba(0, 255, 0, 100);
                min-height: 30px;
                border-radius: 4px;
            }

            QScrollBar::handle:vertical:hover {
                background: #00FF00;
            }

            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0;
                border: none;
                background: none;
            }

            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {
                background: transparent;
            }

            QScrollBar:horizontal {
                height: 8px;
                background: rgba(0, 0, 0, 120);
                border: none;
                border-radius: 4px;
                margin: 0;
            }

            QScrollBar::handle:horizontal {
                background: rgba(0, 255, 0, 100);
                min-width: 30px;
                border-radius: 4px;
            }

            QScrollBar::handle:horizontal:hover {
                background: #00FF00;
            }

            QScrollBar::add-line:horizontal,
            QScrollBar::sub-line:horizontal {
                width: 0;
                border: none;
                background: none;
            }

            QScrollBar::add-page:horizontal,
            QScrollBar::sub-page:horizontal {
                background: transparent;
            }
        """)
