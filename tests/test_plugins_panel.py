import json
import textwrap

import pytest

import stlibs
from stlibs.plugins.manager import core as core_module
from stlibs.plugins.manager.panel import EMPTY_HINT, READY_HINT, PluginsPanel, state_text


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    root = tmp_path / "plugins"
    root.mkdir()

    monkeypatch.setattr(stlibs, "CONFIG_PATH", str(tmp_path / "configure.json"))
    monkeypatch.setattr(stlibs.Config, "plugins", {
        "enable": True, "directory": str(root), "disabled": [], "settings": {}, "timeout": 3.0,
    }, raising=False)

    from stlibs.plugins import PluginManager
    fresh = PluginManager(directory=str(root))
    monkeypatch.setattr(core_module, "manager", fresh)
    return root, fresh


def write_plugin(root, plugin_id, code, **extra):
    directory = root / plugin_id
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "main.py").write_text(textwrap.dedent(code), encoding="utf-8")
    payload = {"id": plugin_id, "name": f"插件 {plugin_id}", "language": "python", "entry": "main.py"}
    payload.update(extra)
    (directory / "plugin.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


OK_PLUGIN = '''
    def on_load(api):
        api.register_command("cmd")
'''


def test_panel_uses_current_singleton(isolated):
    _root, fresh = isolated

    assert PluginsPanel().manager is fresh, "单例被换掉后，面板要跟着换（不能缓存旧对象）"


def test_rows_and_hint_when_empty(isolated):
    panel = PluginsPanel()
    panel.refresh()

    assert panel.rows() == []
    assert panel.hint() == EMPTY_HINT


def test_rows_describe_loaded_plugin(isolated):
    root, manager = isolated
    write_plugin(root, "alpha", OK_PLUGIN)
    manager.load_all()
    panel = PluginsPanel(manager)
    panel.refresh()

    row = panel.rows()[0]

    assert row["id"] == "alpha"
    assert row["title"] == "插件 alpha  (alpha)"
    assert row["language"] == "Python（进程内）"
    assert row["state"].startswith("已加载")
    assert int(row["calls"]) >= 1, "on_load 也算一次调用"
    assert panel.hint() == READY_HINT


def test_hint_reports_manifest_problems(isolated):
    root, manager = isolated
    (root / "broken").mkdir()
    (root / "broken" / "plugin.json").write_text("{ 坏的", encoding="utf-8")
    panel = PluginsPanel(manager)
    panel.refresh()

    assert "有问题" in panel.hint()
    assert "broken" in panel.hint()


def test_selected_maps_row_to_id(isolated):
    root, manager = isolated
    write_plugin(root, "first", OK_PLUGIN)
    write_plugin(root, "second", OK_PLUGIN)
    panel = PluginsPanel(manager)
    panel.refresh()

    assert panel.selected(0) == "first"
    assert panel.selected(1) == "second"
    assert panel.selected(-1) is None
    assert panel.selected(99) is None


def test_toggle_without_selection(isolated):
    panel = PluginsPanel()

    assert panel.toggle(None) == ("warning", "先在表里选中一个插件")


def test_toggle_disables_then_enables(isolated):
    root, manager = isolated
    write_plugin(root, "alpha", OK_PLUGIN)
    manager.load_all()
    panel = PluginsPanel(manager)

    level, message = panel.toggle("alpha")
    assert level == "success" and "停用" in message
    assert manager.infos["alpha"].manifest.enabled is False
    assert "alpha" in stlibs.Config.plugins["disabled"]

    level, message = panel.toggle("alpha")
    assert level == "success" and "启用" in message
    assert manager.infos["alpha"].manifest.enabled is True
    assert stlibs.Config.plugins["disabled"] == []


def test_toggle_unknown_plugin(isolated):
    panel = PluginsPanel()

    assert panel.toggle("不存在")[0] == "error"


def test_reload_reports_success(isolated):
    root, manager = isolated
    write_plugin(root, "alpha", OK_PLUGIN)
    manager.load_all()
    panel = PluginsPanel(manager)

    level, message = panel.reload("alpha")

    assert level == "success"
    assert "已重载" in message


def test_reload_reports_remaining_error(isolated):
    root, manager = isolated
    write_plugin(root, "bad", "import 根本不存在的模块\n")
    manager.load_all()
    panel = PluginsPanel(manager)

    level, message = panel.reload("bad")

    assert level == "error"
    assert "仍然失败" in message


def test_reload_without_selection(isolated):
    assert PluginsPanel().reload(None) == ("warning", "先在表里选中一个插件")


def test_master_switch_off_unloads(isolated):
    root, manager = isolated
    write_plugin(root, "alpha", OK_PLUGIN)
    manager.load_all()
    panel = PluginsPanel(manager)

    level, message = panel.set_enabled(False)

    assert level == "info" and "已停用" in message
    assert stlibs.Config.plugins["enable"] is False
    assert manager.infos["alpha"].loaded is False

    level, message = panel.set_enabled(True)
    assert level == "success"
    assert manager.infos["alpha"].loaded is True


def test_open_folder_creates_and_opens(isolated, monkeypatch):
    _root, manager = isolated
    opened = []
    monkeypatch.setattr("stlibs.plugins.manager.panel._open_local", lambda path: opened.append(path) or True)
    panel = PluginsPanel(manager)

    level, message = panel.open_folder()

    assert level == "info"
    assert opened and opened[0].endswith("plugins")
    assert str(manager.directory) in message


@pytest.mark.parametrize("item,expected", [
    ({"enabled": False, "loaded": True}, "已停用"),
    ({"enabled": True, "loaded": False, "error": "ModuleNotFoundError: x"}, "加载失败：ModuleNotFoundError: x"),
    ({"enabled": True, "loaded": True, "error": "RuntimeError: 钩子炸了"}, "运行出错：RuntimeError: 钩子炸了"),
    ({"enabled": True, "loaded": True, "runtime": "in-process"}, "已加载（in-process）"),
    ({"enabled": True, "loaded": False}, "未加载"),
])
def test_state_text(item, expected):
    assert state_text(item) == expected


def test_state_text_truncates_long_error():
    text = state_text({"enabled": True, "loaded": False, "error": "x" * 200})

    assert len(text) <= len("加载失败：") + 60
