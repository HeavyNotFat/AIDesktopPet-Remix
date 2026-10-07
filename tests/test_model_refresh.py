import importlib
import sys

import pytest

import stlibs
from stlibs.mproc.onlinechat.registry import ModelRegistry


class FakeModelChat:
    def __init__(self, ai_name, model, is_local, api_key=None, base_url=None, parent=None):
        self.ai_name = ai_name
        self.model = model
        self.is_local = is_local
        self.deleted = False

    def windowTitle(self):
        return self.ai_name

    def deleteLater(self):
        self.deleted = True


class FakeWindow:
    def __init__(self, parent=None):
        self.nav = []
        self.categories = {}
        self.active = None

    def addNavigation(self, text, widget, shortcut_keys=None, position="top", category=None):
        self.nav.append((category, text, widget))
        # 跟真主题一样：第一个页面自动激活
        if len(self.nav) == 1:
            self._set_active(widget)

    def removeNavigation(self, widget):
        self.nav = [item for item in self.nav if item[2] is not widget]

    def create_category(self, category, position="top"):
        self.categories[category] = category
        return category

    def remove_category(self, category):
        return self.categories.pop(category, None) is not None

    def setTitle(self, title):
        self.title = title

    def _set_active(self, widget):
        self.active = widget


class FakeTheme:
    Window = FakeWindow
    ModelChat = FakeModelChat


@pytest.fixture
def chat_module(monkeypatch):
    # chat.py 在导入期就继承 SharingData.theme.Window，所以先装假主题再导入
    monkeypatch.setattr(stlibs.SharingData, "theme", FakeTheme)
    monkeypatch.setattr(stlibs.Config, "models", {"旧的": {"name": "m", "apikey": "k", "baseurl": "u"}})
    sys.modules.pop("stlibs.graphics.chat", None)
    module = importlib.import_module("stlibs.graphics.chat")
    monkeypatch.setattr(module, "get_model_lists", lambda: ["glm4:latest"])
    return module


def test_chat_lists_local_and_api_models(chat_module):
    chat = chat_module.Chat()

    assert set(chat.model_widgets) == {"glm4:latest", "旧的"}
    assert [item[1] for item in chat.nav] == ["glm4:latest", "旧的"]


def test_reload_models_picks_up_new_api_model(chat_module):
    chat = chat_module.Chat()
    stlibs.Config.models["新的"] = {"name": "m2", "apikey": "k", "baseurl": "u"}

    names = chat.reload_models("新的")

    assert set(names) == {"glm4:latest", "旧的", "新的"}
    assert len(chat.nav) == 3, "旧条目要先摘掉，不能越刷越多"
    assert chat.active is chat.model_widgets["新的"], "刚添加的模型应该自动选中"


def test_reload_models_without_select_activates_a_live_model(chat_module):
    chat = chat_module.Chat()
    chat.reload_models("旧的")
    stale = chat.model_widgets["旧的"]

    chat.reload_models()

    assert chat.active is not stale, "刷新后不能还停在已经删掉的页面上"
    assert chat.active in chat.model_widgets.values()


def test_reload_models_drops_removed_model(chat_module):
    chat = chat_module.Chat()
    stlibs.Config.models.pop("旧的")

    names = chat.reload_models()

    assert names == ["glm4:latest"]
    assert "旧的" not in chat.model_widgets


def test_refresh_models_touches_window_and_web_registry(monkeypatch):
    from stlibs.mproc.onlinechat import registry as registry_module

    calls = []

    class Window:
        def reload_models(self, select=None):
            calls.append(select)

    invalidated = []
    monkeypatch.setattr(stlibs.SharingData, "chat_window", Window())
    monkeypatch.setattr(registry_module.registry, "invalidate", lambda: invalidated.append(True))

    stlibs.refresh_models("新模型")

    assert calls == ["新模型"]
    assert invalidated == [True]


def test_refresh_models_is_safe_without_window(monkeypatch):
    monkeypatch.setattr(stlibs.SharingData, "chat_window", None)
    stlibs.refresh_models()


def test_registry_invalidate_forces_rescan():
    data = {"a": {"value": "a", "label": "a", "backend": "local", "model": "a"}}
    registry = ModelRegistry(ttl=3600, provider=lambda: dict(data))
    assert list(registry.snapshot()) == ["a"]

    data["b"] = {"value": "b", "label": "b", "backend": "local", "model": "b"}
    assert list(registry.snapshot()) == ["a"], "TTL 内不该重新扫描"

    registry.invalidate()
    assert list(registry.snapshot()) == ["a", "b"]


def test_refresh_coop_reconfigures_live_instances(monkeypatch):
    class Coop:
        def __init__(self):
            self.reconfigured = 0

        def reconfigure(self):
            self.reconfigured += 1

    class Instance:
        coop_disabled = False

        def __init__(self, coop):
            self.coop = coop

    kept = Coop()
    live = Instance(kept)
    agent = Instance(None)
    agent.coop_disabled = True
    fresh = Instance(None)

    monkeypatch.setattr(stlibs.SharingData, "llm_instances", type(stlibs.SharingData.llm_instances)())
    stlibs.SharingData.llm_instances["a"] = live
    stlibs.SharingData.llm_instances["b"] = agent
    stlibs.SharingData.llm_instances["c"] = fresh

    stlibs.refresh_coop()

    assert kept.reconfigured == 1
    assert agent.coop is None, "协作成员不能再套一层协作"
    assert fresh.coop is not None, "协作后来才打开时也要给已有实例补上"
