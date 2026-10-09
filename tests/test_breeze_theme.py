
import os

import pytest

pytestmark = pytest.mark.ui

QtWidgets = pytest.importorskip("PySide6.QtWidgets", reason="主题测试需要 PySide6")
QtCore = pytest.importorskip("PySide6.QtCore", reason="主题测试需要 PySide6")

import stlibs  # noqa: E402

THEME_NAME = "breeze"

# 契约里的 16 个映射，与 _ThemeTypingProtocol 同步
MAPPINGS = (
    "Window", "Button", "Label", "Menu", "Action", "Notify", "ScrollArea", "TextEdit",
    "LineEdit", "Slider", "Switch", "ComboBox", "CardWidget", "ChatWidget", "ChatBubble", "ModelChat",
)
# 6 个子模块，每个都要有设置窗会去取的页面类
SUBMODULE_PAGES = {
    "general": "GeneralPage",
    "llm": "LLMPage",
    "tts": "TTSPage",
    "settings": "SettingsPage",
    "animation": "AnimationPage",
    "plugins": "PluginsPage",
}


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    yield QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture(scope="module")
def theme(qapp):
    """装上 breeze 主题做断言，用完必须还原 SharingData.theme。"""
    previous = stlibs.SharingData.theme
    stlibs.SharingData.theme = stlibs.load_theme(THEME_NAME)
    yield stlibs.SharingData.theme
    stlibs.SharingData.theme = previous


def test_theme_is_discovered_by_load_theme(theme):
    assert theme.__name__ == f"stlibs.themes.{THEME_NAME}"
    assert theme is not stlibs.load_theme("hacker"), "别把新主题接回 hacker"


def test_all_mappings_exist(theme):
    missing = [name for name in MAPPINGS if not hasattr(theme, name)]
    assert missing == [], f"主题缺映射：{missing}"


def test_mappings_are_classes_and_iconlist_is_an_instance(theme):
    for name in MAPPINGS:
        assert isinstance(getattr(theme, name), type), f"{name} 应该是类"

    # 图标是 QPixmap 画的，得有 QApplication 才能 init（core.py 也是启动后再调）
    assert not isinstance(theme.IconList, type), "IconList 应该已经是实例"
    theme.IconList.init()
    for icon in ("SETTING", "CHAT", "SHUTDOWN"):
        assert hasattr(theme.IconList, icon)


def test_window_implements_the_navigation_contract(theme):
    for member in ("addNavigation", "removeNavigation", "create_category", "remove_category", "setTitle"):
        assert callable(getattr(theme.Window, member, None)), f"Window 缺 {member}"


def test_menu_implements_the_menu_contract(theme):
    assert callable(getattr(theme.Menu, "addAction", None))
    assert callable(getattr(theme.Menu, "addSeparator", None))
    assert hasattr(theme.Menu, "menu_closed"), "桌宠拖拽复位要靠 menu_closed 信号"


def test_menu_is_flat_without_submenus(theme):
    assert not hasattr(theme.Menu, "addMenu"), "插件菜单已改成一层平铺，主题不该再提供子菜单"


def test_chat_widget_contract(theme):
    """graphics/chat.py 靠这几个方法跟聊天窗打交道。"""
    for member in ("userInputSignal", "add_user_msg", "add_assistant_msg", "disable_send_button",
                   "enable_send_button", "update_bubble_widths", "scroll_to_bottom", "clear_messages"):
        assert hasattr(theme.ChatWidget, member), f"ChatWidget 缺 {member}"


def test_chat_bubble_contract(theme):
    for member in ("append_text", "updateBubbleWidth"):
        assert callable(getattr(theme.ChatBubble, member, None)), f"ChatBubble 缺 {member}"


def test_model_chat_contract(theme):
    assert callable(getattr(theme.ModelChat, "return_llm_class", None))


def test_action_signature_matches_callers(theme):
    """shader 与 graphics/menu.py 都按 ``Action(text, parent, icon)`` 造动作。"""
    action = theme.Action("设置", None, theme.IconList.SETTING)

    assert action.text() == "设置"
    assert not action.icon().isNull(), "带图标构造时图标要真的挂上"


def test_submodules_and_pages_exist(theme):
    for module_name, page in SUBMODULE_PAGES.items():
        assert hasattr(theme, module_name), f"缺子模块 {module_name}"
        module = getattr(theme, module_name)
        assert hasattr(module, page), f"子模块 {module_name} 缺 {page}"


def test_general_page_signals(theme, qapp):
    """设置窗把常规页的信号转成桌宠的实时调整，名字不能变。"""
    page = theme.general.GeneralPage(None)

    for signal_name in ("opacity_changed", "size_changed", "rotate_changed", "model_live2d"):
        assert hasattr(page, signal_name), f"GeneralPage 缺 {signal_name}"


def test_animation_page_signals(theme, qapp):
    page = theme.animation.AnimationPage(None)

    for signal_name in ("live2d_mot_signal", "live2d_exp_signal"):
        assert hasattr(page, signal_name), f"AnimationPage 缺 {signal_name}"


def test_pages_are_constructible_and_named(theme, qapp):
    """设置窗靠 windowTitle() 当导航文字，六页都要建得出来。"""
    pages = {
        "general": theme.general.GeneralPage(None),
        "llm": theme.llm.LLMPage(None),
        "tts": theme.tts.TTSPage(None),
        "animation": theme.animation.AnimationPage(None),
        "plugins": theme.plugins.PluginsPage(None),
        "settings": theme.settings.SettingsPage(None),
    }

    for name, page in pages.items():
        assert page.windowTitle(), f"{name} 页没有标题"


def test_notify_can_be_constructed(theme, qapp):
    note = theme.Notify("主题自检：这条提示应该能显示", "success", 800)

    assert note is not None
    assert note.isVisible() or note.parent() is None

    # 用完必须收干净：提示条是全局堆叠的，留着会污染后面按"当前主题"写的用例
    note.dismiss()
    for pending in list(theme.Notify._stack):
        pending.hide()
        pending.deleteLater()
    theme.Notify._stack.clear()
    stlibs.SharingData.setting_window = None
    qapp.processEvents()


def test_available_themes_lists_both(theme):
    from stlibs.themes.breeze.settings import available_themes

    themes = available_themes()

    assert "hacker" in themes
    assert THEME_NAME in themes


def test_window_builds_pages_and_navigation(theme, qapp):
    """真的建一个主窗口：加分类、加导航、切页、再摘掉。"""
    previous_window = stlibs.SharingData.setting_window
    window = theme.Window()
    stlibs.SharingData.setting_window = window
    page = theme.Label("演示页")
    window.addNavigation("演示", page, shortcut_keys=(QtCore.Qt.Key_Control, QtCore.Qt.Key_9),
                         category="测试分类")

    assert window.pages.currentWidget() is page
    assert "演示" in window.nav_widgets

    window.setTitle("换了个标题")
    window.removeNavigation(page)
    assert "演示" not in window.nav_widgets

    assert window.remove_category("测试分类") is True
    assert window.remove_category("测试分类") is False

    window.close()
    stlibs.SharingData.setting_window = previous_window
    qapp.processEvents()
