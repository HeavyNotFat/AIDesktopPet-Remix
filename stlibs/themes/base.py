from abc import ABCMeta, abstractmethod
from PySide6.QtWidgets import QWidget

from ..ai import local, cloud

_QWidgetMeta = type(QWidget)


class CombinedMeta(_QWidgetMeta, ABCMeta):
    pass


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
