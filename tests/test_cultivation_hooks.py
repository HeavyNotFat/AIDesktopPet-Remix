import importlib.util
import sys
from pathlib import Path

import pytest

PLUGIN_DIR = Path(__file__).resolve().parents[1] / "plugins" / "cultivation_system"
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

MODULE_NAME = "adp_plugin_cultivation_system_test"


class FakeAPI:
    """够用的 PluginAPI 替身。"""
    def __init__(self, settings=None, storage=None):
        self.name = "养成系统"
        self.id = "cultivation_system"
        self.storage = dict(storage or {})
        self.settings = dict(settings or {})
        self.menu_items = []
        self.commands = {}
        self.prompts = []
        self.notices = []
        self.logs = []
        self.ui_calls = []

    def log(self, message):
        self.logs.append(str(message))

    def notify(self, text, level="info", timeout=2600):
        self.notices.append((level, str(text)))

    def add_menu_item(self, label, action=None):
        self.menu_items.append((label, action or label))
        return action

    def register_command(self, name, help_text=""):
        self.commands[name] = help_text
        return name

    def append_system_prompt(self, text):
        self.prompts.append(text)
        return text

    def storage_get(self, key, default=None):
        return self.storage.get(key, default)

    def storage_set(self, key, value):
        self.storage[key] = value
        return value

    def get_setting(self, key, default=None):
        return self.settings.get(key, default)

    def run_on_ui(self, func, *args, **kwargs):
        self.ui_calls.append(getattr(func, "__name__", str(func)))
        return None


def load_plugin_module():
    """按插件加载器的方式导入 main.py（模块名唯一，避免和别的插件撞）。"""
    spec = importlib.util.spec_from_file_location(MODULE_NAME, PLUGIN_DIR / "main.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def plugin():
    module = load_plugin_module()
    # 模块级状态要清干净，否则用例之间互相影响
    module._state = None
    module._window = None
    module._timer = None
    yield module
    module._state = None
    module._window = None
    module._timer = None


def start(plugin, settings=None, storage=None):
    """装好一个插件实例，返回 (api, plugin)。"""
    api = FakeAPI(settings=settings, storage=storage)
    plugin.on_load(api)
    return api


def command(plugin, api, name, args=""):
    return plugin.on_command(api, {"name": name, "args": args, "text": f"/{name} {args}".strip()})


# 加载
def test_on_load_registers_menu_and_commands(plugin):
    api = start(plugin)

    labels = [label for label, _action in api.menu_items]
    assert any("打开面板" in label for label in labels)
    assert set(api.commands) >= {"养成", "状态", "喂食", "买"}
    assert api.ui_calls == ["_start_timer"], "定时器要丢回 UI 线程"


def test_on_load_restores_saved_state(plugin):
    api = start(plugin, storage={"state": {"coin": 777, "level": {"level": 3, "current": 5, "next": 500}}})

    assert plugin._state.coin == 777
    assert plugin._state.level["level"] == 3
    assert api.logs, "加载完成要留一条日志"


def test_on_load_starts_from_defaults(plugin):
    start(plugin)

    assert plugin._state.coin == 0
    assert plugin._state.hungry["hungry"] == 60


# 命令
def test_status_command_reports_everything(plugin):
    api = start(plugin)

    text = command(plugin, api, "状态")

    assert "金币" in text
    assert "背包" in text
    assert "商店" in text


def test_buy_then_feed_through_commands(plugin):
    api = start(plugin, storage={"state": {"coin": 200}})

    bought = command(plugin, api, "买", "汉堡")
    assert "已放进背包" in bought

    fed = command(plugin, api, "喂食", "汉堡")
    assert "好吃" in fed
    assert plugin._state.bag() == {}


def test_buy_without_coin_tells_the_gap(plugin):
    api = start(plugin)

    text = command(plugin, api, "买", "烤鱼")

    assert "金币不足" in text
    assert "850" in text


def test_buy_without_argument_lists_shop(plugin):
    api = start(plugin)

    text = command(plugin, api, "买")

    assert "要买什么" in text
    assert "汉堡" in text


def test_feed_without_argument_lists_bag(plugin):
    api = start(plugin)

    text = command(plugin, api, "喂食")

    assert "要喂什么" in text


def test_unknown_command_returns_none(plugin):
    api = start(plugin)

    assert command(plugin, api, "不相干的命令") is None


def test_open_panel_without_ui_explains_itself(plugin, monkeypatch):
    monkeypatch.setattr("PySide6.QtWidgets.QApplication.instance", staticmethod(lambda: None))
    api = start(plugin)

    text = command(plugin, api, "cultivation_system:open")

    assert "界面环境" in text
    assert plugin._window is None


# 奖励
def test_pet_click_gives_coin(plugin):
    api = start(plugin)

    plugin.on_event(api, {"name": "pet_click"})

    assert plugin._state.coin >= 1
    assert any("金币" in text for _level, text in api.notices)


def test_pet_click_respects_coin_cap(plugin):
    api = start(plugin, settings={"click_coin": 1})

    for _ in range(10):
        plugin.on_event(api, {"name": "pet_click"})

    assert plugin._state.coin <= 10, "每次最多 1 枚"


def test_other_events_are_ignored(plugin):
    api = start(plugin)
    stats = dict(api.storage)

    plugin.on_event(api, {"name": "chat_finished"})
    plugin.on_event(api, None)

    assert api.storage == stats


def test_chat_reply_grants_exp(plugin):
    api = start(plugin)

    plugin.on_chat_reply(api, {"text": "这是一段挺长的回答。" * 10})

    state = plugin._state
    assert state.level["current"] > 0 or state.level["level"] > 1
    assert state.state["replies"] == 1
    assert any("奖励" in item for item in api.logs)


def test_chat_reply_notifies_on_level_up(plugin):
    api = start(plugin)

    # 4200 字：经验 105（≥100 升级）、好感 210（≥100 好感升级）
    plugin.on_chat_reply(api, {"text": "字" * 4200})

    assert plugin._state.level["level"] > 1
    assert plugin._state.favor["favorability"] >= 1


# 心情提示词与卸载
def test_system_prompt_reflects_hunger(plugin):
    api = start(plugin)
    plugin._state.hungry["hungry"] = 3

    assert "饿" in plugin.on_system_prompt(api)


def test_system_prompt_can_be_disabled(plugin):
    api = start(plugin, settings={"mood_prompt": False})
    plugin._state.hungry["hungry"] = 0

    assert plugin.on_system_prompt(api) is None


def test_system_prompt_before_load_is_none(plugin):
    """还没加载过就别塞提示词（None = 不加）。"""
    api = FakeAPI()

    assert plugin.on_system_prompt(api) is None


def test_unload_cleans_up(plugin):
    api = start(plugin)

    plugin.on_unload(api)

    assert plugin._window is None
    assert plugin._timer is None
    assert plugin._state is not None, "存档还在，下次加载接着用"


def test_state_is_persisted_to_storage(plugin):
    api = start(plugin)

    plugin.on_event(api, {"name": "pet_click"})

    assert api.storage["state"]["coin"] == plugin._state.coin
