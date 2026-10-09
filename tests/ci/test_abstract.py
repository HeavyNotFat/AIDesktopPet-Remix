from __future__ import annotations

from conftest import checks_of, findings_of, run_checks


def test_abstract_method_not_implemented_is_reported(mini_repo):
    root = mini_repo(
        {
            "pkg/impl.py": (
                "from stlibs.themes.base import ModelChatABS\n"
                "\n"
                "\n"
                "class Chat(ModelChatABS):\n"
                "    pass\n"
            )
        },
        contract=True,
    )
    findings = findings_of(root, "abs/contract")
    assert len(findings) == 1
    assert "return_llm_class" in findings[0].message
    # 抽象基类的定义处不应该被误报
    assert findings[0].location.path == "pkg/impl.py"


def test_fully_implemented_class_is_clean(mini_repo):
    root = mini_repo(
        {
            "pkg/impl.py": (
                "from stlibs.themes.base import ModelChatABS\n"
                "\n"
                "\n"
                "class Chat(ModelChatABS):\n"
                "    @staticmethod\n"
                "    def return_llm_class(model):\n"
                "        return model\n"
            )
        },
        contract=True,
    )
    assert findings_of(root, "abs/contract") == []


def test_class_attribute_counts_as_implementation(mini_repo):
    """类属性也算实现，不算「没实现」。"""
    root = mini_repo(
        {
            "stlibs/themes/base.py": (
                "from abc import ABCMeta, abstractmethod\n"
                "\n"
                "\n"
                "class IconListABS(metaclass=ABCMeta):\n"
                "    @property\n"
                "    @abstractmethod\n"
                "    def SETTING(self): pass\n"
            ),
            "pkg/impl.py": (
                "from stlibs.themes.base import IconListABS\n"
                "\n"
                "\n"
                "class IconList(IconListABS):\n"
                "    SETTING = None\n"
            ),
        }
    )
    assert findings_of(root, "abs/contract") == []


def test_abstract_class_left_abstract_is_not_reported(mini_repo):
    """中间抽象基类故意不实现，属于合法用法。"""
    root = mini_repo(
        {
            "pkg/impl.py": (
                "from abc import abstractmethod\n"
                "\n"
                "from stlibs.themes.base import ModelChatABS\n"
                "\n"
                "\n"
                "class Base(ModelChatABS):\n"
                "    @abstractmethod\n"
                "    def extra(self): pass\n"
            )
        },
        contract=True,
    )
    assert findings_of(root, "abs/contract") == []


def test_instantiating_abstract_class(mini_repo):
    root = mini_repo(
        {
            "pkg/impl.py": (
                "from stlibs.themes.base import ModelChatABS\n"
                "\n"
                "\n"
                "class Chat(ModelChatABS):\n"
                "    pass\n"
                "\n"
                "\n"
                "obj = Chat()\n"
            )
        },
        contract=True,
    )
    findings = findings_of(root, "abs/instantiate")
    assert len(findings) == 1
    assert findings[0].severity.value == "error"
    assert findings[0].location.line == 8


def test_decorator_order(mini_repo):
    root = mini_repo(
        {
            "pkg/mod.py": (
                "from abc import ABCMeta, abstractmethod\n"
                "\n"
                "\n"
                "class Good(metaclass=ABCMeta):\n"
                "    @property\n"
                "    @abstractmethod\n"
                "    def ok(self): pass\n"
                "\n"
                "\n"
                "class Bad(metaclass=ABCMeta):\n"
                "    @abstractmethod\n"
                "    @property\n"
                "    def wrong(self): pass\n"
            )
        }
    )
    findings = findings_of(root, "abs/decorator-order")
    assert [f.location.line for f in findings] == [13]


def test_abstractmethod_without_abcmeta(mini_repo):
    root = mini_repo(
        {
            "pkg/mod.py": (
                "from abc import abstractmethod\n"
                "from PySide6.QtWidgets import QWidget\n"
                "\n"
                "\n"
                "class Canvas(QWidget):\n"
                "    @abstractmethod\n"
                "    def on_draw(self): pass\n"
            )
        }
    )
    findings = findings_of(root, "abs/not-enforced")
    assert len(findings) == 1
    assert "Canvas" in findings[0].message


def test_combined_metaclass_is_accepted(mini_repo):
    root = mini_repo(
        {
            "stlibs/themes/base.py": (
                "from abc import ABCMeta, abstractmethod\n"
                "from PySide6.QtWidgets import QWidget\n"
                "\n"
                "_QWidgetMeta = type(QWidget)\n"
                "\n"
                "\n"
                "class CombinedMeta(_QWidgetMeta, ABCMeta):\n"
                "    pass\n"
                "\n"
                "\n"
                "class SwitchWidgetABS(metaclass=ABCMeta):\n"
                "    @abstractmethod\n"
                "    def isChecked(self): pass\n"
            ),
            "pkg/widget.py": (
                "from abc import abstractmethod\n"
                "\n"
                "from PySide6.QtWidgets import QWidget\n"
                "\n"
                "from stlibs.themes.base import SwitchWidgetABS, CombinedMeta\n"
                "\n"
                "\n"
                "class Switch(QWidget, SwitchWidgetABS, metaclass=CombinedMeta):\n"
                "    @abstractmethod\n"
                "    def extra(self): pass\n"
                "\n"
                "    def isChecked(self):\n"
                "        return False\n"
            ),
        }
    )
    assert findings_of(root, "abs/metaclass") == []
    # 自定义合并元类继承链里有 ABCMeta，不该被当成"约束不生效"
    assert findings_of(root, "abs/not-enforced") == []


def test_metaclass_conflict_detected(mini_repo):
    root = mini_repo(
        {
            "pkg/widget.py": (
                "from PySide6.QtWidgets import QWidget\n"
                "\n"
                "from stlibs.themes.base import SwitchWidgetABS\n"
                "\n"
                "\n"
                "class Switch(QWidget, SwitchWidgetABS):\n"
                "    def isChecked(self):\n"
                "        return False\n"
            )
        },
        contract=True,
    )
    findings = findings_of(root, "abs/metaclass")
    assert len(findings) == 1
    assert "metaclass conflict" in findings[0].message


def test_signature_too_many_required_params(mini_repo):
    root = mini_repo(
        {
            "stlibs/themes/base.py": (
                "from abc import ABCMeta, abstractmethod\n"
                "\n"
                "\n"
                "class MenuWidgetABS(metaclass=ABCMeta):\n"
                "    @abstractmethod\n"
                "    def addAction(self): pass\n"
            ),
            "pkg/menu.py": (
                "from stlibs.themes.base import MenuWidgetABS\n"
                "\n"
                "\n"
                "class Menu(MenuWidgetABS):\n"
                "    def addAction(self, action): pass\n"
            ),
        }
    )
    findings = findings_of(root, "abs/signature")
    assert len(findings) == 1
    assert findings[0].severity.value == "error"
    assert "必填参数" in findings[0].message


def test_signature_positional_rename_is_warning(mini_repo):
    root = mini_repo(
        {
            "stlibs/themes/base.py": (
                "from abc import ABCMeta, abstractmethod\n"
                "\n"
                "\n"
                "class MainWindowABS(metaclass=ABCMeta):\n"
                "    @abstractmethod\n"
                "    def addNavigation(self, text: str, widget, category: str): pass\n"
            ),
            "pkg/window.py": (
                "from stlibs.themes.base import MainWindowABS\n"
                "\n"
                "\n"
                "class Win(MainWindowABS):\n"
                "    def addNavigation(self, text, widget, shortcut_keys=None, position='top', category=None): pass\n"
            ),
        }
    )
    findings = findings_of(root, "abs/signature")
    assert len(findings) == 1
    assert findings[0].severity.value == "warning"
    assert "第 3 个参数名" in findings[0].message


def test_abstractproperty_implemented_as_method(mini_repo):
    root = mini_repo(
        {
            "stlibs/themes/base.py": (
                "from abc import ABCMeta, abstractmethod\n"
                "\n"
                "\n"
                "class AnimationABS(metaclass=ABCMeta):\n"
                "    @property\n"
                "    @abstractmethod\n"
                "    def signal(self): pass\n"
            ),
            "pkg/page.py": (
                "from stlibs.themes.base import AnimationABS\n"
                "\n"
                "\n"
                "class Page(AnimationABS):\n"
                "    def signal(self): pass\n"
            ),
        }
    )
    findings = findings_of(root, "abs/signature")
    assert len(findings) == 1
    assert "property" in findings[0].message


def test_all_checks_report_no_crash_on_mini_repo(mini_repo):
    root = mini_repo(
        {
            "pkg/mod.py": (
                "from abc import ABCMeta, abstractmethod\n"
                "\n"
                "\n"
                "class A(metaclass=ABCMeta):\n"
                "    @abstractmethod\n"
                "    def x(self): pass\n"
            )
        },
        contract=True,
    )
    report = run_checks(root)
    assert report.crashes == [], [r.crash for r in report.crashes]
    assert checks_of(report, "abs/contract") == []
