import pytest

from stlibs.ai import MultiAgentCoop


class FakeLLM:
    def __init__(self, name, reply="", error=None):
        self.name = name
        self.reply = reply
        self.error = error
        self.calls = []

    def complete(self, messages):
        self.calls.append(messages)
        if self.error:
            raise self.error
        yield self.reply


def make_coop(agents, replies=None, **config):
    replies = replies or {}
    built = {}

    def builder(model_key, system_prompt=""):
        llm = FakeLLM(model_key, replies.get(model_key, f"{model_key}-的输出"))
        built[(model_key, system_prompt)] = llm
        return llm

    settings = {"enable": True, "mode": "review", "rounds": 1, "agents": agents}
    settings.update(config)
    return MultiAgentCoop(config=settings, builder=builder), built


def collect(coop, lead, query="问题"):
    events = []
    text = ""
    for item in coop.run(query, lead, base_messages=[{"role": "user", "content": query}]):
        if isinstance(item, str):
            text += item
        else:
            events.append(item)
    return events, text


def stages(events):
    return [event["stage"] for event in events]


def test_disabled_by_default():
    coop = MultiAgentCoop(config={})
    assert coop.enable is False
    assert coop.describe() == "协作已关闭"


def test_review_pipeline_order_and_final_prompt():
    agents = [{"model": "reviewer-a", "name": "小A"}, {"model": "reviewer-b", "name": "小B"}]
    coop, built = make_coop(agents)
    lead = FakeLLM("lead", "定稿")

    events, text = collect(coop, lead)

    assert stages(events) == ["draft", "review_start", "review_done", "review_start", "review_done", "final"]
    assert text == "定稿"
    # 初稿走的是不碰记忆的 complete()，定稿提示里带着初稿和两份评审
    final_prompt = lead.calls[-1][-1]["content"]
    assert "初稿" in final_prompt and "小A" in final_prompt and "小B" in final_prompt
    assert built[("reviewer-a", MultiAgentCoop.REVIEW_PROMPT)].calls[0][-1]["content"].count("初稿") == 0
    assert len(lead.calls) == 2


def test_parallel_mode_collects_every_agent():
    agents = [{"model": "a", "name": "A"}, {"model": "b", "name": "B"}]
    coop, _built = make_coop(agents, mode="parallel")
    lead = FakeLLM("lead", "汇总")

    events, text = collect(coop, lead)

    assert stages(events) == ["agent_start", "agent_done", "agent_start", "agent_done", "final"]
    assert text == "汇总"
    final_prompt = lead.calls[-1][-1]["content"]
    assert "a-的输出" in final_prompt and "b-的输出" in final_prompt
    assert "汇总" in final_prompt or "综合" in final_prompt


def test_agent_error_does_not_break_the_round():
    agents = [{"model": "bad", "name": "坏的"}, {"model": "good", "name": "好的"}]
    coop, _built = make_coop(agents)
    coop._builder = lambda model_key, system_prompt="": FakeLLM(
        model_key, "好的意见", RuntimeError("连接失败") if model_key == "bad" else None
    )
    lead = FakeLLM("lead", "定稿")

    events, text = collect(coop, lead)

    assert "agent_error" in stages(events)
    assert [event["agent"] for event in events if event["stage"] == "review_done"] == ["好的"]
    assert text == "定稿"


def test_all_agents_failing_falls_back_to_draft():
    coop, _built = make_coop([{"model": "x", "name": "X"}])
    coop._builder = lambda model_key, system_prompt="": FakeLLM(model_key, "", RuntimeError("坏了"))
    lead = FakeLLM("lead", "初稿")

    events, text = collect(coop, lead)

    assert stages(events) == ["draft", "review_start", "agent_error", "empty"]
    assert text == "初稿"


def test_no_agents_falls_back_to_plain_answer():
    coop, _built = make_coop([])
    lead = FakeLLM("lead", "普通回答")

    events, text = collect(coop, lead)

    assert stages(events) == ["empty"]
    assert "按普通模式回答" in events[0]["detail"]
    assert text == "普通回答"


def test_rounds_repeat_the_review():
    coop, _built = make_coop([{"model": "a", "name": "A"}], rounds=3)
    lead = FakeLLM("lead", "定稿")

    events, _text = collect(coop, lead)

    assert stages(events).count("review_start") == 3
    assert [event["round"] for event in events if event["stage"] == "review_start"] == [1, 2, 3]


def test_rounds_and_mode_are_clamped():
    coop = MultiAgentCoop(config={"enable": True, "mode": "瞎写", "rounds": "很多"})
    assert coop.rounds == 1
    assert coop.mode == "review"

    coop = MultiAgentCoop(config={"enable": True, "rounds": 99})
    assert coop.rounds == 3


def test_agents_skip_incomplete_rows():
    coop = MultiAgentCoop(config={"enable": True, "agents": [
        {"model": "ok", "name": "OK"},
        {"model": "  ", "name": "空模型"},
        "不是字典",
        {"name": "没有模型"},
    ]})
    assert [agent["model"] for agent in coop.agents] == ["ok"]
    assert coop.agents[0]["name"] == "OK"


def test_agent_without_name_uses_model_name():
    coop = MultiAgentCoop(config={"enable": True, "agents": [{"model": "glm4:latest"}]})
    assert coop.agents[0]["name"] == "glm4:latest"
    assert coop.agents[0]["prompt"] == ""


def test_custom_role_prompt_is_used_as_system_prompt():
    agents = [{"model": "a", "name": "A", "prompt": "你是杠精"}]
    coop, built = make_coop(agents)
    collect(coop, FakeLLM("lead", "定稿"))

    assert ("a", "你是杠精") in built
    assert ("a", MultiAgentCoop.REVIEW_PROMPT) not in built


def test_instances_are_cached_between_runs():
    coop, built = make_coop([{"model": "a", "name": "A"}])
    lead = FakeLLM("lead", "定稿")

    collect(coop, lead)
    collect(coop, lead, query="第二个问题")

    assert len(built) == 1
    assert len(built[("a", MultiAgentCoop.REVIEW_PROMPT)].calls) == 2


def test_reconfigure_picks_up_new_settings():
    coop, _built = make_coop([{"model": "a"}])
    assert coop.enable is True

    coop.reconfigure({"enable": False})
    assert coop.enable is False
    assert coop.agents == []

    coop.reconfigure({"enable": True, "agents": [{"model": "b"}]})
    assert [agent["model"] for agent in coop.agents] == ["b"]


def test_describe_summarizes_settings():
    coop, _built = make_coop([{"model": "a"}, {"model": "b"}], mode="parallel", rounds=2)
    assert coop.describe() == "并行汇总：主模型 + 2 个协作模型，2 轮"

    empty = MultiAgentCoop(config={"enable": True, "agents": []})
    assert "没有配置可用的模型" in empty.describe()


def test_llm_without_complete_falls_back_to_chat():
    class OnlyChat:
        def __init__(self):
            self.seen = []

        def chat(self, question, should_emit=True):
            self.seen.append(question)
            yield "兜底"

    agent = OnlyChat()
    coop = MultiAgentCoop(config={"enable": True, "agents": [{"model": "a"}]}, builder=lambda *_a, **_k: agent)
    lead = FakeLLM("lead", "定稿")

    _events, text = collect(coop, lead)

    assert text == "定稿"
    assert agent.seen, "没有 complete() 时应该退回 chat()"


@pytest.mark.parametrize("agents", [[{"model": "a"}], [{"model": "a"}, {"model": "b"}]])
def test_lead_draft_is_not_written_into_memory(agents):
    coop, _built = make_coop(agents)
    lead = FakeLLM("lead", "定稿")

    collect(coop, lead)

    # 初稿用 complete()（不碰记忆），定稿也走 complete()，由 LLM.chat() 统一记账
    assert all(call[-1]["role"] == "user" for call in lead.calls)
