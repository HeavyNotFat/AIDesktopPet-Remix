import json
import textwrap
from pathlib import Path

import pytest

import stlibs
from stlibs.plugins.errors import PluginError
from stlibs.plugins.pages import (
    MAX_COLUMNS,
    MAX_NESTED_ROWS,
    MAX_ROWS,
    PLUGIN_CATEGORY,
    PluginPages,
    make_row,
    normalize_form,
    rows_from_manifest,
)

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


@pytest.fixture
def manager(tmp_path, monkeypatch):
    """干净的管理器：插件目录与配置都关在 tmp 里。"""
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
    """拦下提示条：返回值里的文本会走 stlibs.notify。"""
    calls = []
    monkeypatch.setattr(stlibs, "notify", lambda text, level="info", timeout=2600: calls.append(text))
    return calls


def write_plugin(root, plugin_id, code, **manifest):
    directory = Path(root) / plugin_id
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "main.py").write_text(textwrap.dedent(code), encoding="utf-8")
    data = {"id": plugin_id, "name": f"插件 {plugin_id}", "language": "python", "entry": "main.py"}
    data.update(manifest)
    (directory / "plugin.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return directory


def test_form_rows_are_normalized():
    rows = normalize_form([
        {"type": "text", "key": "suffix", "label": "后缀", "default": "喵"},
        {"type": "number", "key": "times", "min": 1, "max": 9, "default": "3"},
        {"type": "select", "key": "mode", "options": ["a", ("b", "乙"), {"value": "c", "label": "丙"}]},
        {"type": "switch", "key": "on", "default": 0},
        {"type": "button", "action": "reset", "label": "重置"},
        {"type": "hint", "text": "改完立刻生效"},
    ])

    assert [row.type for row in rows] == ["text", "number", "select", "switch", "button", "hint"]
    assert rows[0].default == "喵"
    assert rows[1].default == 3 and rows[1].minimum == 1 and rows[1].maximum == 9
    assert [item["value"] for item in rows[2].options] == ["a", "b", "c"]
    assert [item["label"] for item in rows[2].options] == ["a", "乙", "丙"]
    assert rows[3].default is False
    assert rows[4].action == "reset"


def test_bad_rows_are_skipped_and_unknown_types_ignored():
    assert make_row("不是字典") is None
    assert make_row({"type": "视频", "key": "x"}) is None
    assert make_row({"type": "text"}) is None, "值类型的行必须有 key"
    assert make_row({"type": "button"}) is None, "按钮行必须有 action 或 key"
    assert make_row({"type": "label"}) is None, "文字行必须有 text"

    rows = normalize_form([{"type": "nope"}, {"type": "text", "key": "ok", "label": "好"}])
    assert [row.key for row in rows] == ["ok"]


def test_section_is_a_grid_with_columns_and_span():
    rows = normalize_form([
        {"type": "section", "title": "连接", "columns": 2, "hint": "两列", "rows": [
            {"type": "text", "key": "server", "label": "服务器", "span": 2},
            {"type": "number", "key": "threads", "label": "线程"},
            {"type": "button", "action": "ping", "text": "测试"},
        ]},
    ])

    assert [row.type for row in rows] == ["section"]
    section = rows[0]
    assert section.title == "连接" and section.hint == "两列"
    assert section.columns == 2
    assert [child.key or child.action for child in section.rows] == ["server", "threads", "ping"]
    assert section.rows[0].span == 2 and section.rows[1].span == 1


def test_section_limits_and_nesting():
    rows = normalize_form([
        {"type": "section", "title": "夹回来", "columns": 99, "rows": [
            {"type": "text", "key": "a", "span": 42},
        ]},
        {"type": "section", "title": "嵌套", "rows": [
            {"type": "section", "title": "里层不许", "rows": [{"type": "text", "key": "b"}]},
            {"type": "text", "key": "c"},
        ]},
        {"type": "section", "title": "空块", "rows": []},
        {"type": "section", "title": "全是坏行", "rows": [{"type": "text"}]},
    ])

    assert [row.type for row in rows] == ["section", "section"]
    assert rows[0].columns == MAX_COLUMNS
    assert rows[0].rows[0].span == MAX_COLUMNS
    assert [child.key for child in rows[1].rows] == ["c"], "嵌套的 section 要被丢掉"

    capped = normalize_form([{"type": "section", "title": "太多", "rows": [
        {"type": "text", "key": f"k{index}"} for index in range(MAX_NESTED_ROWS + 10)
    ]}])
    assert len(capped[0].rows) == MAX_NESTED_ROWS


def test_map_row_accepts_three_shapes():
    rows = normalize_form([
        {"type": "map", "title": "状态一", "items": {"素材站": "https://a.example", "账号": None}},
        {"type": "map", "title": "状态二", "items": [["线程", 4], ["开关", True]]},
        {"type": "map", "title": "状态三", "items": [{"key": "进度", "value": "3 / 10"}]},
        {"type": "map", "title": "空的", "items": {}},
        {"type": "map", "title": "只有空键", "items": {"": 1}},
    ])

    assert [row.type for row in rows] == ["map", "map", "map"]
    assert [item["key"] for item in rows[0].items] == ["素材站", "账号"]
    assert rows[0].items[0]["value"] == "https://a.example"
    assert rows[1].items[0]["value"] == 4 and rows[1].items[1]["value"] is True
    assert rows[2].items[0]["key"] == "进度"


def test_public_shape_carries_sections_and_maps():
    rows = normalize_form([
        {"type": "section", "title": "块", "columns": 2, "rows": [
            {"type": "text", "key": "server", "span": 2},
        ]},
        {"type": "map", "title": "表", "items": {"账号": "alice"}},
    ])

    payload = [row.public() for row in rows]
    assert payload[0]["columns"] == 2
    assert payload[0]["rows"][0]["key"] == "server"
    assert payload[0]["rows"][0]["span"] == 2
    assert payload[1]["items"] == [{"key": "账号", "value": "alice"}]



def test_form_must_be_a_list():
    with pytest.raises(PluginError):
        normalize_form({"type": "text", "key": "a"})


def test_rows_are_capped():
    rows = normalize_form([{"type": "text", "key": f"k{index}"} for index in range(MAX_ROWS + 20)])
    assert len(rows) == MAX_ROWS


def test_rows_from_manifest_settings():
    rows = rows_from_manifest([
        {"key": "suffix", "label": "后缀", "type": "text", "default": "喵"},
        {"key": "count", "label": "次数", "type": "number", "default": 3},
        {"key": "loud", "label": "大声", "type": "switch", "default": False},
        {"key": "bad", "label": "怪类型", "type": "视频", "default": 1},
    ])

    assert [row.type for row in rows] == ["text", "number", "switch", "text"]
    assert rows[2].default is False


def test_plugin_registers_page(manager):
    write_plugin(manager.directory, "alpha", PAGE_PLUGIN)
    manager.load_all()

    pages = manager.pages.pages("alpha")
    assert len(pages) == 1
    assert pages[0].title == "养猫设置"
    assert pages[0].key == "养猫设置"
    assert [row.key for row in pages[0].rows] == ["suffix", "noisy"]

    reported = manager.settings_pages()
    assert reported[0]["plugin"] == "alpha"
    assert reported[0]["form"][0]["label"] == "后缀"
    assert manager.status()["pages"] == reported


def test_page_key_is_replaced_not_duplicated(manager):
    write_plugin(manager.directory, "alpha", '''
        def on_load(api):
            api.add_settings_page("设置", form=[{"type": "text", "key": "a"}], key="main")
            api.add_settings_page("设置（改过）", form=[{"type": "text", "key": "b"}], key="main")
    ''')
    manager.load_all()

    pages = manager.pages.pages("alpha")
    assert len(pages) == 1
    assert pages[0].title == "设置（改过）"
    assert pages[0].generation == 1, "覆盖注册要换 generation，界面才会重建"
    assert [row.key for row in pages[0].rows] == ["b"]


def test_pages_sorted_by_plugin_order(manager):
    write_plugin(manager.directory, "late", '''
        def on_load(api):
            api.add_settings_page("晚", form=[{"type": "text", "key": "a"}])
    ''', order=200)
    write_plugin(manager.directory, "early", '''
        def on_load(api):
            api.add_settings_page("早", form=[{"type": "text", "key": "a"}])
    ''', order=10)
    manager.load_all()

    assert [spec.plugin for spec in manager.pages.pages()] == ["early", "late"]


def test_pages_are_removed_with_the_plugin(manager):
    write_plugin(manager.directory, "alpha", PAGE_PLUGIN)
    manager.load_all()
    assert manager.pages.pages()

    manager.unload("alpha")
    assert manager.pages.pages() == []

    manager.load("alpha")
    assert len(manager.pages.pages()) == 1


def test_reload_rebuilds_pages(manager):
    write_plugin(manager.directory, "alpha", PAGE_PLUGIN)
    manager.load_all()
    before = manager.pages.pages()[0].generation

    manager.reload("alpha")

    specs = manager.pages.pages()
    assert len(specs) == 1
    assert specs[0].generation >= before, "重载后页面没有被摘掉又加回来"


def test_plugin_can_remove_and_refresh_pages(manager):
    write_plugin(manager.directory, "alpha", '''
        def on_load(api):
            api.register_command("r")
            api.register_command("drop")
            api.add_settings_page("一", form=[{"type": "text", "key": "a"}], key="one")
            api.add_settings_page("二", form=[{"type": "text", "key": "b"}], key="two")

        def on_command(api, ctx):
            if ctx["name"] == "drop":
                return str(api.remove_settings_page("one"))
            return str(api.refresh_settings_page("two"))
    ''')
    manager.load_all()
    assert {spec.key for spec in manager.pages.pages()} == {"one", "two"}

    generation = manager.pages.find("alpha", "two").generation
    assert manager.run_command("/r") == (True, "1")
    assert manager.pages.find("alpha", "two").generation == generation + 1

    assert manager.run_command("/drop") == (True, "1")
    assert {spec.key for spec in manager.pages.pages()} == {"two"}


def test_manifest_settings_become_the_page(manager):
    write_plugin(manager.directory, "alpha", '''
        def on_load(api):
            api.add_settings_page("插件设置")
    ''', settings=[
        {"key": "suffix", "label": "后缀", "type": "text", "default": "喵"},
    ])
    manager.load_all()

    pages = manager.pages.pages("alpha")
    assert [row.key for row in pages[0].rows] == ["suffix"]


def test_page_without_content_is_an_error(manager, said):
    write_plugin(manager.directory, "alpha", '''
        def on_load(api):
            api.add_settings_page("空页")
    ''')
    manager.load_all()
    info = manager.infos["alpha"]

    assert "form" in info.error and "settings" in info.error
    assert manager.pages.pages() == []


def test_settings_action_persists_and_dispatches(manager, said):
    write_plugin(manager.directory, "alpha", PAGE_PLUGIN)
    manager.load_all()

    result = manager.settings_action("alpha", "养猫设置", "suffix", "汪", key="suffix")

    assert result == "收到 suffix"
    assert stlibs.Config.plugins["settings"]["alpha"]["suffix"] == "汪"
    assert manager._apis["alpha"].storage_get("last")["value"] == "汪"
    assert said and "收到" in said[-1]


def test_settings_action_without_key_does_not_touch_config(manager, said):
    write_plugin(manager.directory, "alpha", PAGE_PLUGIN)
    manager.load_all()

    manager.settings_action("alpha", "养猫设置", "refresh", None, key=None)

    assert manager._apis["alpha"].storage_get("last")["action"] == "refresh"
    assert stlibs.Config.plugins["settings"].get("alpha") is None


def test_javascript_style_call(manager):
    """JS 桥走 PluginAPI.call，参数是 JSON 里过来的纯数据。"""
    write_plugin(manager.directory, "alpha", PAGE_PLUGIN)
    manager.load_all()
    plugin_api = manager._apis["alpha"]

    form = json.loads(json.dumps([
        {"type": "select", "key": "mode", "label": "模式", "options": [{"value": "a", "label": "甲"}]},
    ]))
    key = plugin_api.call("add_settings_page", "JS 页面", form, None, "js-page", 5)

    assert key == "js-page"
    spec = manager.pages.find("alpha", "js-page")
    assert spec.order == 5 and spec.rows[0].options[0]["label"] == "甲"

    assert {item["key"] for item in plugin_api.call("settings_pages")} == {"养猫设置", "js-page"}
    assert plugin_api.call("refresh_settings_page", "js-page") == 1
    assert plugin_api.call("remove_settings_page", "js-page") == 1
    assert manager.pages.find("alpha", "js-page") is None


def test_builder_must_be_callable(manager):
    pages = PluginPages(manager)
    with pytest.raises(PluginError):
        pages.add("alpha", "页面", form=[{"type": "text", "key": "a"}], builder="不是函数")


def test_empty_title_is_rejected(manager):
    pages = PluginPages(manager)
    with pytest.raises(PluginError):
        pages.add("alpha", "   ", form=[{"type": "text", "key": "a"}])


def test_listener_gets_notified_on_change(manager):
    seen = []
    manager.pages.bind(lambda rebuild: seen.append(rebuild))

    write_plugin(manager.directory, "alpha", PAGE_PLUGIN)
    manager.load_all()

    assert seen, "注册页面要通知监听者"
    assert seen[-1] is True


def test_dead_listener_is_dropped(manager):
    class Window:
        def on_change(self, rebuild):
            raise AssertionError("这个监听者已经被回收了")

    window = Window()
    manager.pages.bind(window.on_change)
    del window

    write_plugin(manager.directory, "alpha", PAGE_PLUGIN)
    manager.load_all()

    assert manager.pages._listeners == []


def test_category_constant_is_shared():
    assert PLUGIN_CATEGORY == "插件"
