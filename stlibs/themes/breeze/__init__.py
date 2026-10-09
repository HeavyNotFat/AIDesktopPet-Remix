
from ..base import (
    AnimationABS,
    CombinedMeta,
    IconListABS,
    MainWindowABS,
    MenuWidgetABS,
    ModelChatABS,
    SwitchWidgetABS,
    ThemePalette,
)
from ... import Config, SharingData, derfer
from ...ai import cloud, local
from . import animation
from . import general
from . import llm
from . import plugins
from . import settings
from . import tts
from .chat import (
    BreezeAttachmentChip,
    BreezeBubbleAction,
    BreezeChatBubble,
    BreezeChatWidget,
    _ChatInputEdit,
)
from .chrome import (
    MAPPING_ANIMATION,
    MAPPING_SPECTIAL_ANIMATION,
    _Category,
    _CodeRain,
    _NavButton,
    _SoftBackdrop,
    _TitleBar,
    prompts,
    rounded_pixmap,
    soft_shadow,
)
from .feedback import BreezeNotify
from .menu import MENU_ICON, Action, BreezeMenu, draw_badge, menu_icon_pixmap
from .model_chat import ModelChat, cache_llm_class
from .primitives import (
    BreezeButton,
    BreezeCard,
    BreezeComboBox,
    BreezeLabel,
    BreezeLineEdit,
    BreezeScrollArea,
    BreezeSlider,
    BreezeSwitch,
    BreezeTable,
    BreezeTabWidget,
    BreezeTextEdit,
    base_sheet,
)
from .window import BreezeWindow, IconList, PageHint, PageTitle
from .theme import (
    ACCENT,
    ACCENT_SOFT,
    BG,
    BORDER,
    BORDER_STRONG,
    ERROR,
    INFO,
    PRIMARY,
    PRIMARY_DEEP,
    PRIMARY_SOFT,
    RADIUS,
    RADIUS_SMALL,
    SUCCESS,
    SURFACE,
    SURFACE_SOFT,
    SURFACE_SUNK,
    TEXT,
    TEXT_DIM,
    TEXT_FAINT,
    WARNING,
)

# 窗口标题里显示的中文名（见 stlibs/graphics/theme_label.py）
THEME_LABEL = "轻风"

# 给插件/探针用的语义配色（见 stlibs/graphics/palette.py）
PALETTE = ThemePalette(
    bg=BG,
    surface=SURFACE,
    surface_soft=SURFACE_SOFT,
    surface_sunk=SURFACE_SUNK,
    primary=PRIMARY,
    primary_dim=PRIMARY_DEEP,
    accent=ACCENT,
    text=TEXT,
    text_dim=TEXT_DIM,
    text_faint=TEXT_FAINT,
    border=BORDER,
    border_strong=BORDER_STRONG,
    radius=RADIUS,
    radius_small=RADIUS_SMALL,
    hover=ACCENT_SOFT,
    track=SURFACE_SUNK,
    success=SUCCESS,
    warning=WARNING,
    error=ERROR,
    info=INFO,
    tints={
        "level": (PRIMARY, PRIMARY_SOFT),
        "favor": ("#E88AA8", "#FDEEF2"),
        "hungry": (WARNING, "#FDF4E4"),
    },
)

# 契约映射别名（名字见 stlibs/__init__.py::_ThemeTypingProtocol）
Window = BreezeWindow
Menu = BreezeMenu
Notify = BreezeNotify
TextEdit = BreezeTextEdit
LineEdit = BreezeLineEdit
Button = BreezeButton
Label = BreezeLabel
Slider = BreezeSlider
Switch = BreezeSwitch
ComboBox = BreezeComboBox
CardWidget = BreezeCard
ScrollArea = BreezeScrollArea
ChatBubble = BreezeChatBubble
ChatWidget = BreezeChatWidget

# 契约要的是"能直接用的实例"，不是类
IconList = IconList()

__all__ = [
    "Action",
    "AnimationABS",
    "BreezeAttachmentChip",
    "BreezeBubbleAction",
    "BreezeButton",
    "BreezeCard",
    "BreezeChatBubble",
    "BreezeChatWidget",
    "BreezeComboBox",
    "BreezeLabel",
    "BreezeLineEdit",
    "BreezeMenu",
    "BreezeNotify",
    "BreezeScrollArea",
    "BreezeSlider",
    "BreezeSwitch",
    "BreezeTable",
    "BreezeTabWidget",
    "BreezeTextEdit",
    "BreezeWindow",
    "Button",
    "CardWidget",
    "ChatBubble",
    "ChatWidget",
    "CombinedMeta",
    "ComboBox",
    "Config",
    "IconList",
    "IconListABS",
    "Label",
    "LineEdit",
    "MAPPING_ANIMATION",
    "MAPPING_SPECTIAL_ANIMATION",
    "MENU_ICON",
    "MainWindowABS",
    "Menu",
    "MenuWidgetABS",
    "ModelChat",
    "ModelChatABS",
    "Notify",
    "PageHint",
    "PageTitle",
    "ScrollArea",
    "SharingData",
    "Slider",
    "Switch",
    "SwitchWidgetABS",
    "TextEdit",
    "Window",
    "animation",
    "base_sheet",
    "cache_llm_class",
    "cloud",
    "derfer",
    "draw_badge",
    "general",
    "llm",
    "local",
    "menu_icon_pixmap",
    "plugins",
    "prompts",
    "rounded_pixmap",
    "settings",
    "soft_shadow",
    "tts",
]
