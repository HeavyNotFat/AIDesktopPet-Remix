import pytest

from stlibs.ai import find_skill, inject_skill, parse_skill, skill_prompt

SKILLS = [
    {"name": "翻译", "description": "翻译成中文", "prompt": "只输出译文"},
    {"name": "Review", "description": "", "prompt": "挑毛病"},
    {"name": "", "prompt": "没有名字的应该被忽略"},
    "不是字典",
]


def test_find_skill_by_name():
    assert find_skill("翻译", SKILLS)["prompt"] == "只输出译文"
    assert find_skill("/翻译", SKILLS)["name"] == "翻译"
    assert find_skill("review", SKILLS)["name"] == "Review", "应该忽略大小写"
    assert find_skill(" Review ", SKILLS)["name"] == "Review"


def test_find_skill_missing():
    assert find_skill("没有的技能", SKILLS) is None
    assert find_skill("", SKILLS) is None
    assert find_skill("/", SKILLS) is None


def test_find_skill_ignores_broken_rows():
    assert find_skill("不是字典", SKILLS) is None
    assert find_skill("", SKILLS) is None


def test_parse_skill_splits_prefix_and_body():
    skill, text = parse_skill("/翻译 hello world", SKILLS)

    assert skill["name"] == "翻译"
    assert text == "hello world"


def test_parse_skill_without_body():
    skill, text = parse_skill("/总结", [{"name": "总结", "prompt": "p"}])

    assert skill["name"] == "总结"
    assert text == ""


def test_parse_skill_passes_through_unknown():
    skill, text = parse_skill("/没有这个 正文", SKILLS)

    assert skill is None
    assert text == "/没有这个 正文", "认不出来就原样发出去，别把用户的话吃掉"


def test_parse_skill_ignores_plain_text():
    skill, text = parse_skill("直接说话", SKILLS)

    assert skill is None
    assert text == "直接说话"


def test_parse_skill_keeps_extra_spaces_in_body():
    _skill, text = parse_skill("/翻译   两边有空格   ", SKILLS)

    assert text == "两边有空格"


def test_inject_skill_goes_after_system_messages():
    messages = [
        {"role": "system", "content": "你是助手"},
        {"role": "user", "content": "第一轮"},
        {"role": "assistant", "content": "回答"},
        {"role": "user", "content": "问题"},
    ]

    result = inject_skill(messages, "只输出译文")

    assert [item["role"] for item in result] == ["system", "system", "user", "assistant", "user"]
    assert result[1]["content"] == "只输出译文"
    assert result[-1]["content"] == "问题", "用户消息必须原样保留"
    assert messages[1]["content"] == "第一轮", "不能就地改原列表"


def test_inject_skill_without_system_message():
    messages = [{"role": "user", "content": "问题"}]

    result = inject_skill(messages, "只输出译文")

    assert [item["role"] for item in result] == ["system", "user"]


@pytest.mark.parametrize("prompt", ["", "   ", None])
def test_inject_skill_ignores_empty_prompt(prompt):
    messages = [{"role": "user", "content": "问题"}]

    assert inject_skill(messages, prompt) == messages


def test_skill_prompt_reads_dict():
    assert skill_prompt({"prompt": "  内容  "}) == "内容"
    assert skill_prompt({"name": "只有名字"}) == ""
    assert skill_prompt(None) == ""
    assert skill_prompt("字符串") == ""


def test_local_llm_chat_injects_skill(monkeypatch):
    pytest.importorskip("PySide6.QtCore", reason="local.LLM 是 QObject")
    import stlibs

    monkeypatch.setattr(stlibs.Config, "mcp", {"enable": False, "mcp": []}, raising=False)
    monkeypatch.setattr(stlibs.Config, "rag", {"enable": False}, raising=False)
    monkeypatch.setattr(stlibs.Config, "memory", {"shortterm": True, "longterm": False}, raising=False)

    from stlibs.ai import local

    llm = local.LLM("skill-probe")
    captured = {}

    class FakeCall:
        def run(self, messages):
            captured["messages"] = [dict(item) for item in messages]
            yield "好的"

    llm.function_call = FakeCall()
    llm.rag = None

    assert "".join(llm.chat("你好", skill="你是翻译")) == "好的"
    assert [item["role"] for item in captured["messages"]] == ["system", "user"]
    assert captured["messages"][0]["content"] == "你是翻译"
    assert captured["messages"][1]["content"] == "你好"
    assert llm.memory.messages == [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "好的"},
    ], "记忆里只有这轮问答，不该混进提示词"


def test_local_llm_chat_without_skill_has_no_extra_system_message(monkeypatch):
    pytest.importorskip("PySide6.QtCore", reason="local.LLM 是 QObject")
    import stlibs

    monkeypatch.setattr(stlibs.Config, "mcp", {"enable": False, "mcp": []}, raising=False)
    monkeypatch.setattr(stlibs.Config, "rag", {"enable": False}, raising=False)
    monkeypatch.setattr(stlibs.Config, "memory", {"shortterm": True, "longterm": False}, raising=False)

    from stlibs.ai import local

    llm = local.LLM("skill-probe-2")
    captured = {}

    class FakeCall:
        def run(self, messages):
            captured["messages"] = [dict(item) for item in messages]
            yield "好的"

    llm.function_call = FakeCall()
    llm.rag = None

    list(llm.chat("你好"))

    assert [item["role"] for item in captured["messages"]] == ["user"]
