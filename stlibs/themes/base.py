from abc import ABCMeta, abstractmethod
from dataclasses import dataclass, field

from PySide6.QtWidgets import QWidget

from ..ai import local, cloud

_QWidgetMeta = type(QWidget)


class CombinedMeta(_QWidgetMeta, ABCMeta):
    pass


@dataclass(frozen=True, slots=True)
class ThemePalette:
    """主题的语义配色，给"不属于某个主题"的界面用（插件面板、探针、SDK 弹窗）。

    主题包可以导出一个 ``PALETTE = ThemePalette(...)``；没导出的主题由
    `stlibs.graphics.palette` 退回默认（深色那套），所以这是个**可选**接口。
    插件只认这些语义名，不认具体色号——这样换主题时插件面板跟着变。
    """

    # 底色：本体 / 卡片 / 次级填充 / 凹陷（滚动槽）
    bg: str = "#16181c"
    surface: str = "rgba(0, 0, 0, 110)"
    surface_soft: str = "rgba(0, 255, 0, 18)"
    surface_sunk: str = "rgba(0, 0, 0, 170)"

    # 主色与点缀
    primary: str = "#00FF00"
    primary_dim: str = "#00FF88"
    accent: str = "#00FF00"

    # 文字
    text: str = "#d8ffd8"
    text_dim: str = "#00FF88"
    text_faint: str = "rgba(0, 255, 0, 150)"

    # 线与圆角
    border: str = "rgba(0, 255, 0, 90)"
    border_strong: str = "#00FF00"
    radius: int = 10
    radius_small: int = 6

    # 悬停 / 选中：卡片悬停底、可点格子的悬停底与描边
    hover: str = "rgba(0, 255, 0, 40)"
    track: str = "rgba(0, 0, 0, 170)"

    # 语义色（提示条、进度条）
    success: str = "#3ddc84"
    warning: str = "#ffcc00"
    error: str = "#ff6b6b"
    info: str = "#00FF00"

    # 进度条等按语义取色：{"level": (亮色, 浅底), ...}
    tints: dict = field(default_factory=dict)

    def tint(self, key: str) -> tuple[str, str]:
        """取一组强调色，没有就用主色。返回 ``(亮色, 浅底)``。"""
        value = self.tints.get(key)
        if isinstance(value, (tuple, list)) and len(value) == 2:
            return str(value[0]), str(value[1])
        return self.primary, self.surface_soft

    def sheet(self, widget: str = "QWidget") -> str:
        """给一整个面板用的基础样式（底 + 字色 + 滚动区）。"""
        return f"""
        {widget} {{ background: {self.bg}; color: {self.text}; }}
        QLabel {{ background: transparent; color: {self.text}; }}
        QScrollArea {{ border: none; background: transparent; }}
        """


# 定义抽象类
class ModelChatABS(metaclass=ABCMeta):
    """模型聊天的构建页面"""
    @staticmethod
    @abstractmethod
    def return_llm_class(model) -> local.LLM | cloud.LLM: pass


class MainWindowABS(metaclass=ABCMeta):
    @abstractmethod
    def addNavigation(
        self,
        text: str,
        widget,
        shortcut_keys: tuple[int, ...] | None = None,
        position: str = "top",
        category: str | None = None,
    ): pass
    @abstractmethod
    def removeNavigation(self, widget): pass
    @abstractmethod
    def create_category(self, category: str, position: str = "top"): pass
    @abstractmethod
    def remove_category(self, category: str): pass
    @abstractmethod
    def setTitle(self, title: str): pass


class IconListABS(metaclass=ABCMeta):
    @property
    @abstractmethod
    def SETTING(self): pass
    @property
    @abstractmethod
    def CHAT(self): pass
    @property
    @abstractmethod
    def SHUTDOWN(self): pass


class MenuWidgetABS(metaclass=ABCMeta):
    @abstractmethod
    def addSeparator(self): pass
    @abstractmethod
    def addAction(self, action): pass


class SwitchWidgetABS(metaclass=ABCMeta):
    @property
    @abstractmethod
    def stateChanged(self): pass
    @abstractmethod
    def setChecked(self, checked: bool): pass
    @abstractmethod
    def isChecked(self): pass


# 内部页面抽象类
class AnimationABS(metaclass=ABCMeta):
    """动画"""
    @property
    @abstractmethod
    def live2d_mot_signal(self): pass
    @property
    @abstractmethod
    def live2d_exp_signal(self): pass
