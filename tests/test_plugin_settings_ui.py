import importlib
import json
import os
import sys
import textwrap
from pathlib import Path

import pytest

import stlibs

pytestmark = pytest.mark.ui

QtWidgets = pytest.importorskip("PySide6.QtWidgets", reason="插件设置页 UI 测试需要 PySide6")

PAGE_PLUGIN = '''
    def on_load(api):
        api.add_settings_page("养猫设置", form=[
            {"type": "text", "key": "suffix", "label": "后缀", "default": "喵"},
            {"type": "switch", "key": "noisy", "label": "爱说话", "default": True},
        ], hint="这些值存在主配置里")

    def on_settings_action(api, ctx):
        api.storage_set("last", ctx)
        return "收到 " + str(ctx["action"])
'''

# 仓库里那个真插件（养成系统），用来跑端到端
PLUGIN_DIR = Path(__file__).resolve().parents[1] / "plugins" / "cultivation_system"


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    yield QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def theme(qapp):
    previous = stlibs.SharingData.theme
    stlibs.SharingData.theme = stlibs.load_theme("hacker")
    yield stlibs.SharingData.theme
    stlibs.SharingData.theme = previous


@pytest.fixture
def settings_module(theme):
    """Settings 的窗口基类导入时定死，先把主题绑好再导。"""
    module = importlib.import_module("stlibs.graphics.settings")
    if not issubclass(module.Settings, theme.Window):
        module = importlib.reload(module)
    return module


@pytest.fixture
def manager(tmp_path, monkeypatch):
    root = tmp_path / "plugins"
    root.mkdir()

    monkeypatch.setattr(stlibs, "CONFIG_PATH", str(tmp_path / "configure.json"))
    monkeypatch.setattr(stlibs.Config, "plugins", {
        "enable": True, "directory": str(root), "disabled": [], "settings": {}, "timeout": 3.0,
    }, raising=False)

    from stlibs.plugins import PluginManager
    from stlibs.plugins.manager import core as manager_module

    fresh = PluginManager(directory=str(root))
    monkeypatch.setattr(manager_module, "manager", fresh)
    return fresh


@pytest.fixture
def said(monkeypatch):
    calls = []
    monkeypatch.setattr(stlibs, "notify", lambda text, level="info", timeout=2600: calls.append(text))
    return calls


@pytest.fixture
def window(settings_module, manager, qapp):
    """设置窗要绑在测试的 manager 上，所以 manager 必须先就位。"""
    previous = stlibs.SharingData.setting_window
    built = settings_module.Settings()
    stlibs.SharingData.setting_window = built
    yield built
    stlibs.SharingData.setting_window = previous
    built.hide()
    built.deleteLater()
    qapp.processEvents()


def write_plugin(root, plugin_id, code, **manifest):
    directory = Path(root) / plugin_id
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "main.py").write_text(textwrap.dedent(code), encoding="utf-8")
    data = {"id": plugin_id, "name": f"插件 {plugin_id}", "language": "python", "entry": "main.py"}
    data.update(manifest)
    (directory / "plugin.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return directory


def nav_titles(category):
    """分类下面那些导航项的文字。"""
    titles = []
    for index in range(category.content_layout.count()):
        widget = category.content_layout.itemAt(index).widget()
        label = getattr(widget, "label", None)
        if label is not None:
            titles.append(label.text())
    return titles


def nav_button(category, text):
    for index in range(category.content_layout.count()):
        widget = category.content_layout.itemAt(index).widget()
        label = getattr(widget, "label", None)
        if label is not None and text in label.text():
            return widget
    return None


def has_pixmap(button):
    for label in button.findChildren(QtWidgets.QLabel):
        pixmap = label.pixmap()
        if pixmap is not None and not pixmap.isNull():
            return True
    return False


def category_of(window, settings_module):
    return window.categories[settings_module.PLUGIN_CATEGORY]


def test_settings_window_has_an_empty_plugin_category(window, settings_module):
    category = category_of(window, settings_module)

    assert settings_module.PLUGIN_CATEGORY == "插件"
    assert nav_titles(category) == ["插件"], "没有插件时分类里只有宿主的管理页"
    assert "插件" in window.nav_widgets


def test_plugin_page_mounts_under_the_plugin_category(window, settings_module, manager):
    write_plugin(manager.directory, "alpha", PAGE_PLUGIN)
    manager.load_all()

    titles = nav_titles(category_of(window, settings_module))
    assert len(titles) == 2
    assert any("养猫设置" in title for title in titles), titles

    spec = manager.pages.pages("alpha")[0]
    widget = window.plugin_page(spec.id)
    assert widget is not None
    assert widget.windowTitle() == "养猫设置"
    assert set(widget.controls) == {"suffix", "noisy"}


def test_nav_entry_carries_the_plugin_icon(window, settings_module, manager):
    write_plugin(manager.directory, "alpha", PAGE_PLUGIN)
    manager.load_all()

    button = nav_button(category_of(window, settings_module), "养猫设置")

    assert button is not None
    assert has_pixmap(button), "导航项左边要有插件图标"


def test_switch_writes_setting_and_calls_hook(window, settings_module, manager, said):
    write_plugin(manager.directory, "alpha", PAGE_PLUGIN)
    manager.load_all()
    spec = manager.pages.pages("alpha")[0]
    widget = window.plugin_page(spec.id)

    widget.controls["noisy"].setChecked(False)

    assert stlibs.Config.plugins["settings"]["alpha"]["noisy"] is False
    assert manager._apis["alpha"].storage_get("last")["key"] == "noisy"
    assert said and "收到" in said[-1]


def test_text_row_commits_on_editing_finished(window, settings_module, manager):
    write_plugin(manager.directory, "alpha", PAGE_PLUGIN)
    manager.load_all()
    spec = manager.pages.pages("alpha")[0]
    widget = window.plugin_page(spec.id)
    edit = widget.controls["suffix"]
    assert edit.text() == "喵"

    edit.setText("汪")
    edit.editingFinished.emit()

    assert stlibs.Config.plugins["settings"]["alpha"]["suffix"] == "汪"


def test_number_row_rejects_junk(window, settings_module, manager, said):
    write_plugin(manager.directory, "alpha", '''
        def on_load(api):
            api.add_settings_page("数字页", form=[
                {"type": "number", "key": "times", "label": "次数", "default": 3, "min": 1, "max": 5},
            ])
    ''', key="numbers")
    manager.load_all()
    spec = manager.pages.pages("alpha")[0]
    widget = window.plugin_page(spec.id)
    edit = widget.controls["times"]

    edit.setText("不是数字")
    edit.editingFinished.emit()
    assert edit.text() == "3", "填了非数字要退回原来的值"
    assert said and "要填数字" in said[-1]

    edit.setText("9")
    edit.editingFinished.emit()
    assert stlibs.Config.plugins["settings"]["alpha"]["times"] == 5, "超出上限要夹回来"


def test_unload_removes_the_page_from_the_window(window, settings_module, manager):
    write_plugin(manager.directory, "alpha", PAGE_PLUGIN)
    manager.load_all()
    spec = manager.pages.pages("alpha")[0]
    widget = window.plugin_page(spec.id)
    assert widget is not None

    manager.unload("alpha")

    assert nav_titles(category_of(window, settings_module)) == ["插件"]
    assert window.plugin_page(spec.id) is None
    assert widget.parent() is None


def test_python_builder_page_is_mounted(window, settings_module, manager):
    write_plugin(manager.directory, "alpha", '''
        from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

        def build(parent=None):
            page = QWidget(parent)
            page.setWindowTitle("自绘页")
            QVBoxLayout(page).addWidget(QLabel("我自己画的界面"))
            return page

        def on_load(api):
            api.add_settings_page("自绘页", builder=build, key="custom")
    ''')
    manager.load_all()

    widget = window.plugin_page("alpha:custom")

    assert isinstance(widget, QtWidgets.QWidget)
    assert widget.findChild(QtWidgets.QLabel).text() == "我自己画的界面"


def test_broken_builder_shows_a_message_page(window, settings_module, manager, said):
    write_plugin(manager.directory, "alpha", '''
        def on_load(api):
            api.add_settings_page("坏页", builder=lambda parent=None: 1 / 0, key="bad")
    ''')
    manager.load_all()

    widget = window.plugin_page("alpha:bad")
    texts = [label.text() for label in widget.findChildren(QtWidgets.QLabel)]

    assert any("构建失败" in text for text in texts), texts


def test_refresh_rebuilds_the_controls(window, settings_module, manager):
    write_plugin(manager.directory, "alpha", PAGE_PLUGIN)
    manager.load_all()
    spec = manager.pages.pages("alpha")[0]
    before = window.plugin_page(spec.id)
    assert before.controls["suffix"].text() == "喵"

    manager.set_setting("alpha", "suffix", "汪")
    manager.pages.refresh("alpha", spec.key)

    after = window.plugin_page(spec.id)
    assert after is not before, "刷新要重建控件"
    assert after.controls["suffix"].text() == "汪"


def test_show_plugin_page_switches_to_it(window, settings_module, manager):
    write_plugin(manager.directory, "alpha", PAGE_PLUGIN)
    manager.load_all()
    spec = manager.pages.pages("alpha")[0]

    assert window.show_plugin_page(spec.id) is True
    assert window.pages.currentWidget() is window.plugin_page(spec.id)
    assert window.show_plugin_page("没有这页") is False


def test_real_cultivation_plugin_page(window, settings_module, manager, qapp, said):
    """真插件端到端：养成系统的设置页挂进「插件」分类，按钮回调到插件。"""
    import shutil

    shutil.copytree(PLUGIN_DIR, Path(manager.directory) / "cultivation_system",
                    ignore=shutil.ignore_patterns(".data", "__pycache__"))
    manager.load_all()

    spec = manager.pages.find("cultivation_system", "settings")
    assert spec is not None, "养成系统没有注册设置页"
    widget = window.plugin_page(spec.id)
    assert widget is not None
    assert any("养成系统" in title and "养成设置" in title
               for title in nav_titles(category_of(window, settings_module)))

    widget.controls["click_coin"].setText("9")
    widget.controls["click_coin"].editingFinished.emit()
    assert stlibs.Config.plugins["settings"]["cultivation_system"]["click_coin"] == 9

    widget.controls["cultivation_system:status"].click()
    assert said and "金币" in said[-1]

    manager.unload("cultivation_system")
    assert window.plugin_page(spec.id) is None


@pytest.mark.parametrize("theme_name", ["hacker", "breeze"])
def test_form_rows_use_the_theme_widgets(theme_name, qapp):
    from stlibs.graphics.plugin_page import PluginSettingsPage
    from stlibs.plugins.pages import PluginPages

    previous = stlibs.SharingData.theme
    stlibs.SharingData.theme = stlibs.load_theme(theme_name)
    page = None
    try:
        spec = PluginPages().add("alpha", "主题页", form=[
            {"type": "text", "key": "suffix", "label": "后缀"},
            {"type": "switch", "key": "noisy", "label": "爱说话"},
            {"type": "select", "key": "mode", "label": "模式", "options": ["a", "b"]},
        ])
        page = PluginSettingsPage(spec)
        theme = stlibs.SharingData.theme

        assert isinstance(page.controls["suffix"], theme.LineEdit)
        assert isinstance(page.controls["noisy"], theme.Switch)
        assert isinstance(page.controls["mode"], theme.ComboBox)
    finally:
        stlibs.SharingData.theme = previous
        if page is not None:
            page.deleteLater()
        qapp.processEvents()


def test_settings_module_is_reloadable(settings_module, theme):
    """Settings 的基类必须还是当前主题的窗口，不能被写死。"""
    assert issubclass(settings_module.Settings, theme.Window)
    assert "stlibs.graphics.settings" in sys.modules
