
import os

import pytest

import stlibs
from stlibs.graphics.menu import (
    add_plugin_menu,
    item_label,
    plugin_menu_groups,
    plugin_menu_items,
    trigger_plugin_action,
)

pytestmark = pytest.mark.ui

QtWidgets = pytest.importorskip("PySide6.QtWidgets", reason="菜单测试需要 PySide6")
QtCore = pytest.importorskip("PySide6.QtCore", reason="菜单测试需要 PySide6")
QPoint = QtCore.QPoint
Qt = QtCore.Qt


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    yield QApplication.instance() or QApplication([])


@pytest.fixture
def theme(qapp):
    from stlibs.themes import hacker

    previous = stlibs.SharingData.theme
    stlibs.SharingData.theme = hacker
    yield hacker
    # 复原：留成 None 会让后面拿 SharingData.theme 当基类 import 的地方 AttributeError
    stlibs.SharingData.theme = previous


@pytest.fixture
def plugins_dir(tmp_path, monkeypatch):
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
    return root, fresh


def write_plugin(root, plugin_id, name, items, **extra):
    import json

    directory = root / plugin_id
    directory.mkdir(parents=True, exist_ok=True)
    lines = ["def on_load(api):"]
    for label, action in items:
        lines.append(f"    api.add_menu_item({label!r}, {action!r})")
    lines.append("def on_command(api, ctx):")
    lines.append("    return '点了 ' + ctx['name']")
    (directory / "main.py").write_text("\n".join(lines) + "\n", encoding="utf-8")

    payload = {"id": plugin_id, "name": name, "language": "python", "entry": "main.py"}
    payload.update(extra)
    (directory / "plugin.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return directory


def build_menu(theme):
    menu = theme.HackerMenu(None)
    menu.addAction(theme.Action("设置", menu, theme.IconList.SETTING))
    menu.addSeparator()
    groups = add_plugin_menu(menu)
    menu.addSeparator()
    menu.addAction(theme.Action("关闭", menu, theme.IconList.SHUTDOWN))
    return menu, groups


def texts(menu):
    """菜单里一层的条目文字，自己画的条目要翻 _action_items。"""
    return [entry["text"] for entry in menu._action_items]


def settle(times=4):
    app = QtWidgets.QApplication.instance()
    for _ in range(times):
        app.processEvents()


class FakeClick:
    """只带 button() 的最小鼠标事件替身。"""

    def __init__(self, button=Qt.MouseButton.LeftButton):
        self._button = button

    def button(self):
        return self._button


def test_two_plugins_are_flattened_into_one_list(theme, plugins_dir):
    """两个插件各两条：全部平铺，一条一层，没有子菜单。"""
    root, manager = plugins_dir
    write_plugin(root, "cultivation", "养成系统", [("打开面板", "panel"), ("状态", "state")], order=10)
    write_plugin(root, "gacha", "桌宠扭蛋机", [("扭一次", "roll")], order=20)
    manager.load_all()

    menu, groups = build_menu(theme)

    assert [group.title for group in groups] == ["养成系统", "桌宠扭蛋机"]
    assert texts(menu) == [
        "设置",
        "养成系统 · 打开面板",
        "养成系统 · 状态",
        "桌宠扭蛋机 · 扭一次",
        "关闭",
    ]
    assert not hasattr(menu, "addMenu"), "子菜单那套已经从主题菜单里拿掉了"


def test_flat_entries_keep_their_plugin_icon(theme, plugins_dir):
    """回归：平铺后没有分组标题兜底，每条都得带插件自己的图标。"""
    root, manager = plugins_dir
    write_plugin(root, "cultivation", "养成系统", [("打开面板", "panel")], order=10)
    write_plugin(root, "gacha", "桌宠扭蛋机", [("扭一次", "roll")], order=20)
    manager.load_all()

    menu, _groups = build_menu(theme)

    entries = [entry for entry in menu._action_items if " · " in entry["text"]]
    assert len(entries) == 2
    for entry in entries:
        assert entry["pixmap"] is not None, f"{entry['text']} 少了插件图标"

    # 条目的 QAction 上也得有图标（SDK/探针读的是 QAction）
    icons = [action.icon() for action in menu.menu_actions() if " · " in action.text()]
    assert all(not icon.isNull() for icon in icons)


def test_single_plugin_single_item_is_still_flat(theme, plugins_dir):
    """只有一个插件的一条菜单：照样平铺（标签仍带插件名前缀）。"""
    root, manager = plugins_dir
    write_plugin(root, "solo", "唯一插件", [("唯一一条", "one")])
    manager.load_all()

    menu, groups = build_menu(theme)

    assert len(groups) == 1
    assert texts(menu) == ["设置", "唯一插件 · 唯一一条", "关闭"]


def test_item_label_formats_plugin_then_menu(theme, plugins_dir):
    """标签格式 ``插件名 · 菜单名``，插件名已在菜单名里就不重复。"""
    root, manager = plugins_dir
    write_plugin(root, "solo", "唯一插件", [("唯一一条", "one"), ("唯一插件：自报家门", "two")])
    write_plugin(root, "gacha", "桌宠扭蛋机", [("扭蛋机：来一发", "roll")], order=20)
    manager.load_all()

    labels = {item.action: item_label(group, item) for group, item in plugin_menu_items()}

    assert labels["one"] == "唯一插件 · 唯一一条"
    assert labels["two"] == "唯一插件：自报家门", "插件名已经写进菜单名了，别再加前缀"
    assert labels["roll"] == "扭蛋机：来一发", "标题「桌宠扭蛋机」去掉桌宠前缀就是菜单名前缀，也别重复"

    class NoTitle:
        title = ""

    group, item = next(pair for pair in plugin_menu_items() if pair[1].action == "roll")
    assert item_label(NoTitle(), item) == "扭蛋机：来一发"


def test_clicking_a_flat_entry_runs_plugin_and_closes(theme, plugins_dir):
    """点平铺的插件条目：要触发插件回调，并把菜单收起来。"""
    root, manager = plugins_dir
    write_plugin(root, "cultivation", "养成系统", [("打开面板", "panel")], order=10)
    write_plugin(root, "gacha", "桌宠扭蛋机", [("扭一次", "roll")], order=20)
    manager.load_all()

    called = []
    from stlibs.graphics import menu as menu_module

    original = menu_module.trigger_plugin_action
    menu_module.trigger_plugin_action = lambda action: called.append(action)

    try:
        menu, _groups = build_menu(theme)
        menu.exec(QPoint(30, 30))
        entry = next(item for item in menu._action_items if item["text"] == "养成系统 · 打开面板")
        entry["label"].mousePressEvent(FakeClick(Qt.MouseButton.LeftButton))
        settle(6)
    finally:
        menu_module.trigger_plugin_action = original

    assert called == ["panel"]
    assert not menu.isVisible(), "点完要把菜单收起来"


def test_right_clicking_a_flat_entry_does_nothing(theme, plugins_dir):
    """右键点条目不该触发动作，也不该把菜单收掉。"""
    root, manager = plugins_dir
    write_plugin(root, "cultivation", "养成系统", [("打开面板", "panel")], order=10)
    write_plugin(root, "gacha", "桌宠扭蛋机", [("扭一次", "roll")], order=20)
    manager.load_all()

    called = []
    from stlibs.graphics import menu as menu_module

    original = menu_module.trigger_plugin_action
    menu_module.trigger_plugin_action = lambda action: called.append(action)

    try:
        menu, _groups = build_menu(theme)
        menu.exec(QPoint(30, 30))
        entry = next(item for item in menu._action_items if item["text"] == "养成系统 · 打开面板")
        entry["label"].mousePressEvent(FakeClick(Qt.MouseButton.RightButton))
        settle(4)
    finally:
        menu_module.trigger_plugin_action = original

    assert called == []
    assert menu.isVisible(), "右键不该顺手把菜单关了"
    menu.close()


def test_entries_share_the_widest_row(theme, plugins_dir):
    """一行铺满：所有条目宽度一致，短的不会只亮一半。"""
    root, manager = plugins_dir
    write_plugin(root, "cultivation", "养成系统", [("打开面板", "panel"), ("状态", "state")], order=10)
    write_plugin(root, "gacha", "桌宠扭蛋机", [("扭一次", "roll")], order=20)
    manager.load_all()

    menu, _groups = build_menu(theme)

    widths = {entry["label"].width() for entry in menu._action_items}
    assert len(widths) == 1, f"条目宽度不一致：{widths}"


def test_menu_closed_signal_fires_once_per_close(theme, plugins_dir):
    """菜单收起要通知宿主，桌宠靠它复位拖拽状态。"""
    root, manager = plugins_dir
    write_plugin(root, "cultivation", "养成系统", [("打开面板", "panel")], order=10)
    manager.load_all()

    menu, _groups = build_menu(theme)
    fired = []
    menu.menu_closed.connect(lambda: fired.append(1))

    menu.exec(QPoint(30, 30))
    settle()
    assert fired == [], "只是打开不该发关闭信号"

    menu.close()
    settle()
    assert len(fired) == 1, f"收起一次只该通知一次（实际 {len(fired)}）"

    # 再开再关：每次关闭都要通知（Popup 是被反复开关的）
    menu.exec(QPoint(30, 30))
    settle()
    menu.close()
    settle()
    assert len(fired) == 2


def test_no_plugins_means_no_extra_separator(theme, plugins_dir):
    menu, groups = build_menu(theme)

    assert groups == []
    assert texts(menu) == ["设置", "关闭"]


def test_broken_manager_does_not_break_the_menu(theme, monkeypatch):
    class Boom:
        def menu_groups(self):
            raise RuntimeError("插件系统炸了")

    menu = theme.HackerMenu(None)
    menu.addAction(theme.Action("设置", menu))

    assert add_plugin_menu(menu, manager=Boom()) == []
    assert texts(menu) == ["设置"]


def test_trigger_reports_plugin_result(theme, plugins_dir, monkeypatch):
    root, manager = plugins_dir
    write_plugin(root, "solo", "唯一插件", [("唯一一条", "one")])
    manager.load_all()

    calls = []
    monkeypatch.setattr(stlibs, "notify", lambda text, level="info", timeout=2600: calls.append((level, text)))

    assert trigger_plugin_action("one") == "点了 one"
    assert calls and calls[-1][0] == "info"
    assert "点了 one" in calls[-1][1]


def test_trigger_unknown_action_is_silent(theme, plugins_dir, monkeypatch):
    _root, _manager = plugins_dir
    calls = []
    monkeypatch.setattr(stlibs, "notify", lambda text, level="info", timeout=2600: calls.append((level, text)))

    assert not trigger_plugin_action("不存在的动作"), "认不出来的动作不该有返回文本"
    assert calls == []


def test_shaders_expose_the_plugin_menu_hook(theme):
    """两个 shader 都要有主题动作工厂，否则运行时断掉。"""
    import shader.live2d as live2d
    import shader.static as static_shader

    for module in (live2d, static_shader):
        assert hasattr(module.PublicShader, "add_plugin_actions")
        assert hasattr(module.PublicShader, "plugin_menu_action")
        assert hasattr(module.PublicShader, "run_plugin_action")


def test_plugin_menu_groups_ignores_disabled(theme, plugins_dir):
    root, manager = plugins_dir
    write_plugin(root, "cultivation", "养成系统", [("打开面板", "panel")])
    manager.load_all()
    manager.set_enabled("cultivation", False)

    assert plugin_menu_groups() == []
