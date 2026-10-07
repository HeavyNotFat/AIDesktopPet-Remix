"""hacker 主题（默认主题）的契约门面。

这里只做三件事：把实现模块里的控件重新导出、给契约映射起别名、暴露子模块。
真正的实现按"干什么"分在下面这些文件里，改哪块去翻哪块：

| 文件               | 内容                                                        |
|:-----------------|:----------------------------------------------------------|
| `primitives.py`  | 基础控件：`HackerLabel` / `HackerButton` / `HackerLineEdit` / `HackerTextEdit` / |
|                  | `HackerComboBox` / `HackerSlider` / `HackerSwitch` / `HackerCard` / `HackerTable` / |
|                  | `HackerTabWidget` / `HackerScrollArea`                      |
| `menu.py`        | 自绘右键菜单 `HackerMenu`（一层平铺、无子菜单）+ `Action` + `menu_icon_pixmap` |
| `chrome.py`      | 主窗口零件：标题栏、`_CodeRain` 代码雨、侧栏分类与导航按钮 + 动画名映射表 |
| `feedback.py`    | 操作反馈条 `HackerNotify`                                    |
| `chat.py`        | 聊天区：`HackerChatBubble` / `HackerChatWidget` / 附件 chip / 输入框 |
| `window.py`      | 主窗口 `HackerWindow` + 菜单图标集 `IconList`                 |
| `model_chat.py`  | 单模型聊天页 `ModelChat` + LLM 实例缓存 `cache_llm_class`      |
| `general.py` / `llm.py` / `tts.py` / `settings.py` / `animation.py` / `plugins.py` | 设置页各页签 |

**契约映射三处必须同步**：`stlibs/__init__.py::_ThemeTypingProtocol`（类型）、
`stlibs/themes/base.py`（ABC）、`tools/ci/contract.py`（CI 侧），外加本文件尾部的别名。
新增控件时不要塞回这里，加进对应模块再从下面 import。
"""

# 下面这一大段 Qt / 全局对象 import 是**故意留着**的：拆分之前全都写在
# 本文件里，主题包外可能已经有人 `from stlibs.themes.hacker import QLabel`
# 这么用（插件、调试脚本）。真正的实现已经搬进各子模块，这些名字只是一层
# 兼容垫片，别照抄到新模块里去。（ruff 的 F401 在本文件已关）
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
