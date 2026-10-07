import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import stlibs
from stlibs.ai import MultiAgentCoop, build_llm


def main():
    argv = sys.argv[1:]
    lead_model = argv[0] if argv else "glm4:latest"
    members = argv[1:] or [lead_model]

    # 联调只关心协作本身，别去拉 MCP、也别建 RAG 索引
    stlibs.Config.mcp["enable"] = False
    stlibs.Config.rag["enable"] = False
    stlibs.Config.memory["longterm"] = False

    coop = MultiAgentCoop(config={
        "enable": True,
        "mode": "review",
        "rounds": 1,
        "agents": [{"model": model, "name": model} for model in members],
    })
    assert coop.agents, "没有可用的协作成员"

    lead = build_llm(lead_model, "你是一个简洁的助手。", coop=False)
    question = "用三句话说明为什么要给代码写测试。"
    print(f"主模型：{lead_model}")
    print(f"协作成员：{'、'.join(members)}")
    print(f"模式：{coop.describe()}")
    print(f"问题：{question}\n")

    started = time.time()
    answer = ""
    for event in coop.run(question, lead, base_messages=[{"role": "user", "content": question}]):
        elapsed = time.time() - started
        if isinstance(event, str):
            answer += event
            continue

        stage = event.get("stage")
        if stage in {"review_done", "agent_done"}:
            print(f"[{elapsed:6.2f}s] {event.get('agent')} 的意见：{event.get('text', '')[:80]!r}")
        elif stage == "agent_error":
            print(f"[{elapsed:6.2f}s] {event.get('agent')} 失败：{event.get('detail')}")
        else:
            print(f"[{elapsed:6.2f}s] {stage} {event.get('detail', '')}".rstrip())

    print(f"\n定稿（{len(answer)} 字）：\n{answer}")
    assert answer.strip(), "协作没有产出定稿"
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
