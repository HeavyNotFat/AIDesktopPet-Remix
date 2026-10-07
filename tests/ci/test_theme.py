"""UI 主题类映射检测的行为验证。

契约来源：``stlibs/__init__.py::_ThemeTypingProtocol`` +
``stlibs/themes/base.py`` 里的抽象基类。
"""

from __future__ import annotations

from conftest import BASE_SRC, MAPPING_NAMES, PROTOCOL_SRC, THEME_SUBMODULES, findings_of, write_mini_repo, run_checks

THEME_HEAD = '''\
from . import general, llm, tts, settings, animation


class HackerWindow:
    def addNavigation(self, text, widget, shortcut_keys=None, position="top", category=None): pass
    def removeNavigation(self, widget): pass
    def create_category(self, category, position="top"): pass
    def setTitle(self, title): pass


class HackerButton:
    pass


class HackerMenu:
    def addSeparator(self): pass
    def addAction(self, action): pass


class HackerIconList:
    SETTING = None
    CHAT = None
    SHUTDOWN = None

    def init(self): pass


class HackerChatWidget:
    userInputSignal = None

    def add_user_msg(self, text=""): pass
    def add_assistant_msg(self, text="", image=None): pass
    def disable_send_button(self): pass
    def enable_send_button(self): pass
    def update_bubble_widths(self): pass
    def scroll_to_bottom(self): pass
    def clear_messages(self): pass


class HackerChatBubble:
    def append_text(self, chunk): pass
    def updateBubbleWidth(self, width): pass


class HackerModelChat:
    @staticmethod
    def return_llm_class(model): pass
'''

# 只提供「必需映射」里的前五个，其余留给测试断言
THEME_EXPORTS = '''\
Window = HackerWindow
Button = HackerButton
Menu = HackerMenu
IconList = HackerIconList()
ChatWidget = HackerChatWidget
ChatBubble = HackerChatBubble
ModelChat = HackerModelChat
'''

FULL_EXPORTS = THEME_EXPORTS + "".join(
    f"{name} = HackerButton\n" for name in MAPPING_NAMES if name not in {
        "Window", "Button", "Menu", "ChatWidget", "ChatBubble", "ModelChat",
    }
)


def _theme(files: dict[str, str] | None = None, exports: str = THEME_EXPORTS, head: str = THEME_HEAD):
    base = {"stlibs/themes/hacker/__init__.py": head + "\n\n" + exports}
    base.update({f"stlibs/themes/hacker/{name}.py": text for name, text in THEME_SUBMODULES.items()})
    base.update(files or {})
    return base


def test_missing_mapping_is_error(mini_repo):
    root = mini_repo(_theme(), contract=True)
    findings = findings_of(root, "theme/mapping-missing")
    missing = {f.message.split("映射 ")[1].split("，")[0] for f in findings}
    assert missing == {
        "Label", "Action", "ScrollArea", "TextEdit", "LineEdit", "Slider", "ComboBox", "CardWidget",
    }
    assert all(f.severity.value == "error" for f in findings)


def test_complete_theme_has_no_mapping_findings(mini_repo):
    root = mini_repo(_theme(exports=FULL_EXPORTS), contract=True)
    assert findings_of(root, "theme/mapping-missing") == []
    assert findings_of(root, "theme/member-missing") == []


def test_missing_submodule(mini_repo):
    files = _theme()
    del files["stlibs/themes/hacker/tts.py"]
    root = mini_repo(files, contract=True)
    findings = findings_of(root, "theme/submodule-missing")
    assert len(findings) == 1
    assert "子模块 tts" in findings[0].message


def test_missing_member(mini_repo):
    head = THEME_HEAD.replace("    def setTitle(self, title): pass\n", "")
    root = mini_repo(_theme(head=head), contract=True)
    findings = findings_of(root, "theme/member-missing")
    assert len(findings) == 1
    assert "setTitle" in findings[0].message


def test_missing_member_from_abstract_base(mini_repo):
    """ModelChat 的 return_llm_class 来自 ModelChatABS 契约。"""
    head = THEME_HEAD.replace(
        "class HackerModelChat:\n    @staticmethod\n    def return_llm_class(model): pass\n",
        "class HackerModelChat:\n    pass\n",
    )
    root = mini_repo(_theme(head=head), contract=True)
    findings = findings_of(root, "theme/member-missing")
    assert any("return_llm_class" in f.message for f in findings)


def test_kind_mismatch_between_themes(mini_repo):
    files = _theme(exports=FULL_EXPORTS)
    files["stlibs/themes/plain/__init__.py"] = (
        "from . import general, llm, tts, settings, animation\n\n\n"
        "def Window(): pass\n"
        + "".join(f"{name} = object\n" for name in MAPPING_NAMES if name != "Window")
        + "IconList = object\n"
    )
    for name, text in THEME_SUBMODULES.items():
        files[f"stlibs/themes/plain/{name}.py"] = text
    root = mini_repo(files, contract=True)
    findings = findings_of(root, "theme/kind-mismatch")
    assert findings
    assert any("Window" in f.message for f in findings)


def test_usage_unsupported(mini_repo):
    files = _theme()
    files["stlibs/graphics/chat.py"] = "from stlibs import SharingData\n\n\ndef build():\n    return SharingData.theme.Nope()\n"
    root = mini_repo(files, contract=True)
    findings = findings_of(root, "theme/usage-unsupported")
    assert len(findings) == 1
    assert "Nope" in findings[0].message


def test_protocol_drift_warning(mini_repo):
    files = _theme(exports=THEME_EXPORTS + "Extra = HackerButton\n")
    files["stlibs/graphics/chat.py"] = "from stlibs import SharingData\n\n\ndef build():\n    return SharingData.theme.Extra()\n"
    root = mini_repo(files, contract=True)
    findings = findings_of(root, "theme/protocol-drift")
    assert len(findings) == 1
    assert "_ThemeTypingProtocol" in findings[0].message


def test_declared_mapping_used_by_app_is_clean(mini_repo):
    files = _theme()
    files["stlibs/graphics/chat.py"] = (
        "from stlibs import SharingData\n\n\ndef build():\n    return SharingData.theme.Window()\n"
    )
    root = mini_repo(files, contract=True)
    report = run_checks(root, ["theme/usage-unsupported", "theme/protocol-drift"])
    assert report.findings == []


def test_module_member_missing(mini_repo):
    files = _theme()
    files["stlibs/graphics/settings.py"] = (
        "from stlibs import SharingData\n\n\ndef build():\n    return SharingData.theme.general.OtherPage()\n"
    )
    root = mini_repo(files, contract=True)
    findings = findings_of(root, "theme/module-member")
    assert len(findings) == 1
    assert "OtherPage" in findings[0].message


def test_protocol_missing_is_error(mini_repo):
    root = mini_repo({"stlibs/__init__.py": "SharingData = None\n", **_theme()})
    findings = findings_of(root, "theme/protocol-declared")
    assert len(findings) == 1
    assert "找不到 _ThemeTypingProtocol" in findings[0].message


def test_alias_duplicate_warning(mini_repo):
    exports = THEME_EXPORTS.replace("Button = HackerButton", "Button = HackerButton\nLabel = HackerButton")
    root = mini_repo(_theme(exports=exports), contract=True)
    findings = findings_of(root, "theme/alias-duplicate")
    assert len(findings) == 1
    assert "HackerButton" in findings[0].message


def test_abc_mapping_warns_when_missing(mini_repo):
    """契约关联的抽象基类被删掉时要提示（否则成员要求会静默失效）。"""
    trimmed_base = BASE_SRC.split("class IconListABS")[0]
    files = _theme(exports=FULL_EXPORTS)
    files["stlibs/__init__.py"] = PROTOCOL_SRC
    files["stlibs/themes/base.py"] = trimmed_base
    root = mini_repo(files)
    findings = findings_of(root, "theme/abc-mapping")
    assert {f.message.split("契约把 ")[1].split(" ")[0] for f in findings} == {"Menu", "IconList"}


def test_instance_mapping_members_are_checked(mini_repo):
    """IconList 是实例（IconList = IconList()），成员同样要按 ABC 校验。"""
    head = THEME_HEAD.replace("    CHAT = None\n", "")
    root = mini_repo(_theme(head=head), contract=True)
    findings = findings_of(root, "theme/member-missing")
    assert any("CHAT" in f.message and "IconList" in f.message for f in findings)


def test_theme_checks_clean_on_real_repo(repo_root):
    report = run_checks(repo_root, ["theme/*"])
    assert report.crashes == [], [r.crash for r in report.crashes]
    assert report.findings == []
