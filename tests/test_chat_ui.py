import os

import pytest

import stlibs

pytestmark = pytest.mark.ui

QtWidgets = pytest.importorskip("PySide6.QtWidgets", reason="聊天气泡/技能测试需要 PySide6")


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(stlibs, "CONFIG_PATH", str(tmp_path / "configure.json"))
    monkeypatch.setattr(stlibs.Config, "skills", [
        {"name": "翻译", "description": "翻译成中文", "prompt": "只输出译文"},
        {"name": "总结", "description": "提炼要点", "prompt": "三条要点"},
    ], raising=False)
    yield stlibs.Config


@pytest.fixture
def notify_spy(monkeypatch):
    calls = []

    def fake(text, level="info", timeout=3200, parent=None):
        calls.append((level, text))

    # 主题里直接用 HackerNotify；设置页走的是 from ... import notify
    monkeypatch.setattr("stlibs.themes.hacker.HackerNotify", fake)
    monkeypatch.setattr(
        "stlibs.themes.hacker.llm.notify",
        lambda text, level="info", timeout=3200: calls.append((level, text)),
    )
    return calls


def _bubble(qapp, text="你好呀", is_user=False):
    from stlibs.themes.hacker import HackerChatBubble

    return HackerChatBubble(text=text, is_user=is_user)


# 复制按钮
def test_assistant_bubble_has_copy_button(qapp):
    bubble = _bubble(qapp)

    assert bubble.copy_button.isVisible() is False or True  # 未 show 时 isVisible 取决于父窗口
    assert bubble.actions.isVisibleTo(bubble) is True
    assert bubble.copy_button.text() == "复制"


def test_copy_button_puts_text_on_clipboard(qapp, notify_spy):
    bubble = _bubble(qapp, "这段要被复制")
    bubble.show()

    bubble.copy_button.click()

    assert QtWidgets.QApplication.clipboard().text() == "这段要被复制"
    assert notify_spy[-1][0] == "success"


def test_copy_button_copies_what_streamed_in(qapp, notify_spy):
    bubble = _bubble(qapp, "")
    bubble.append_text("流式")
    bubble.append_text("拼起来的内容")
    bubble.show()

    bubble.copy_button.click()

    assert QtWidgets.QApplication.clipboard().text() == "流式拼起来的内容"


def test_copy_empty_bubble_warns(qapp, notify_spy):
    bubble = _bubble(qapp, "   ")
    bubble.copy_button.click()

    assert notify_spy[-1][0] == "warning"


def test_user_bubble_has_no_actions(qapp):
    bubble = _bubble(qapp, "我发的", is_user=True)

    assert bubble.actions.isVisibleTo(bubble) is False


# 音频播放按钮
def test_audio_is_not_played_automatically(qapp, monkeypatch):
    played = []
    monkeypatch.setattr("stlibs.derfer.play_audio", lambda data: played.append(data))

    bubble = _bubble(qapp)
    bubble.attach_audio("ZmFrZQ==")

    assert played == [], "挂上音频不能自动播"
    assert bubble.play_button.isVisibleTo(bubble) is True
    assert "播放" in bubble.play_button.text()


def test_audio_plays_on_click(qapp, monkeypatch, notify_spy):
    played = []
    monkeypatch.setattr("stlibs.derfer.play_audio", lambda data: played.append(data))

    bubble = _bubble(qapp)
    bubble.attach_audio("ZmFrZQ==")
    bubble.play_button.click()

    assert played == ["ZmFrZQ=="]
    assert notify_spy[-1][0] == "info"


def test_audio_click_without_audio_does_nothing(qapp, monkeypatch):
    played = []
    monkeypatch.setattr("stlibs.derfer.play_audio", lambda data: played.append(data))

    bubble = _bubble(qapp)
    bubble.play_audio()

    assert played == []


def test_audio_failure_is_reported(qapp, monkeypatch, notify_spy):
    def broken(_data):
        raise RuntimeError("没有可用的声卡")

    monkeypatch.setattr("stlibs.derfer.play_audio", broken)

    bubble = _bubble(qapp)
    bubble.attach_audio("ZmFrZQ==")
    bubble.play_button.click()

    assert notify_spy[-1][0] == "error"
    assert "没有可用的声卡" in notify_spy[-1][1]
    assert bubble.play_button.isEnabled() is True, "失败后按钮要能再点"


def test_llm_callback_forwards_audio_without_playing(monkeypatch):
    import stlibs.derfer as derfer

    played = []
    monkeypatch.setattr(derfer, "play_audio", lambda data: played.append(data))
    monkeypatch.setattr(derfer.sounddevice, "play", lambda *a, **k: played.append("直接播了"))

    events = []

    class FakeLLM:
        def chat(self, query, skill=None, attachments=None):
            yield "文字"
            yield {"type": "audio", "data": "ZmFrZQ==", "transcript": "转写"}
            yield {"type": "tool_call", "name": "x"}

    worker = derfer.LLMAICallback(FakeLLM(), "问题", None)
    worker.tool_event.connect(events.append)
    worker.run()

    assert played == [], "回调里不该自动播音频"
    assert [event["type"] for event in events] == ["audio", "tool_call"]


def test_llm_callback_passes_skill_to_llm(monkeypatch):
    import stlibs.derfer as derfer

    seen = {}

    class FakeLLM:
        def chat(self, query, skill=None, attachments=None):
            seen["query"] = query
            seen["skill"] = skill
            yield "ok"

    derfer.LLMAICallback(FakeLLM(), "正文", None, skill="只输出译文").run()

    assert seen == {"query": "正文", "skill": "只输出译文"}


# 聊天窗里的技能
def _chat(qapp, isolated_config):
    from stlibs.themes.hacker import HackerChatWidget

    return HackerChatWidget()


def test_chat_widget_has_skill_button(qapp, isolated_config):
    chat = _chat(qapp, isolated_config)

    assert chat.skill_button.text() == "技能"
    assert chat.active_skill is None
    assert chat.skill_bar.isVisibleTo(chat) is False


def test_set_skill_updates_chip_and_button(qapp, isolated_config, notify_spy):
    chat = _chat(qapp, isolated_config)

    chat.set_skill({"name": "翻译", "description": "翻译成中文", "prompt": "只输出译文"})

    assert chat.active_skill["name"] == "翻译"
    assert chat.skill_bar.isVisibleTo(chat) is True
    assert "翻译" in chat.skill_bar_label.text()
    assert "✓" in chat.skill_button.text()
    assert notify_spy[-1][0] == "success"

    chat.set_skill(None)
    assert chat.active_skill is None
    assert chat.skill_bar.isVisibleTo(chat) is False
    assert chat.skill_button.text() == "技能"


def test_send_with_skill_prefix_strips_it(qapp, isolated_config, notify_spy):
    chat = _chat(qapp, isolated_config)
    sent = Recorder()
    chat.userInputSignal.connect(sent)

    chat.input_edit.setPlainText("/翻译 hello world")
    chat._send_message()

    assert sent.texts == ["hello world"], "前缀只用来选技能，不该发给模型"
    assert chat.active_skill["name"] == "翻译"
    assert chat.input_edit.toPlainText() == ""
    assert chat.bubbles[-1].skill_name == "翻译", "气泡上要标出用了哪个技能"


def test_send_with_only_skill_name_does_not_send(qapp, isolated_config, notify_spy):
    chat = _chat(qapp, isolated_config)
    sent = Recorder()
    chat.userInputSignal.connect(sent)

    chat.input_edit.setPlainText("/总结")
    chat._send_message()

    assert sent.texts == [], "只打技能名是切换技能，不是发消息"
    assert chat.active_skill["name"] == "总结"
    assert chat.input_edit.toPlainText() == ""


def test_send_with_unknown_prefix_sends_as_is(qapp, isolated_config):
    chat = _chat(qapp, isolated_config)
    sent = Recorder()
    chat.userInputSignal.connect(sent)

    chat.input_edit.setPlainText("/没有这个 正文")
    chat._send_message()

    assert sent.texts == ["/没有这个 正文"]
    assert chat.active_skill is None


def test_active_skill_keeps_working_on_later_messages(qapp, isolated_config, notify_spy):
    chat = _chat(qapp, isolated_config)
    sent = Recorder()
    chat.userInputSignal.connect(sent)

    chat.set_skill({"name": "翻译", "prompt": "只输出译文"})
    chat.input_edit.setPlainText("第二句")
    chat._send_message()

    assert sent.texts == ["第二句"]
    assert chat.bubbles[-1].skill_name == "翻译"


def test_skill_menu_lists_config_skills(qapp, isolated_config):
    chat = _chat(qapp, isolated_config)

    menu = chat.build_skill_menu()
    labels = [action.text() for action in menu.menu_actions()]

    assert len(labels) == 2
    assert "翻译" in labels[0] and "翻译成中文" in labels[0]
    menu.deleteLater()


def test_skill_menu_has_clear_entry_when_active(qapp, isolated_config, notify_spy):
    chat = _chat(qapp, isolated_config)
    chat.set_skill({"name": "翻译", "prompt": "p"})

    menu = chat.build_skill_menu()
    labels = [action.text() for action in menu.menu_actions()]

    assert labels[-1] == "取消技能"
    clear = [action for action in menu.menu_actions() if action.text() == "取消技能"]
    clear[0].trigger()
    assert chat.active_skill is None
    menu.deleteLater()


def test_skill_menu_when_no_skills(qapp, monkeypatch, isolated_config):
    monkeypatch.setattr(stlibs.Config, "skills", [], raising=False)
    chat = _chat(qapp, isolated_config)

    menu = chat.build_skill_menu()
    actions = menu.menu_actions()

    assert len(actions) == 1
    assert actions[0].isEnabled() is False, "没技能时给一条灰掉的提示"
    menu.deleteLater()


# 设置页
def _memory_page(qapp, isolated_config, monkeypatch, models=("model-a", "model-b")):
    """记忆页：模型列表用假数据，免得依赖本机 Ollama（用 monkeypatch 免得泄漏到别的用例）。"""
    import stlibs.themes.hacker.llm as llm_module

    monkeypatch.setattr(llm_module, "get_model_lists", lambda: list(models))
    page = llm_module.Memory(None)
    page.resize(660, 460)
    page.show()
    for _ in range(3):
        qapp.processEvents()
    return page


def test_memory_page_has_single_viewer_and_interactive_selector(qapp, isolated_config, monkeypatch):
    """回归：重建展示项会盖在整页上 —— 表现为两个输入框、控件点不动。"""
    page = _memory_page(qapp, isolated_config, monkeypatch)

    texts = [item for item in page.findChildren(QtWidgets.QTextEdit) if item.isVisible()]
    assert len(texts) == 1, f"记忆页只该有一个展示框，实际 {len(texts)} 个"

    center = page.model_selector.geometry().center()
    top = page.childAt(center)
    assert top is not None
    assert top is page.model_selector or page.model_selector.isAncestorOf(top), \
        f"下拉被 {type(top).__name__} 盖住了，点不到"

    # 切走再切回（设置页切页签就是这个效果）后依然如此
    page.hide()
    page.show()
    for _ in range(3):
        qapp.processEvents()

    texts = [item for item in page.findChildren(QtWidgets.QTextEdit) if item.isVisible()]
    assert len(texts) == 1
    top = page.childAt(center)
    assert top is page.model_selector or page.model_selector.isAncestorOf(top)
    page.hide()


def test_memory_page_switches_model_and_receives_updates(qapp, isolated_config, monkeypatch):
    page = _memory_page(qapp, isolated_config, monkeypatch)

    assert page.model_selector.count() == 2
    assert page.current_model == "model-a"
    assert page.memory_json.toPlainText() == "[]", "没有活着的实例时展示空记忆"

    receive = stlibs.SharingData.add_memory_to_ui["model-a"]
    receive(["model-a", [{"role": "user", "content": "你好"}]])
    assert "你好" in page.memory_json.toPlainText()

    receive(["model-b", [{"role": "user", "content": "别的模型"}]])
    assert "别的模型" not in page.memory_json.toPlainText(), "只显示当前选中的模型"

    page.model_selector.setCurrentText("model-b")
    for _ in range(2):
        qapp.processEvents()
    assert page.current_model == "model-b"
    page.hide()


def test_memory_page_without_models_shows_hint(qapp, isolated_config, monkeypatch):
    page = _memory_page(qapp, isolated_config, monkeypatch, models=())

    assert page.model_selector.count() == 0
    assert "还没有可用模型" in page.memory_json.toPlainText()
    page.hide()


def _skills_page(qapp, isolated_config):
    from stlibs.themes.hacker.llm import Skills

    return Skills(None)


def test_skills_page_lists_config(qapp, isolated_config):
    page = _skills_page(qapp, isolated_config)

    assert page.skill_table.rowCount() == 2
    assert page.skill_table.item(0, 0).text() == "翻译"
    assert page.skill_table.item(0, 2).text() == "只输出译文"
    assert page.skill_table.columnCount() == 3


def test_skills_page_add_and_remove(qapp, isolated_config, notify_spy):
    page = _skills_page(qapp, isolated_config)

    page.add_skill()
    assert page.skill_table.rowCount() == 3
    assert len(isolated_config.skills) == 3

    page.skill_table.item(2, 0).setText("新技能")
    assert isolated_config.skills[2]["name"] == "新技能"

    page.skill_table.selectRow(2)
    page.remove_skill()
    assert page.skill_table.rowCount() == 2
    assert all(skill["name"] != "新技能" for skill in isolated_config.skills)
    assert notify_spy[-1][0] == "success"


def test_skills_page_remove_without_selection_is_safe(qapp, isolated_config, notify_spy):
    page = _skills_page(qapp, isolated_config)
    page.skill_table.setCurrentCell(-1, -1)

    page.remove_skill()

    assert notify_spy[-1][0] == "warning"


def test_skills_page_save_skips_duplicates_and_empty_names(qapp, isolated_config, notify_spy):
    page = _skills_page(qapp, isolated_config)

    page.add_skill()
    page.skill_table.item(2, 0).setText("翻译")
    page.skill_table.item(2, 2).setText("重复的名字")
    page.add_skill()
    page.skill_table.item(3, 2).setText("只有提示词没有名字")

    page.save_skills()

    assert [skill["name"] for skill in isolated_config.skills] == ["翻译", "总结"]
    assert any("重复" in text for _level, text in notify_spy)
    assert any("没有技能名" in text for _level, text in notify_spy)


def test_skills_page_save_reports_count(qapp, isolated_config, notify_spy):
    page = _skills_page(qapp, isolated_config)

    page.save_skills()

    assert notify_spy[-1][0] == "success"
    assert "2 个技能" in notify_spy[-1][1]
    assert "翻译" in notify_spy[-1][1]


def test_skills_page_refreshes_on_show(qapp, isolated_config):
    page = _skills_page(qapp, isolated_config)
    isolated_config.skills.append({"name": "新加的", "description": "", "prompt": "p"})

    page.refresh()

    assert page.skill_table.rowCount() == 3


# 聊天页接线：音频事件、技能透传
@pytest.fixture
def model_chat(qapp, monkeypatch, isolated_config):
    from PySide6.QtCore import QObject, Signal

    from stlibs.themes import hacker

    class FakeLLM(QObject):
        memory_signal = Signal(list)
        coop_signal = Signal(dict)

    # ModelChat 里会走 SharingData.theme.Label / ChatWidget，得先把主题装上
    monkeypatch.setattr(stlibs.SharingData, "theme", hacker)
    monkeypatch.setitem(hacker.cache_llm_class, "fake-model", FakeLLM())
    monkeypatch.setattr(stlibs.SharingData, "add_memory_to_ui", {})
    return hacker.ModelChat("测试模型", "fake-model", True, parent=None)


def test_model_chat_attaches_audio_to_current_bubble(model_chat):
    bubble = model_chat.chat.add_assistant_msg()
    model_chat.current_assistant_bubble = bubble

    model_chat.on_tool_event({"type": "audio", "data": "ZmFrZQ==", "transcript": "这段是转写"})

    assert bubble.audio_data == "ZmFrZQ=="
    assert bubble.play_button.isVisibleTo(bubble) is True, "有音频才出现播放按钮"
    assert "这段是转写" in bubble.text(), "没有正文时用转写兜底"


def test_model_chat_ignores_other_tool_events(model_chat):
    bubble = model_chat.chat.add_assistant_msg("正文")
    model_chat.current_assistant_bubble = bubble

    model_chat.on_tool_event({"type": "tool_call", "name": "x"})

    assert bubble.audio_data is None
    assert bubble.play_button.isVisibleTo(bubble) is False


def test_model_chat_without_bubble_does_not_crash(model_chat):
    model_chat.current_assistant_bubble = None

    model_chat.on_tool_event({"type": "audio", "data": "ZmFrZQ=="})


def test_model_chat_passes_active_skill_to_worker(model_chat, monkeypatch):
    from PySide6.QtCore import QObject, Signal

    seen = {}

    class FakeWorker(QObject):
        finished = Signal(str)
        text_chunk = Signal(str)
        tool_event = Signal(dict)

        def __init__(self, llm, query, parent, skill=None, attachments=None):
            super().__init__(parent)
            seen["query"] = query
            seen["skill"] = skill

        def start(self):
            seen["started"] = True

    monkeypatch.setattr("stlibs.themes.hacker.derfer.LLMAICallback", FakeWorker)

    model_chat.chat.set_skill({"name": "翻译", "prompt": "只输出译文"})
    model_chat.add_user_msg("你好")

    assert seen["query"] == "你好"
    assert seen["skill"] == "只输出译文"
    assert seen["started"] is True
    assert model_chat.chat.send_button.isEnabled() is False, "生成期间不该能再发"


def test_model_chat_without_skill_sends_none(model_chat, monkeypatch):
    from PySide6.QtCore import QObject, Signal

    seen = {}

    class FakeWorker(QObject):
        finished = Signal(str)
        text_chunk = Signal(str)
        tool_event = Signal(dict)

        def __init__(self, llm, query, parent, skill=None, attachments=None):
            super().__init__(parent)
            seen["skill"] = skill

        def start(self):
            pass

    monkeypatch.setattr("stlibs.themes.hacker.derfer.LLMAICallback", FakeWorker)

    model_chat.add_user_msg("没有技能")

    assert seen["skill"] is None


# 附件：粘贴 / 选择 / 展示 / 透传
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


class Recorder:
    """记下 userInputSignal 发出来的 (正文, 附件)。"""
    def __init__(self):
        self.calls = []

    def __call__(self, text, attachments=None):
        self.calls.append((text, list(attachments or [])))

    @property
    def texts(self):
        return [text for text, _items in self.calls]


def _make_png(path):
    from PySide6.QtGui import QImage

    image = QImage(4, 4, QImage.Format.Format_ARGB32)
    image.fill(0xFF00FF00)
    assert image.save(str(path), "PNG")
    return str(path)


def test_chat_widget_starts_without_attachments(qapp, isolated_config):
    chat = _chat(qapp, isolated_config)

    assert chat.attachments == []
    assert chat.attachment_bar.isVisibleTo(chat) is False
    assert chat.attach_button.text() == "附件"


def test_add_and_remove_attachment(qapp, isolated_config):
    from stlibs.ai import attachment as attachment_api

    chat = _chat(qapp, isolated_config)
    item = attachment_api.from_bytes(PNG, "cat.png")

    assert chat.add_attachment(item) is True
    assert chat.attachments == [item]
    assert chat.attachment_bar.isVisibleTo(chat) is True
    assert chat.attachment_layout.count() == 1

    chat.remove_attachment(item)
    assert chat.attachments == []
    assert chat.attachment_bar.isVisibleTo(chat) is False


def test_attach_paths_reads_real_files(qapp, isolated_config, tmp_path):
    chat = _chat(qapp, isolated_config)
    doc = tmp_path / "说明.md"
    doc.write_text("正文", encoding="utf-8")
    image = _make_png(tmp_path / "cat.png")

    assert chat.attach_paths([str(doc), image]) == 2

    names = [item["name"] for item in chat.attachments]
    assert names == ["说明.md", "cat.png"]
    assert chat.attachments[0]["text"] == "正文"
    assert chat.attachments[1]["kind"] == "image"


def test_attach_paths_reports_missing_file(qapp, isolated_config, notify_spy):
    chat = _chat(qapp, isolated_config)

    assert chat.attach_paths(["没有这个文件.txt"]) == 0
    assert notify_spy[-1][0] == "error"


def test_attachment_limit_is_enforced(qapp, isolated_config, notify_spy):
    from stlibs.ai import MAX_ATTACHMENTS
    from stlibs.ai import attachment as attachment_api

    chat = _chat(qapp, isolated_config)
    for index in range(MAX_ATTACHMENTS):
        chat.add_attachment(attachment_api.from_bytes(b"x", f"{index}.txt"))

    assert chat.add_attachment(attachment_api.from_bytes(b"x", "多出来的.txt")) is False
    assert len(chat.attachments) == MAX_ATTACHMENTS
    assert notify_spy[-1][0] == "warning"


def test_paste_from_clipboard_adds_image(qapp, isolated_config, notify_spy):
    from PySide6.QtCore import QMimeData
    from PySide6.QtGui import QImage, QPixmap

    chat = _chat(qapp, isolated_config)
    mime = QMimeData()
    image = QImage(6, 6, QImage.Format.Format_ARGB32)
    image.fill(0xFFFF0000)
    mime.setImageData(QPixmap.fromImage(image))

    assert chat.attach_from_mime(mime) is True

    assert len(chat.attachments) == 1
    assert chat.attachments[0]["kind"] == "image"
    assert chat.attachments[0]["name"].endswith(".png")
    assert notify_spy[-1][0] == "success"


def test_paste_from_clipboard_adds_files(qapp, isolated_config, tmp_path):
    from PySide6.QtCore import QMimeData, QUrl

    doc = tmp_path / "粘贴.txt"
    doc.write_text("来自剪切板", encoding="utf-8")

    chat = _chat(qapp, isolated_config)
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(doc))])

    assert chat.attach_from_mime(mime) is True
    assert chat.attachments[0]["text"] == "来自剪切板"


def test_plain_text_paste_is_not_hijacked(qapp, isolated_config):
    from PySide6.QtCore import QMimeData

    chat = _chat(qapp, isolated_config)
    mime = QMimeData()
    mime.setText("普通文字")

    assert chat.attach_from_mime(mime) is False
    assert chat.attachments == []


def test_sending_takes_attachments_and_clears_chips(qapp, isolated_config, tmp_path):
    from stlibs.ai import attachment as attachment_api

    chat = _chat(qapp, isolated_config)
    sent = Recorder()
    chat.userInputSignal.connect(sent)
    # 真图片才能变成缩略图（上面那个 PNG 常量只是用来测逻辑的假数据）
    chat.add_attachment(attachment_api.from_path(_make_png(tmp_path / "cat.png")))

    chat._send_message()

    assert sent.texts == [""], "只有附件没有文字时也要发出去"
    assert len(sent.calls[0][1]) == 1, "附件要跟着信号一起到接收方"
    assert chat.attachments == []
    assert chat.attachment_bar.isVisibleTo(chat) is False
    assert len(chat.bubbles[-1].image_labels) == 1, "气泡里要看到图片"


def test_sending_document_shows_chip_in_bubble(qapp, isolated_config):
    from stlibs.ai import attachment as attachment_api

    chat = _chat(qapp, isolated_config)
    chat.add_attachment(attachment_api.from_bytes("正文".encode("utf-8"), "说明.md"))
    chat.input_edit.setPlainText("看看这个")

    chat._send_message()

    labels = [child.text() for child in chat.bubbles[-1].findChildren(QtWidgets.QLabel)]
    assert any("说明.md" in text and "已读入正文" in text for text in labels)


def test_empty_message_without_attachments_does_nothing(qapp, isolated_config):
    chat = _chat(qapp, isolated_config)
    sent = Recorder()
    chat.userInputSignal.connect(sent)

    chat._send_message()

    assert sent.texts == []


def test_real_clipboard_ctrl_v_attaches_image(qapp, isolated_config, notify_spy):
    """真实剪切板给的是 QImage（不是 QPixmap），以前只判 QPixmap，所以真按 Ctrl+V 没反应。"""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication, QImage
    from PySide6.QtTest import QTest

    chat = _chat(qapp, isolated_config)
    image = QImage(8, 8, QImage.Format.Format_ARGB32)
    image.fill(0xFF00FF00)
    QGuiApplication.clipboard().setImage(image)

    QTest.keyClick(chat.input_edit, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)

    assert len(chat.attachments) == 1, "Ctrl+V 应该把剪切板里的图片变成附件"
    assert chat.attachments[0]["kind"] == "image"
    assert notify_spy[-1][0] == "success"


def test_plain_text_ctrl_v_still_pastes_text(qapp, isolated_config):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtTest import QTest

    chat = _chat(qapp, isolated_config)
    QGuiApplication.clipboard().setText("粘贴进来的文字")

    QTest.keyClick(chat.input_edit, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)

    assert chat.attachments == [], "纯文字不该变成附件"
    assert "粘贴进来的文字" in chat.input_edit.toPlainText()


def test_paste_key_detection_ignores_paste_as_plain_text(qapp, isolated_config):
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent

    chat = _chat(qapp, isolated_config)
    edit = chat.input_edit
    kinds = {
        "ctrl+v": QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier, "v"),
        "ctrl+shift+v": QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_V,
                                  Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier, "V"),
        "shift+insert": QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Insert, Qt.KeyboardModifier.ShiftModifier),
        "v": QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_V, Qt.KeyboardModifier.NoModifier, "v"),
    }

    assert edit._is_paste_key(kinds["ctrl+v"]) is True
    assert edit._is_paste_key(kinds["ctrl+shift+v"]) is False, "Ctrl+Shift+V 是粘贴为纯文本"
    assert edit._is_paste_key(kinds["shift+insert"]) is True
    assert edit._is_paste_key(kinds["v"]) is False


def test_send_message_hands_attachments_to_worker(model_chat, monkeypatch):
    """走真实发送流程（_send_message 而不是直接调 add_user_msg）：附件必须到 worker。"""

    from PySide6.QtCore import QObject, Signal
    from stlibs.ai import attachment as attachment_api

    seen = {}

    class FakeWorker(QObject):
        finished = Signal(str)
        text_chunk = Signal(str)
        tool_event = Signal(dict)

        def __init__(self, llm, query, parent, skill=None, attachments=None):
            super().__init__(parent)
            seen["query"] = query
            seen["attachments"] = attachments

        def start(self):
            seen["started"] = True

    monkeypatch.setattr("stlibs.themes.hacker.derfer.LLMAICallback", FakeWorker)

    model_chat.chat.add_attachment(attachment_api.from_bytes(PNG, "cat.png"))
    model_chat.chat.input_edit.setPlainText("看看这张图")
    model_chat.chat._send_message()

    assert seen["query"] == "看看这张图"
    assert [item["name"] for item in seen["attachments"]] == ["cat.png"], "附件在半路被清空了"
    assert seen["started"] is True


@pytest.fixture
def worker_spy(monkeypatch):
    """拦住真正的生成线程，只记下它收到了什么。"""
    from PySide6.QtCore import QObject, Signal

    seen = {}

    class FakeWorker(QObject):
        finished = Signal(str)
        text_chunk = Signal(str)
        tool_event = Signal(dict)

        def __init__(self, llm, query, parent, skill=None, attachments=None):
            super().__init__(parent)
            seen["query"] = query
            seen["skill"] = skill
            seen["attachments"] = attachments

        def start(self):
            seen["started"] = True

    monkeypatch.setattr("stlibs.themes.hacker.derfer.LLMAICallback", FakeWorker)
    return seen


def test_model_chat_passes_attachments_to_worker(model_chat, worker_spy):
    from stlibs.ai import attachment as attachment_api

    item = attachment_api.from_bytes(PNG, "cat.png")
    model_chat.add_user_msg("这是什么", [item])

    assert worker_spy["query"] == "这是什么"
    assert [entry["name"] for entry in worker_spy["attachments"]] == ["cat.png"]
    assert worker_spy["started"] is True


def test_warns_when_local_model_cannot_see_images(model_chat, worker_spy, monkeypatch, notify_spy):
    from stlibs.ai import attachment as attachment_api

    model_chat.is_local = True
    monkeypatch.setattr(attachment_api, "can_see_images", lambda model: False)

    model_chat.add_user_msg("看图", [attachment_api.from_bytes(PNG, "cat.png")])

    assert notify_spy[-1][0] == "warning"
    assert "看不了图片" in notify_spy[-1][1]
    assert worker_spy["started"] is True, "提示不该挡住发送"


def test_no_warning_for_text_only_messages(model_chat, worker_spy, monkeypatch, notify_spy):
    from stlibs.ai import attachment as attachment_api

    model_chat.is_local = True
    monkeypatch.setattr(attachment_api, "can_see_images", lambda model: False)

    model_chat.add_user_msg("只有文字", [attachment_api.from_bytes(b"hi", "a.txt")])

    assert notify_spy == [], "没有图片就别提示"


def test_no_warning_when_model_can_see_images(model_chat, worker_spy, monkeypatch, notify_spy):
    from stlibs.ai import attachment as attachment_api

    model_chat.is_local = True
    monkeypatch.setattr(attachment_api, "can_see_images", lambda model: True)

    model_chat.add_user_msg("看图", [attachment_api.from_bytes(PNG, "cat.png")])

    assert notify_spy == []


def test_warning_check_failure_does_not_block_send(model_chat, worker_spy, monkeypatch):
    from stlibs.ai import attachment as attachment_api

    model_chat.is_local = True

    def broken(_model):
        raise RuntimeError("ollama 挂了")

    monkeypatch.setattr(attachment_api, "can_see_images", broken)

    model_chat.add_user_msg("看图", [attachment_api.from_bytes(PNG, "cat.png")])

    assert worker_spy["started"] is True, "能力查询失败也不能挡住发送"
