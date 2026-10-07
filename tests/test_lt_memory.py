import json

import pytest

from stlibs.ai import LTMemory, inject_memory_context, summarize_turns


@pytest.fixture
def memory(tmp_path):
    def factory(scope="probe", **kwargs):
        kwargs.setdefault("window", 2)
        return LTMemory(scope=scope, path=str(tmp_path / "lt.json"), **kwargs)

    return factory


def test_summarize_keeps_question_and_answer():
    text = summarize_turns(
        [
            {"user": "我住在杭州", "assistant": "杭州是座很舒服的城市，西湖很值得逛。"},
            {"user": "我喜欢猫娘", "assistant": "好的喵，记住啦。"},
        ]
    )
    assert "杭州" in text and "猫娘" in text
    assert text.count("用户问：") == 2


def test_summarize_truncates_to_limit():
    turns = [{"user": "问" * 200, "assistant": "答" * 200}]
    assert len(summarize_turns(turns, max_chars=120)) <= 120


def test_remember_turn_waits_for_window(memory):
    store = memory()
    assert store.remember_turn("第一问", "第一答") is None
    entry = store.remember_turn("第二问", "第二答")
    assert entry is not None
    assert entry["turns"] == 2
    assert entry["topics"] == ["第一问", "第二问"]
    assert store.stats()["entries"] == 1


def test_flush_writes_partial_window(memory):
    store = memory()
    store.remember_turn("只有一问", "只有一答")
    entry = store.flush()
    assert entry["turns"] == 1
    assert store.flush() is None


def test_recall_ranks_related_entries(memory):
    store = memory(window=1)
    store.remember_turn("我住在杭州", "杭州很美")
    store.remember_turn("我养了一只猫", "猫很可爱")

    hits = store.recall("杭州怎么样")
    assert hits and "杭州" in hits[0]["summary"]
    assert hits[0]["score"] > 0
    assert store.recall("量子纠缠") == []


def test_recall_can_cross_scopes(memory, tmp_path):
    path = str(tmp_path / "lt.json")
    first = LTMemory(scope="model-a", path=path, window=1)
    second = LTMemory(scope="model-b", path=path, window=1)
    first.remember_turn("我喜欢抹茶", "抹茶好喝")
    second.remember_turn("我讨厌香菜", "记下了")

    assert [e["scope"] for e in first.recall("抹茶")] == ["model-a"]
    assert {e["scope"] for e in first.recall("香菜", scope=None)} == {"model-b"}
    assert first.recall("香菜", scope="model-a") == []


def test_entries_survive_new_instance(memory, tmp_path):
    store = memory()
    store.remember_turn("记住这个名字：小明", "好的")
    store.flush()

    reopened = LTMemory(scope="probe", path=str(tmp_path / "lt.json"))
    assert reopened.stats()["entries"] == 1
    assert reopened.recall("小明")


def test_instances_share_one_file_without_losing_entries(memory, tmp_path):
    path = str(tmp_path / "shared.json")
    stores = [LTMemory(scope=f"s{i}", path=path, window=1) for i in range(4)]

    for index, store in enumerate(stores):
        store.remember_turn(f"问题{index}", f"回答{index}")

    entries = LTMemory(scope="reader", path=path).entries()
    assert len(entries) == 4, "并发写同一个记忆文件时丢了条目"


def test_max_entries_trims_oldest(memory):
    store = memory(window=1, max_entries=3)
    for index in range(6):
        store.remember_turn(f"问题{index}", f"回答{index}")

    entries = store.entries()
    assert len(entries) == 3
    assert "问题5" in entries[-1]["summary"]


def test_build_context_format_and_empty(memory):
    store = memory(window=1)
    assert store.build_context("随便问问") == ""

    store.remember_turn("我住在杭州", "杭州很美")
    context = store.build_context("杭州")
    assert "长期记忆" in context
    assert "[1]" in context
    assert "杭州" in context


def test_context_can_be_capped(memory):
    store = memory(window=1)
    for index in range(5):
        store.remember_turn(f"关于杭州的问题{index}", "杭州" * 50)
    assert len(store.build_context("杭州", max_chars=200)) <= 200


def test_clear_by_scope_and_all(memory, tmp_path):
    path = str(tmp_path / "lt.json")
    first = LTMemory(scope="a", path=path, window=1)
    second = LTMemory(scope="b", path=path, window=1)
    first.remember_turn("a 的问题", "a 的回答")
    second.remember_turn("b 的问题", "b 的回答")

    assert first.clear(scope="a") == 1
    assert [e["scope"] for e in first.entries()] == ["b"]
    assert first.clear() == 1
    assert first.entries() == []


def test_stats_reports_scopes(memory, tmp_path):
    path = str(tmp_path / "lt.json")
    LTMemory(scope="a", path=path, window=1).remember_turn("x", "y")
    LTMemory(scope="b", path=path, window=1).remember_turn("x", "y")

    stats = LTMemory(scope="c", path=path).stats()
    assert stats["entries"] == 2
    assert stats["scopes"] == {"a": 1, "b": 1}
    assert stats["path"].endswith("lt.json")


def test_custom_summarizer_is_used(memory):
    store = memory(window=1, summarizer=lambda turns, max_chars: "压缩后的摘要")
    store.remember_turn("原始问题", "原始回答")
    assert store.entries()[0]["summary"] == "压缩后的摘要"


def test_corrupted_store_is_tolerated(memory, tmp_path):
    path = tmp_path / "lt.json"
    path.write_text("{ 这不是 JSON", encoding="utf-8")

    store = LTMemory(scope="probe", path=str(path), window=1)
    assert store.entries() == []
    store.remember_turn("还能写", "是的")
    assert json.loads(path.read_text(encoding="utf-8"))["entries"][0]["topics"] == ["还能写"]


def test_inject_memory_context_keeps_system_first():
    messages = [
        {"role": "system", "content": "你是桌宠"},
        {"role": "user", "content": "在吗"},
    ]
    merged = inject_memory_context(messages, "记忆内容")
    assert [m["role"] for m in merged] == ["system", "system", "user"]
    assert merged[1]["content"] == "记忆内容"
    assert inject_memory_context(messages, "") is messages
