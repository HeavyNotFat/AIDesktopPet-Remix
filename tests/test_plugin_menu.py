"""插件右键菜单的装配与子菜单展开（两个 shader 共用的那份逻辑）。"""

import os

import pytest

import stlibs
from stlibs.graphics.menu import add_plugin_menu, plugin_menu_groups, trigger_plugin_action

pytestmark = pytest.mark.ui

QtWidgets = pytest.importorskip("PySide6.QtWidgets", reason="菜单测试需要 PySide6")
QPoint = pytest.importorskip("PySide6.QtCore", reason="菜单测试需要 PySide6").QPoint


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
    # 复原：stlibs.graphics.chat / settings 是拿 SharingData.theme 当基类定义的，
    # 留成 None 会让后面 import 它们的地方直接 AttributeError
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


def test_two_plugins_get_two_sub_menus(theme, plugins_dir):
    root, manager = plugins_dir
    write_plugin(root, "cultivation", "养成系统", [("打开面板", "panel"), ("状态", "state")], order=10)
    write_plugin(root, "gacha", "桌宠扭蛋机", [("扭一次", "roll")], order=20)
    manager.load_all()

    menu, groups = build_menu(theme)

    assert [group.title for group in groups] == ["养成系统", "桌宠扭蛋机"]
    assert [entry["text"] for entry in menu._action_items] == ["设置", "养成系统", "桌宠扭蛋机", "关闭"]
    assert len(menu.sub_menus()) == 2
    assert [item["text"] for item in menu.sub_menus()[0]._action_items] == ["打开面板", "状态"]
    assert [item["text"] for item in menu.sub_menus()[1]._action_items] == ["扭一次"]


def test_sub_menu_entries_show_arrow(theme, plugins_dir):
    """有子菜单的条目要留出 ▸ 的位置（宽度里能看出来，比没有子菜单的宽）。"""
    root, manager = plugins_dir
    write_plugin(root, "cultivation", "养成系统", [("打开面板", "panel")], order=10)
    write_plugin(root, "gacha", "桌宠扭蛋机", [("扭一次", "roll")], order=20)
    manager.load_all()

    menu, _groups = build_menu(theme)
    has_sub = next(entry for entry in menu._action_items if entry["submenu"] is not None)
    plain = next(entry for entry in menu._action_items if entry["submenu"] is None)

    from PySide6.QtGui import QFontMetrics

    metrics = QFontMetrics(menu.hacker_font)
    assert has_sub["width"] - menu._measure(has_sub["text"], has_sub["pixmap"], False) == \
        metrics.horizontalAdvance("  ▸") + 4
    assert plain["width"] == menu._measure(plain["text"], plain["pixmap"], False)


def test_single_plugin_single_item_is_flat(theme, plugins_dir):
    """只有一个插件的一条菜单：平铺，不套一层子菜单。"""
    root, manager = plugins_dir
    write_plugin(root, "solo", "唯一插件", [("唯一一条", "one")])
    manager.load_all()

    menu, groups = build_menu(theme)

    assert len(groups) == 1
    assert menu.sub_menus() == [], "只有一条就别套子菜单了"
    assert [entry["text"] for entry in menu._action_items] == ["设置", "唯一一条", "关闭"]


def test_single_plugin_with_two_items_still_groups(theme, plugins_dir):
    root, manager = plugins_dir
    write_plugin(root, "solo", "唯一插件", [("第一条", "one"), ("第二条", "two")])
    manager.load_all()

    menu, _groups = build_menu(theme)

    assert len(menu.sub_menus()) == 1, "两条以上就该分组"
    assert [entry["text"] for entry in menu._action_items] == ["设置", "唯一插件", "关闭"]


def test_hover_opens_sub_menu_and_switching_closes_old(theme, plugins_dir):
    root, manager = plugins_dir
    write_plugin(root, "cultivation", "养成系统", [("打开面板", "panel")], order=10)
    write_plugin(root, "gacha", "桌宠扭蛋机", [("扭一次", "roll")], order=20)
    manager.load_all()

    menu, _groups = build_menu(theme)
    menu.exec(QPoint(30, 30))

    first = next(entry for entry in menu._action_items if entry["text"] == "养成系统")
    second = next(entry for entry in menu._action_items if entry["text"] == "桌宠扭蛋机")

    qapp = QtWidgets.QApplication.instance()

    first["label"].enterEvent(None)
    qapp.processEvents()
    assert first["submenu"].isVisible()
    assert not second["submenu"].isVisible()

    second["label"].enterEvent(None)
    qapp.processEvents()
    assert second["submenu"].isVisible()
    assert not first["submenu"].isVisible(), "换一组时旧子菜单要收起来"

    menu.close()


def test_clicking_sub_menu_entry_runs_plugin_and_closes(theme, plugins_dir):
    root, manager = plugins_dir
    write_plugin(root, "cultivation", "养成系统", [("打开面板", "panel")], order=10)
    write_plugin(root, "gacha", "桌宠扭蛋机", [("扭一次", "roll")], order=20)
    manager.load_all()

    menu, _groups = build_menu(theme)
    menu.exec(QPoint(30, 30))
    entry = next(item for item in menu._action_items if item["text"] == "养成系统")
    entry["label"].enterEvent(None)

    qapp = QtWidgets.QApplication.instance()
    qapp.processEvents()
    submenu = entry["submenu"]
    submenu._action_items[0]["label"].mousePressEvent(None)
    qapp.processEvents()

    assert not submenu.isVisible(), "点完子菜单要收起来"
    assert not menu.isVisible(), "父菜单也要一起收（否则只剩一个空菜单挂在屏幕上）"


def test_no_plugins_means_no_extra_separator(theme, plugins_dir):
    menu, groups = build_menu(theme)

    assert groups == []
    assert [entry["text"] for entry in menu._action_items] == ["设置", "关闭"]


def test_broken_manager_does_not_break_the_menu(theme, monkeypatch):
    class Boom:
        def menu_groups(self):
            raise RuntimeError("插件系统炸了")

    menu = theme.HackerMenu(None)
    menu.addAction(theme.Action("设置", menu))

    assert add_plugin_menu(menu, manager=Boom()) == []
    assert [entry["text"] for entry in menu._action_items] == ["设置"]


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
    """两个 shader 都要有主题动作工厂（否则主题换实现就断在运行时）。"""
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
