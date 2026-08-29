from abc import ABCMeta, abstractmethod
from PySide6.QtWidgets import QWidget

_QWidgetMeta = type(QWidget)


class CombinedMeta(_QWidgetMeta, ABCMeta):
    """
    解决冲突。如果需要引入：
    class X(Slot1, Slot2, metaclass=CombinedMeta):
        pass
    """
    pass


# 定义抽象类
class MainWindowABS(metaclass=ABCMeta):
    """UI主窗口"""
    @abstractmethod
    def addNavigation(self, text: str, widget, category: str): pass
    @abstractmethod
    def removeNavigation(self, widget): pass
    @abstractmethod
    def create_category(self, category: str, position: str = "top"): pass
    @abstractmethod
    def setTitle(self, title: str): pass


class IconListABS(metaclass=ABCMeta):
    """
    图标抽象类
    """
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
    """
    右键菜单抽象类
    """
    @abstractmethod
    def addSeparator(self): pass
    @abstractmethod
    def addAction(self): pass


class SwitchWidgetABS(metaclass=ABCMeta):
    """
    切换式开关抽象类
    """
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
