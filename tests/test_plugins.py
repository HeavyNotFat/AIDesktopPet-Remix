import json
import shutil
import textwrap

import pytest

import stlibs
from stlibs.plugins import PluginManager, manifest as manifest_module
from stlibs.plugins.api import (
    CHAT_REPLY,
    CHAT_SEND,
    COMMAND,
    EVENT,
    ON_LOAD,
    SYSTEM_PROMPT,
)
from stlibs.plugins.manager.js_plugin import find_node

NODE = find_node()
needs_node = pytest.mark.skipif(NODE is None, reason="需要 node 才能跑 JavaScript 插件")


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    """别把测试插件的开关写进仓库里的 configure.json。"""
    monkeypatch.setattr(stlibs, "CONFIG_PATH", str(tmp_path / "configure.json"))
    monkeypatch.setattr(stlibs.Config, "plugins", {
        "enable": True, "directory": str(tmp_path / "plugins"),
        "disabled": [], "settings": {}, "timeout": 3.0,
    }, raising=False)
    return stlibs.Config


def write_plugin(root, plugin_id, main_code, language="python", **manifest_extra):
    directory = root / plugin_id
    directory.mkdir(parents=True, exist_ok=True)
    entry = "main.py" if language == "python" else "main.js"
    (directory / entry).write_text(textwrap.dedent(main_code), encoding="utf-8")
    payload = {
        "id": plugin_id,
        "name": manifest_extra.pop("name", plugin_id),
        "language": language,
        "entry": entry,
    }
    payload.update(manifest_extra)
    (directory / "plugin.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return directory


@pytest.fixture
def plugins_root(tmp_path):
    root = tmp_path / "plugins"
    root.mkdir()
    return root


def make_manager(root) -> PluginManager:
    manager = PluginManager(directory=str(root))
    manager.discover()
    return manager


PY_SIMPLE = '''
    def on_load(api):
        api.log("loaded")
        api.add_menu_item("打个招呼", "greet")
        api.register_command("hello", "打招呼")
        api.append_system_prompt("说人话。")
    def on_chat_reply(api, ctx):
        return ctx["text"] + " [py]"
    def on_chat_send(api, ctx):
        return ctx["text"].replace("坏词", "***")
    def on_command(api, ctx):
        if ctx["name"] == "greet":
            api.notify("你好")
            return "打个招呼"
        if ctx["name"] == "hello":
            return f"hi {ctx['args']}"
        return None
'''


# 清单
def test_discover_finds_plugins(plugins_root):
    write_plugin(plugins_root, "alpha", PY_SIMPLE)
    write_plugin(plugins_root, "beta", PY_SIMPLE)

    manager = make_manager(plugins_root)

    assert sorted(info.id for info in manager.infos.values()) == ["alpha", "beta"]
    assert manager.problems == []


def test_discover_reports_broken_manifest(plugins_root):
    (plugins_root / "broken").mkdir()
    (plugins_root / "broken" / "plugin.json").write_text("{ 这不是 JSON", encoding="utf-8")
    write_plugin(plugins_root, "good", PY_SIMPLE)

    manager = make_manager(plugins_root)

    assert [info.id for info in manager.infos.values()] == ["good"]
    assert len(manager.problems) == 1
    assert "读不了" in manager.problems[0]["error"]


def test_missing_entry_is_a_problem(plugins_root):
    directory = plugins_root / "noentry"
    directory.mkdir()
    (directory / "plugin.json").write_text(json.dumps({"id": "noentry", "language": "python"}), encoding="utf-8")

    manager = make_manager(plugins_root)

    assert manager.infos == {}
    assert "找不到入口文件" in manager.problems[0]["error"]


def test_unsupported_language_is_a_problem(plugins_root):
    directory = plugins_root / "rust"
    directory.mkdir()
    (directory / "plugin.json").write_text(json.dumps({"id": "rust", "language": "rust"}), encoding="utf-8")

    manager = make_manager(plugins_root)

    assert "不支持的语言" in manager.problems[0]["error"]


def test_manifest_rejects_path_escape(plugins_root):
    directory = plugins_root / "escape"
    directory.mkdir()
    (directory / "plugin.json").write_text(
        json.dumps({"id": "escape", "language": "python", "entry": "../main.py"}), encoding="utf-8"
    )

    manager = make_manager(plugins_root)

    assert "相对路径" in manager.problems[0]["error"]


def test_duplicate_ids_are_reported(plugins_root, tmp_path):
    write_plugin(plugins_root, "first", PY_SIMPLE, name="A")
    write_plugin(plugins_root, "second", PY_SIMPLE, id="first")

    manager = make_manager(plugins_root)

    assert len(manager.infos) == 1
    assert any("重复" in item["error"] for item in manager.problems)


def test_dot_and_underscore_dirs_are_skipped(plugins_root):
    (plugins_root / ".data").mkdir()
    (plugins_root / "_template").mkdir()
    write_plugin(plugins_root, "real", PY_SIMPLE)

    manager = make_manager(plugins_root)

    assert [info.id for info in manager.infos.values()] == ["real"]


def test_manifest_parses_settings(plugins_root):
    write_plugin(plugins_root, "cfg", PY_SIMPLE, settings=[
        {"key": "suffix", "label": "后缀", "type": "text", "default": "喵"},
        {"key": "bad", "label": "坏类型", "type": "什么鬼", "default": 1},
        {"label": "没有 key"},
    ])

    manager = make_manager(plugins_root)
    settings = manager.infos["cfg"].manifest.settings

    assert [item["key"] for item in settings] == ["suffix", "bad"]
    assert settings[1]["type"] == "text", "不认识的类型退回 text"


# Python 插件
def test_python_plugin_loads_and_registers(plugins_root):
    write_plugin(plugins_root, "alpha", PY_SIMPLE)
    manager = make_manager(plugins_root)

    manager.load_all()
    info = manager.infos["alpha"]

    assert info.loaded is True
    assert info.error == ""
    assert info.runtime == "in-process"
    assert [item.label for item in manager.menu_items()] == ["打个招呼"]
    assert "hello" in manager.commands()
    assert manager.system_prompts() == ["说人话。"]


def test_hooks_receive_api_and_payload(plugins_root):
    write_plugin(plugins_root, "alpha", PY_SIMPLE)
    manager = make_manager(plugins_root)
    manager.load_all()

    assert manager.chat_text("你好", "assistant") == "你好 [py]"
    assert manager.chat_text("这是坏词内容", "user") == "这是***内容"


def test_hooks_without_arguments_are_supported(plugins_root):
    write_plugin(plugins_root, "plain", '''
        called = []
        def on_load():
            called.append("load")
        def on_system_prompt():
            return "无参数也能用"
    ''')
    manager = make_manager(plugins_root)

    manager.load_all()

    assert manager.infos["plain"].error == ""
    assert manager.system_prompts() == ["无参数也能用"]


def test_plugin_class_is_supported(plugins_root):
    write_plugin(plugins_root, "classy", '''
        class Plugin:
            def __init__(self):
                self.count = 0
            def on_load(self, api):
                api.register_command("count")
            def on_command(self, api, ctx):
                self.count += 1
                return f"第 {self.count} 次"
    ''')
    manager = make_manager(plugins_root)
    manager.load_all()

    assert manager.run_command("/count") == (True, "第 1 次")
    assert manager.run_command("/count") == (True, "第 2 次")


def test_broken_plugin_only_breaks_itself(plugins_root):
    write_plugin(plugins_root, "boom", 'def on_load(api):\n    raise RuntimeError("我就是坏的")\n')
    write_plugin(plugins_root, "fine", PY_SIMPLE)
    manager = make_manager(plugins_root)

    manager.load_all()

    assert "我就是坏的" in manager.infos["boom"].error
    assert manager.infos["fine"].loaded is True
    assert manager.chat_text("你好", "assistant") == "你好 [py]"


def test_import_error_is_reported(plugins_root):
    write_plugin(plugins_root, "noimport", "import 根本不存在的模块\n")
    manager = make_manager(plugins_root)

    manager.load_all()

    info = manager.infos["noimport"]
    assert info.loaded is False
    assert "ModuleNotFoundError" in info.error


def test_hook_exception_is_isolated(plugins_root):
    write_plugin(plugins_root, "thrower", '''
        def on_chat_reply(api, ctx):
            raise ValueError("回复钩子炸了")
    ''')
    manager = make_manager(plugins_root)
    manager.load_all()

    assert manager.chat_text("原文", "assistant") == "原文", "钩子炸了要保留原文"
    assert "回复钩子炸了" in manager.infos["thrower"].error


def test_hook_returning_none_keeps_text(plugins_root):
    write_plugin(plugins_root, "noop", '''
        def on_chat_reply(api, ctx):
            return None
    ''')
    manager = make_manager(plugins_root)
    manager.load_all()

    assert manager.chat_text("原文", "assistant") == "原文"


def test_plugin_can_import_sibling_module(plugins_root):
    directory = write_plugin(plugins_root, "sibling", '''
        from helper import greeting
        def on_command(api, ctx):
            return greeting()
    ''')
    (directory / "helper.py").write_text('def greeting():\n    return "来自同目录模块"\n', encoding="utf-8")

    manager = make_manager(plugins_root)
    manager.load_all()

    assert manager.run_command("/whatever") == (False, "")
    assert manager.infos["sibling"].error == ""


def test_storage_round_trip(plugins_root):
    write_plugin(plugins_root, "store", '''
        def on_load(api):
            api.register_command("store")
            api.storage_set("count", int(api.storage_get("count", 0)) + 1)
        def on_command(api, ctx):
            return str(api.storage_get("count", 0))
    ''')
    manager = make_manager(plugins_root)
    manager.load_all()
    manager.load("store")  # 第二次加载不该重复计数（已经 loaded 就直接返回）

    assert manager.run_command("/store") == (True, "1")
    saved = json.loads((plugins_root / ".data" / "store.json").read_text(encoding="utf-8"))
    assert saved == {"count": 1}


def test_settings_defaults_and_persistence(plugins_root):
    write_plugin(plugins_root, "cfg", '''
        def on_chat_reply(api, ctx):
            return ctx["text"] + str(api.get_setting("suffix", "?"))
    ''', settings=[{"key": "suffix", "type": "text", "default": "喵"}])
    manager = make_manager(plugins_root)
    manager.load_all()

    assert manager.chat_text("你好", "assistant") == "你好喵"

    manager.set_setting("cfg", "suffix", "汪")
    assert manager.chat_text("你好", "assistant") == "你好汪"
    assert stlibs.Config.plugins["settings"]["cfg"]["suffix"] == "汪"


def test_enable_disable_and_persist(plugins_root):
    write_plugin(plugins_root, "alpha", PY_SIMPLE)
    manager = make_manager(plugins_root)
    manager.load_all()

    manager.set_enabled("alpha", False)
    assert manager.infos["alpha"].manifest.enabled is False
    assert "alpha" in stlibs.Config.plugins["disabled"]
    assert manager.system_prompts() == [], "停用后不该再出现它的提示词"

    manager.set_enabled("alpha", True)
    assert "alpha" not in stlibs.Config.plugins["disabled"]
    assert manager.system_prompts() == ["说人话。"]


def test_master_switch_stops_loading(plugins_root):
    write_plugin(plugins_root, "alpha", PY_SIMPLE)
    stlibs.Config.plugins["enable"] = False
    manager = make_manager(plugins_root)

    assert manager.load_all() == []
    assert manager.infos["alpha"].loaded is False


def test_unload_calls_on_unload(plugins_root):
    write_plugin(plugins_root, "alpha", '''
        def on_load(api):
            api.storage_set("unloaded", False)
        def on_unload(api):
            api.storage_set("unloaded", True)
    ''')
    manager = make_manager(plugins_root)
    manager.load_all()

    assert manager.unload("alpha") is True

    saved = json.loads((plugins_root / ".data" / "alpha.json").read_text(encoding="utf-8"))
    assert saved["unloaded"] is True


def test_reload_picks_up_edits(plugins_root):
    directory = write_plugin(plugins_root, "alpha", PY_SIMPLE)
    manager = make_manager(plugins_root)
    manager.load_all()
    assert manager.chat_text("x", "assistant") == "x [py]"

    (directory / "main.py").write_text(
        textwrap.dedent('def on_chat_reply(api, ctx):\n    return ctx["text"] + " [v2]"\n'), encoding="utf-8"
    )
    manager.reload("alpha")

    assert manager.chat_text("x", "assistant") == "x [v2]"


def test_events_are_dispatched(plugins_root):
    write_plugin(plugins_root, "watcher", '''
        def on_event(api, ctx):
            api.storage_set("last", ctx["name"])
    ''')
    manager = make_manager(plugins_root)
    manager.load_all()

    manager.emit_event("theme_changed", {"theme": "hacker"})

    saved = json.loads((plugins_root / ".data" / "watcher.json").read_text(encoding="utf-8"))
    assert saved["last"] == "theme_changed"


def test_removed_plugin_disappears_from_status(plugins_root):
    directory = write_plugin(plugins_root, "alpha", PY_SIMPLE)
    manager = make_manager(plugins_root)
    manager.load_all()

    shutil.rmtree(directory)
    manager.discover()

    assert manager.infos == {}


# JavaScript 插件
JS_SIMPLE = '''
    let calls = 0;
    module.exports = {
      on_load(api) {
        api.log('js loaded');
        api.addMenuItem('JS 菜单', 'js:menu');
        api.registerCommand('jshello', 'JS 打招呼');
        api.storageSet('loads', Number(api.storageGet('loads', 0)) + 1);
      },
      on_chat_reply(api, ctx) {
        calls += 1;
        return ctx.text + ' [js]';
      },
      on_command(api, ctx) {
        if (ctx.name === 'js:menu') {
          api.notify('JS 收到菜单点击', 'success');
          return 'JS 菜单被点了';
        }
        if (ctx.name === 'jshello') {
          return 'JS 累计加载 ' + api.storageGet('loads', 0) + ' 次';
        }
        return null;
      }
    };
'''


@needs_node
def test_javascript_plugin_loads(plugins_root):
    write_plugin(plugins_root, "jsplug", JS_SIMPLE, language="javascript")
    manager = make_manager(plugins_root)

    manager.load_all()
    info = manager.infos["jsplug"]

    assert info.loaded is True, info.error
    assert info.error == ""
    assert info.runtime.startswith("node(")
    assert manager.chat_text("你好", "assistant") == "你好 [js]"
    assert [item.label for item in manager.menu_items()] == ["JS 菜单"]
    assert "jshello" in manager.commands()


@needs_node
def test_javascript_api_round_trip(plugins_root):
    write_plugin(plugins_root, "jsstore", '''
        module.exports = {
          on_load(api) {
            api.registerCommand('n');
            api.storageSet('n', Number(api.storageGet('n', 0)) + 1);
          },
          on_command(api, ctx) { return 'n=' + api.storageGet('n', 0); }
        };
    ''', language="javascript")
    manager = make_manager(plugins_root)
    manager.load_all()

    assert manager.run_command("/n") == (True, "n=1")
    saved = json.loads((plugins_root / ".data" / "jsstore.json").read_text(encoding="utf-8"))
    assert saved == {"n": 1}


@needs_node
def test_javascript_menu_click(plugins_root):
    write_plugin(plugins_root, "jsplug", JS_SIMPLE, language="javascript")
    manager = make_manager(plugins_root)
    manager.load_all()

    assert manager.trigger_menu("js:menu") == "JS 菜单被点了"


@needs_node
def test_javascript_syntax_error_is_reported(plugins_root):
    write_plugin(plugins_root, "jsbad", "module.exports = { 这不是 JS", language="javascript")
    manager = make_manager(plugins_root)

    manager.load_all()

    info = manager.infos["jsbad"]
    assert info.loaded is False
    assert "加载失败" in info.error


@needs_node
def test_javascript_hook_exception_is_isolated(plugins_root):
    write_plugin(plugins_root, "jsthrow", '''
        module.exports = {
          on_chat_reply(api, ctx) { throw new Error('js 钩子炸了'); }
        };
    ''', language="javascript")
    manager = make_manager(plugins_root)
    manager.load_all()

    assert manager.chat_text("原文", "assistant") == "原文"
    assert "js 钩子炸了" in manager.infos["jsthrow"].error


@needs_node
def test_javascript_missing_hook_is_fine(plugins_root):
    write_plugin(plugins_root, "jsonly", '''
        module.exports = { on_load(api) { api.log('只有 on_load'); } };
    ''', language="javascript")
    manager = make_manager(plugins_root)
    manager.load_all()

    assert manager.infos["jsonly"].loaded is True
    assert manager.chat_text("原文", "assistant") == "原文"
    assert manager.system_prompts() == []


@needs_node
def test_javascript_timeout_is_reported(plugins_root):
    write_plugin(plugins_root, "jsslow", '''
        module.exports = {
          on_load(api) {
            const until = Date.now() + 4000;
            while (Date.now() < until) { /* 死循环式的慢 */ }
          }
        };
    ''', language="javascript")

    manager = PluginManager(directory=str(plugins_root), timeout=0.5)
    manager.discover()
    manager.load_all()

    info = manager.infos["jsslow"]
    assert info.error, "超时要有错误记录"
    assert "没响应" in info.error or "超时" in info.error


@needs_node
def test_javascript_unload_kills_process(plugins_root):
    write_plugin(plugins_root, "jsplug", JS_SIMPLE, language="javascript")
    manager = make_manager(plugins_root)
    manager.load_all()

    assert manager.unload("jsplug") is True

    table = manager._hooks.get("jsplug")
    assert table is None
    assert manager.infos["jsplug"].loaded is False


def test_node_missing_is_reported(plugins_root, monkeypatch):
    write_plugin(plugins_root, "jsplug", JS_SIMPLE, language="javascript")
    monkeypatch.setattr("stlibs.plugins.manager.js_plugin.find_node", lambda: None)

    manager = make_manager(plugins_root)
    manager.load_all()

    info = manager.infos["jsplug"]
    assert info.loaded is False
    assert "node" in info.error


def test_mixed_languages_together(plugins_root):
    # order 小的先加工（清单里的 order 字段）
    write_plugin(plugins_root, "second", '''
        def on_chat_reply(api, ctx):
            return ctx["text"] + " [py]"
    ''', order=20)
    write_plugin(plugins_root, "first", '''
        module.exports = { on_chat_reply(api, ctx) { return ctx.text + " [js]"; } };
    ''', language="javascript", order=10)
    manager = make_manager(plugins_root)

    manager.load_all()
    text = manager.chat_text("原文", "assistant")

    if NODE is None:
        assert text == "原文 [py]", "没有 node 时 JS 插件不参与"
    else:
        assert text == "原文 [js] [py]", "按 order 依次加工"


def test_plugins_run_in_order(plugins_root):
    write_plugin(plugins_root, "later", '''
        def on_chat_reply(api, ctx):
            return ctx["text"] + "B"
    ''', order=50)
    write_plugin(plugins_root, "earlier", '''
        def on_chat_reply(api, ctx):
            return ctx["text"] + "A"
    ''', order=1)
    manager = make_manager(plugins_root)
    manager.load_all()

    assert manager.chat_text("", "assistant") == "AB"


# 状态与配置
def test_status_shape(plugins_root):
    write_plugin(plugins_root, "alpha", PY_SIMPLE)
    manager = make_manager(plugins_root)
    manager.load_all()

    status = manager.status()

    assert status["enable"] is True
    assert status["plugins"][0]["id"] == "alpha"
    assert status["plugins"][0]["loaded"] is True
    assert "commands" in status
    json.dumps(status, ensure_ascii=False)


def test_directory_comes_from_config(plugins_root):
    stlibs.Config.plugins["directory"] = str(plugins_root)
    write_plugin(plugins_root, "alpha", PY_SIMPLE)

    manager = stlibs.plugin_manager()

    assert manager.directory == str(plugins_root)
    assert [info.id for info in manager.discover()] == ["alpha"]


def test_plugin_prompts_helper_never_raises(monkeypatch):
    monkeypatch.setattr(stlibs, "plugin_manager", lambda: (_ for _ in ()).throw(RuntimeError("坏了")))

    assert stlibs.plugin_prompts() == []
    assert stlibs.run_plugin_command("/x") == (False, "")


# 菜单分组（右键菜单每个插件一层子菜单）
MENU_TWO = '''
    def on_load(api):
        api.add_menu_item("第一项", "one")
        api.add_menu_item("第二项", "two")
'''


def test_menu_groups_split_by_plugin(plugins_root):
    write_plugin(plugins_root, "alpha", MENU_TWO, name="甲插件", order=10)
    write_plugin(plugins_root, "beta", 'def on_load(api):\n    api.add_menu_item("乙项", "bee")\n',
                 name="乙插件", order=20)
    manager = make_manager(plugins_root)
    manager.load_all()

    groups = manager.menu_groups()

    assert [(group.plugin, group.title) for group in groups] == [("alpha", "甲插件"), ("beta", "乙插件")]
    assert [len(group) for group in groups] == [2, 1]
    assert groups[0].items[0].label == "第一项"
    assert groups[0].items[0].plugin == "alpha"
    assert groups[0].public()["items"][0]["action"] == "one"


def test_menu_group_title_comes_from_manifest_menu(plugins_root):
    write_plugin(plugins_root, "alpha", MENU_TWO, name="甲插件", menu="甲组")
    manager = make_manager(plugins_root)
    manager.load_all()

    assert manager.menu_groups()[0].title == "甲组"
    assert manager.menu_title("alpha") == "甲组"


def test_menu_items_stays_flat_for_old_callers(plugins_root):
    """老接口（SDK / 探针 / 这些测试）拿到的还是扁平列表。"""
    write_plugin(plugins_root, "alpha", MENU_TWO)
    write_plugin(plugins_root, "beta", 'def on_load(api):\n    api.add_menu_item("乙项", "bee")\n')
    manager = make_manager(plugins_root)
    manager.load_all()

    flat = manager.menu_items()

    assert [item.label for item in flat] == ["第一项", "第二项", "乙项"]
    assert [item.plugin for item in flat] == ["alpha", "alpha", "beta"]


def test_menu_groups_skip_disabled_plugins(plugins_root):
    write_plugin(plugins_root, "alpha", MENU_TWO)
    write_plugin(plugins_root, "beta", 'def on_load(api):\n    api.add_menu_item("乙项", "bee")\n')
    manager = make_manager(plugins_root)
    manager.load_all()

    manager.set_enabled("alpha", False)

    assert [group.plugin for group in manager.menu_groups()] == ["beta"]


def test_menu_groups_empty_without_plugins(plugins_root):
    manager = make_manager(plugins_root)

    assert manager.menu_groups() == []
    assert manager.menu_items() == []


def test_menu_groups_do_not_need_qt(plugins_root):
    """纯逻辑调用（SDK、测试）不该因为造不出图标而报错。"""
    write_plugin(plugins_root, "alpha", MENU_TWO, icon="icon.png")
    manager = make_manager(plugins_root)
    manager.load_all()

    groups = manager.menu_groups()

    assert len(groups) == 1
    assert groups[0].title == "alpha"


@needs_node
def test_javascript_plugin_adds_settings_page(plugins_root):
    """JS 插件走 node 桥注册设置页：表单按 JSON 传，动作回调也回到插件里。"""
    write_plugin(plugins_root, "jspage", '''
        module.exports = {
          on_load(api) {
            api.addSettingsPage('JS 设置', [
              {type: 'switch', key: 'loud', label: '大声', default: true},
              {type: 'button', action: 'ping', label: '打个招呼'}
            ], 'js-page', 10);
          },
          on_settings_action(api, ctx) {
            if (ctx.action === 'ping') return 'pong';
            return '改了 ' + ctx.key;
          }
        };
    ''', language="javascript")
    manager = make_manager(plugins_root)
    manager.load_all()

    spec = manager.pages.find("jspage", "js-page")
    assert spec is not None, "JS 插件没把页面注册进来"
    assert spec.order == 10
    assert [(row.type, row.key) for row in spec.rows] == [("switch", "loud"), ("button", "")]

    assert manager.settings_action("jspage", "js-page", "ping") == "pong"

    assert manager.settings_action("jspage", "js-page", "loud", False, key="loud") == "改了 loud"
    assert stlibs.Config.plugins["settings"]["jspage"]["loud"] is False

    manager.unload("jspage")
    assert manager.pages.pages("jspage") == []
