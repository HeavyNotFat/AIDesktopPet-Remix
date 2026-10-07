import os

import pytest

import stlibs

pytestmark = pytest.mark.ui

QtWidgets = pytest.importorskip("PySide6.QtWidgets", reason="设置页测试需要 PySide6")


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    """把落盘目标挪到临时目录、模型表清空，别动仓库里的 configure.json。"""
    monkeypatch.setattr(stlibs, "CONFIG_PATH", str(tmp_path / "configure.json"))
    monkeypatch.setattr(stlibs.Config, "models", {}, raising=False)
    monkeypatch.setattr(stlibs.Config, "coop", {
        "enable": False,
        "mode": "review",
        "rounds": 1,
        "agents": [],
    }, raising=False)
    yield stlibs.Config


@pytest.fixture
def notify_spy(monkeypatch):
    calls = []

    def fake(text, level="info", timeout=2600):
        calls.append((level, text))

    # llm.py 是 from ... import notify，补丁要打在它自己的命名空间上
    monkeypatch.setattr("stlibs.themes.hacker.llm.notify", fake)
    return calls


@pytest.fixture
def themed(qapp, monkeypatch):
    """装上主题，让 stlibs.notify 真的走 Notify 组件。"""
    from stlibs.themes import hacker

    monkeypatch.setattr(stlibs.SharingData, "theme", hacker)
    return hacker


def test_notify_uses_theme_widget(themed):
    from stlibs.themes.hacker import HackerNotify

    widget = stlibs.notify("测试提示", "success")
    assert isinstance(widget, HackerNotify)
    widget.dismiss()


@pytest.fixture
def notify_host(qapp, monkeypatch):
    """一个"像窗口的"宿主，让提示贴进窗口而不是浮在屏幕上。"""
    from stlibs.themes.hacker import HackerNotify

    for item in list(HackerNotify._stack):
        item.hide()
    HackerNotify._stack.clear()

    window = QtWidgets.QFrame()
    window.resize(800, 600)
    window.show()
    monkeypatch.setattr(stlibs.SharingData, "setting_window", window)
    yield window
    window.hide()


def test_notify_attaches_inside_window(notify_host):
    from stlibs.themes.hacker import HackerNotify

    note = HackerNotify("已添加 API 模型", "success")

    assert note.parent() is notify_host, "有窗口时要贴进窗口里"
    assert note._window_mode is False
    assert note.width() >= HackerNotify.MIN_WIDTH
    assert note.y() <= HackerNotify.TOP + 2, "要贴在窗口顶部"
    assert abs(note.x() + note.width() // 2 - notify_host.width() // 2) <= 2, "应该水平居中"

    note.dismiss()


def test_notify_stacks_inside_window(notify_host):
    from stlibs.themes.hacker import HackerNotify

    first = HackerNotify("第一条", "info")
    second = HackerNotify("第二条", "error")

    assert second.y() > first.y(), "第二条要叠在第一条下面"
    assert second.width() >= HackerNotify.MIN_WIDTH

    first.dismiss()
    second.dismiss()


def test_notify_floats_when_no_window(qapp, monkeypatch):
    from stlibs.themes.hacker import HackerNotify

    for item in list(HackerNotify._stack):
        item.hide()
    HackerNotify._stack.clear()

    monkeypatch.setattr(stlibs.SharingData, "setting_window", None)
    monkeypatch.setattr(stlibs.SharingData, "chat_window", None)
    monkeypatch.setattr(stlibs.SharingData, "mainloop_ui", None)

    note = HackerNotify("没有窗口时的浮层", "warning")

    assert note._window_mode is True
    assert note.parent() is None
    note.dismiss()


def test_notify_levels_have_their_own_color():
    from stlibs.themes.hacker import HackerNotify

    assert set(HackerNotify.LEVELS) == {"info", "success", "warning", "error"}
    colors = {level: value[1] for level, value in HackerNotify.LEVELS.items()}
    assert len(set(colors.values())) == 4, "每个级别要有自己的颜色"
    assert all(glyph for _bg, _color, glyph in HackerNotify.LEVELS.values())


def test_notify_falls_back_to_print_when_theme_missing(monkeypatch, capsys):
    monkeypatch.setattr(stlibs.SharingData, "theme", None)
    assert stlibs.notify("没有主题", "info") is None
    assert "没有主题" in capsys.readouterr().out


def test_notify_survives_broken_theme(monkeypatch, capsys):
    class Broken:
        @staticmethod
        def Notify(*_args, **_kwargs):
            raise RuntimeError("炸了")

    monkeypatch.setattr(stlibs.SharingData, "theme", Broken)
    assert stlibs.notify("主题坏了", "error") is None
    assert "主题坏了" in capsys.readouterr().out


def _cooperation_page(qapp, config):
    from stlibs.themes.hacker.llm import Cooperation

    return Cooperation(None)


def test_cooperation_page_loads_existing_agents(qapp, isolated_config):
    isolated_config.coop.update({
        "agents": [{"model": "a", "name": "小A", "prompt": "评审"}],
    })
    page = _cooperation_page(qapp, isolated_config)

    assert page.agent_table.rowCount() == 1
    assert page.agent_table.item(0, 0).text() == "a"
    assert page.agent_table.item(0, 2).text() == "评审"
    assert page.enable_switch.isChecked() is False


def test_cooperation_toggle_writes_config(qapp, isolated_config, notify_spy):
    page = _cooperation_page(qapp, isolated_config)
    page.enable_switch.setChecked(True)

    assert isolated_config.coop["enable"] is True
    assert notify_spy[-1][0] == "success"
    assert "开启" in notify_spy[-1][1]


def test_cooperation_add_and_remove_rows(qapp, isolated_config, notify_spy):
    page = _cooperation_page(qapp, isolated_config)

    page.add_agent()
    assert page.agent_table.rowCount() == 1
    assert isolated_config.coop["agents"] == [{"model": "", "name": "", "prompt": ""}]

    page.agent_table.item(0, 0).setText("glm4:latest")
    assert isolated_config.coop["agents"][0]["model"] == "glm4:latest"

    page.agent_table.selectRow(0)
    page.remove_agent()
    assert page.agent_table.rowCount() == 0
    assert isolated_config.coop["agents"] == []
    assert "已删除" in notify_spy[-1][1]


def test_cooperation_remove_without_selection_is_safe(qapp, isolated_config, notify_spy):
    page = _cooperation_page(qapp, isolated_config)
    page.agent_table.setCurrentCell(-1, -1)
    page.remove_agent()
    assert notify_spy[-1][0] == "warning"


def test_cooperation_save_reports_unknown_models(qapp, isolated_config, notify_spy, monkeypatch):
    monkeypatch.setattr("stlibs.themes.hacker.llm.get_model_lists", lambda: [])
    page = _cooperation_page(qapp, isolated_config)
    page.add_agent()
    page.agent_table.item(0, 0).setText("不存在的模型")

    page.save_agents()

    assert isolated_config.coop["agents"][0]["model"] == "不存在的模型"
    assert notify_spy[-1][0] == "warning"
    assert "不存在" in notify_spy[-1][1]


def test_cooperation_save_without_model_is_skipped(qapp, isolated_config, notify_spy, monkeypatch):
    monkeypatch.setattr("stlibs.themes.hacker.llm.get_model_lists", lambda: [])
    page = _cooperation_page(qapp, isolated_config)
    page.add_agent()

    page.save_agents()

    assert isolated_config.coop["agents"] == []
    assert notify_spy[-1][0] == "warning"
    assert "没有配置任何模型" in notify_spy[-1][1]


def test_cooperation_mode_and_rounds(qapp, isolated_config, notify_spy):
    page = _cooperation_page(qapp, isolated_config)

    page.mode_combo.setCurrentIndex(1)
    assert isolated_config.coop["mode"] == "parallel"
    assert "并行汇总" in notify_spy[-1][1]

    page.rounds_slider.setValue(3)
    assert isolated_config.coop["rounds"] == 3


def test_cooperation_refresh_lists_available_models(qapp, isolated_config, monkeypatch):
    monkeypatch.setattr("stlibs.themes.hacker.llm.get_model_lists", lambda: ["本地模型"])
    isolated_config.models.update({"云端": {"name": "m", "apikey": "k", "baseurl": "u"}})
    page = _cooperation_page(qapp, isolated_config)

    page.refresh()

    hint = page.available_label.text()
    assert "云端" in hint and "本地模型" in hint


def _basic_page(qapp):
    from stlibs.themes.hacker.llm import BasicWidgetScroll

    return BasicWidgetScroll(None)


def test_add_llm_rejects_missing_fields(qapp, isolated_config, notify_spy):
    page = _basic_page(qapp)
    page.add_llm()
    assert isolated_config.models == {}
    assert notify_spy[-1][0] == "error"
    assert "名字" in notify_spy[-1][1]

    page.ai_name.setText("新模型")
    page.add_llm()
    assert "模型名" in notify_spy[-1][1]

    page.ai_model.setText("deepseek-chat")
    page.add_llm()
    assert "Base URL" in notify_spy[-1][1]
    assert isolated_config.models == {}


def test_add_llm_rejects_duplicate(qapp, isolated_config, notify_spy):
    isolated_config.models["已有的"] = {"name": "m", "apikey": "k", "baseurl": "u"}
    page = _basic_page(qapp)
    page.ai_name.setText("已有的")
    page.ai_model.setText("m")
    page.api_url.setText("https://example.com")

    page.add_llm()

    assert notify_spy[-1][0] == "error"
    assert "已经存在" in notify_spy[-1][1]
    assert isolated_config.models["已有的"]["name"] == "m"


def test_add_llm_success_saves_and_refreshes(qapp, isolated_config, notify_spy, monkeypatch):
    refreshed = []
    monkeypatch.setattr("stlibs.themes.hacker.llm.refresh_models", lambda select=None: refreshed.append(select))

    page = _basic_page(qapp)
    page.ai_name.setText("DeepseekV4")
    page.ai_model.setText("deepseek-chat")
    page.api_url.setText("https://api.deepseek.com")
    page.api_key.setText("sk-test")

    page.add_llm()

    assert isolated_config.models["DeepseekV4"] == {
        "name": "deepseek-chat",
        "apikey": "sk-test",
        "baseurl": "https://api.deepseek.com",
    }
    assert refreshed == ["DeepseekV4"]
    assert notify_spy[-1][0] == "success"
    assert "已添加" in notify_spy[-1][1]
    # 输入框要清空，避免手快点两下又加一遍
    assert page.ai_name.text() == ""
    assert page.selected_alias() == "DeepseekV4"
    assert "deepseek-chat" in page.existing.currentText(), "下拉里带上模型名，删之前能看清删的是哪个"


def test_add_llm_without_key_uses_placeholder(qapp, isolated_config, notify_spy, monkeypatch):
    monkeypatch.setattr("stlibs.themes.hacker.llm.refresh_models", lambda select=None: None)
    page = _basic_page(qapp)
    page.ai_name.setText("本地网关")
    page.ai_model.setText("qwen")
    page.api_url.setText("http://127.0.0.1:8000/v1")

    page.add_llm()

    assert isolated_config.models["本地网关"]["apikey"] == "not-needed"
    assert "not-needed" in notify_spy[-1][1]


def test_remove_llm_drops_config(qapp, isolated_config, notify_spy, monkeypatch):
    monkeypatch.setattr("stlibs.themes.hacker.llm.refresh_models", lambda select=None: None)
    isolated_config.models["要删的"] = {"name": "m", "apikey": "k", "baseurl": "u"}
    page = _basic_page(qapp)
    page.reload_existing()
    assert page.select_existing("要删的") is True

    page.remove_llm()

    assert "要删的" not in isolated_config.models
    assert notify_spy[-1][0] == "success"
    assert "已删除" in notify_spy[-1][1]
    assert page.existing.count() == 0
    assert page.remove_button.isEnabled() is False, "没东西可删时按钮要灰掉"


def test_remove_llm_without_selection_is_safe(qapp, isolated_config, notify_spy):
    page = _basic_page(qapp)
    page.remove_llm()
    assert notify_spy[-1][0] == "warning"


def test_delete_row_is_not_squeezed(qapp, isolated_config):
    """删除这一行以前是竖排，被 HackerCard 压到 30px 高，两个控件都变形。"""
    isolated_config.models["甲"] = {"name": "m", "apikey": "k", "baseurl": "u"}
    page = _basic_page(qapp)
    page.resize(700, 520)
    page.show()

    combo = page.existing.geometry()
    button = page.remove_button.geometry()

    assert combo.width() >= 300, "下拉框太窄了"
    assert combo.height() >= 28, "下拉框被压扁了"
    assert button.width() >= 90
    assert 28 <= button.height() <= 44, "按钮被压扁或拉长了"
    assert abs(combo.center().y() - button.center().y()) <= 4, "两者应该在同一行"
    assert combo.right() < button.left(), "按钮应该在下拉框右边"
    page.hide()


def test_real_chat_window_picks_up_new_model(qapp, monkeypatch, isolated_config):
    """用真主题窗口跑一遍：新增配置后左侧列表要立刻多出一项，且不重复叠加。"""
    import importlib
    import sys

    from stlibs.themes import hacker

    monkeypatch.setattr(stlibs.SharingData, "theme", hacker)
    monkeypatch.setattr(stlibs.Config, "mcp", {"enable": False, "mcp": []}, raising=False)
    monkeypatch.setattr(stlibs.Config, "rag", {"enable": False}, raising=False)
    sys.modules.pop("stlibs.graphics.chat", None)
    chat_module = importlib.import_module("stlibs.graphics.chat")
    monkeypatch.setattr(chat_module, "get_model_lists", lambda: [])

    isolated_config.models["甲"] = {"name": "m1", "apikey": "k", "baseurl": "u"}
    chat = chat_module.Chat()
    assert set(chat.model_widgets) == {"甲"}

    isolated_config.models["乙"] = {"name": "m2", "apikey": "k", "baseurl": "u"}
    names = chat.reload_models("乙")

    assert set(names) == {"甲", "乙"}
    assert chat.pages.count() == 2, "页面数应该跟着模型数走"
    assert len(chat.categories) == 2, "分类头（本地/API）不能越刷越多"
    assert chat.nav_widgets[chat.model_widgets["乙"].windowTitle()] is chat.model_widgets["乙"]

    chat.close()
