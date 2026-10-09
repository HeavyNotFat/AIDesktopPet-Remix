
from __future__ import annotations

# 底色
BG = "#F7FAFC"          # 窗口底
SURFACE = "#FFFFFF"     # 卡片 / 面板
SURFACE_SOFT = "#EDF3F8"  # 次级填充（表头、输入框底、悬停）
SURFACE_SUNK = "#E3ECF3"  # 凹陷（滚动槽、分隔带）

# 主色
PRIMARY = "#3FB7A0"        # 薄荷绿：主按钮、选中态
PRIMARY_DEEP = "#2E9A85"   # 按下 / 强调文字
PRIMARY_SOFT = "#E4F5F1"   # 主色浅底（选中行、标签）
ACCENT = "#5AA9E6"         # 雾蓝：次按钮、链接、开关
ACCENT_DEEP = "#3B87C4"
ACCENT_SOFT = "#E7F1FB"

# 文字
TEXT = "#2C3E50"           # 正文
TEXT_DIM = "#6B8299"       # 次要说明
TEXT_FAINT = "#9AAEC0"     # 占位符 / 禁用
TEXT_ON_PRIMARY = "#FFFFFF"

# 线与阴影
BORDER = "#DCE7EF"         # 常规描边
BORDER_STRONG = "#C3D6E3"  # 悬停描边
SHADOW = "rgba(44, 62, 80, 26)"

# 语义色
SUCCESS = "#4CAF83"
WARNING = "#E8A33D"
ERROR = "#E4756F"
INFO = "#5AA9E6"

LEVEL_COLORS = {
    "info": (INFO, "#EAF4FD"),
    "success": (SUCCESS, "#E9F6F0"),
    "warning": (WARNING, "#FDF4E4"),
    "error": (ERROR, "#FCECEB"),
}

# 圆角与间距
RADIUS = 10
RADIUS_SMALL = 6
RADIUS_LARGE = 14
PAD = 12
ROW_HEIGHT = 34

# 字体：优先用系统里的中文字体，都没有就退回 Qt 默认
FONT_FAMILY = '"PingFang SC", "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", sans-serif'
MONO_FAMILY = '"JetBrains Mono", "Cascadia Mono", Consolas, monospace'

# 仓库自带的那份字体（family 名是 HYWenHei，中英文都全）
BUNDLED_FONT = "./resources/fonts/jetbrains.ttf"

_font_installed = False


def install_ui_font() -> str:
    """把自带字体装进 QApplication 并设为默认字体，返回 family 名。"""
    global _font_installed

    from PySide6.QtGui import QFont, QFontDatabase
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        return ""

    if _font_installed:
        return app.property("breeze_font_family") or ""

    family = ""
    font_id = QFontDatabase.addApplicationFont(BUNDLED_FONT)
    if font_id != -1:
        families = QFontDatabase.applicationFontFamilies(font_id)
        if families:
            family = families[0]
            app.setFont(QFont(family, 10))

    app.setProperty("breeze_font_family", family)
    _font_installed = True
    return family


def font_css(size: int = 14, mono: bool = False, weight: int | None = None) -> str:
    """给样式表用的 font 声明片段。"""
    family = MONO_FAMILY if mono else FONT_FAMILY
    weight_css = f"font-weight: {weight};" if weight else ""
    return f"font-family: {family}; font-size: {size}px; {weight_css}"


def base_sheet() -> str:
    """全局样式表：窗口、滚动条、提示气泡这些公共部件。"""
    install_ui_font()
    return f"""
    QWidget {{
        {font_css(14)}
        color: {TEXT};
    }}

    QToolTip {{
        background: {SURFACE};
        color: {TEXT};
        border: 1px solid {BORDER_STRONG};
        border-radius: {RADIUS_SMALL}px;
        padding: 5px 9px;
        {font_css(13)}
    }}

    /* 滚动条：细、圆、不抢眼 */
    QScrollBar:vertical {{
        background: transparent;
        width: 10px;
        margin: 2px;
    }}
    QScrollBar::handle:vertical {{
        background: {BORDER_STRONG};
        min-height: 32px;
        border-radius: 5px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {ACCENT};
    }}
    QScrollBar:horizontal {{
        background: transparent;
        height: 10px;
        margin: 2px;
    }}
    QScrollBar::handle:horizontal {{
        background: {BORDER_STRONG};
        min-width: 32px;
        border-radius: 5px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background: {ACCENT};
    }}
    QScrollBar::add-line, QScrollBar::sub-line {{
        height: 0px;
        width: 0px;
        border: none;
        background: none;
    }}
    QScrollBar::add-page, QScrollBar::sub-page {{
        background: transparent;
    }}

    QScrollArea {{
        background: transparent;
        border: none;
    }}
    """
