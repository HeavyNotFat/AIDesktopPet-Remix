import base64
import json
import math
import random

from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QStackedWidget,
    QTabWidget,
    QTableWidget,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import (
    Property,
    QByteArray,
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QRectF,
    QSize,
    QTimer,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QCursor,
    QFont,
    QFontDatabase,
    QFontMetrics,
    QIcon,
    QImage,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QShortcut,
)

from . import animation
from . import general
from . import llm
from . import plugins
from . import settings
from . import tts
from ... import Config, SharingData, derfer
from ...ai import cloud, local
from ..base import (
    CombinedMeta,
    IconListABS,
    MainWindowABS,
    MenuWidgetABS,
    ModelChatABS,
    SwitchWidgetABS,
)
from .chat import HackerAttachmentChip, HackerBubbleAction, HackerChatBubble, HackerChatWidget, _ChatInputEdit
from .chrome import (
    MAPPING_ANIMATION,
    MAPPING_SPECTIAL_ANIMATION,
    _CodeRain,
    _HackerCategory,
    _HackerNavButton,
    _HackerTitleBar,
    prompts,
)
from .feedback import HackerNotify
from .menu import MENU_ICON, Action, HackerMenu, menu_icon_pixmap
from .model_chat import ModelChat, cache_llm_class
from .primitives import (
    HackerButton,
    HackerCard,
    HackerComboBox,
    HackerLabel,
    HackerLineEdit,
    HackerScrollArea,
    HackerSlider,
    HackerSwitch,
    HackerTable,
    HackerTabWidget,
    HackerTextEdit,
)
from .window import HackerWindow, IconList

# 契约映射别名（名字见 stlibs/__init__.py::_ThemeTypingProtocol）
Window = HackerWindow
Menu = HackerMenu
Notify = HackerNotify
TextEdit = HackerTextEdit
LineEdit = HackerLineEdit
Button = HackerButton
Label = HackerLabel
Slider = HackerSlider
ComboBox = HackerComboBox
CardWidget = HackerCard
ScrollArea = HackerScrollArea
ChatBubble = HackerChatBubble
ChatWidget = HackerChatWidget

# 契约要的是"能直接用的实例"，不是类
IconList = IconList()
