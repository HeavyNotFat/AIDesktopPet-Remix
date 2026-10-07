import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import stlibs
from stlibs.ai import local, parse_skill

MARK = "【技能生效】"
SKILL = {"name": "暗号", "description": "联调用", "prompt": f"无论用户问什么，回答开头都必须原样写上 {MARK} 这四个字符。"}


def ask(llm, question, skill=None):
    return "".join(chunk for chunk in llm.chat(question, should_emit=False, skill=skill) if isinstance(chunk, str))


def main():
    model = sys.argv[1] if len(sys.argv) > 1 else "glm4:latest"

    stlibs.Config.mcp["enable"] = False
    stlibs.Config.rag["enable"] = False
    stlibs.Config.memory["longterm"] = False

    print("技能列表（配置文件里的）:")
    for item in stlibs.Config.skills or []:
        print(f"   /{item['name']}  {item.get('description', '')}")

    skill, body = parse_skill("/翻译 把这句话翻译成英文", stlibs.Config.skills)
    print(f"\n前缀解析：技能={skill['name'] if skill else None} 正文={body!r}")
    assert skill and body == "把这句话翻译成英文"

    question = "用一句话介绍你自己"

    plain = local.LLM(model, coop=False)
    without = ask(plain, question)
    print(f"\n不启用技能（{len(without)} 字）：{without[:60]!r}")
    assert MARK not in without, "没启用技能却出现了暗号，说明注入逻辑有问题"

    with_skill = local.LLM(model, coop=False)
    answer = ask(with_skill, question, skill=SKILL["prompt"])
    print(f"启用技能（{len(answer)} 字）：{answer[:60]!r}")
    assert MARK in answer, f"技能提示词没生效（回答里没有 {MARK}）"

    print("\n技能确实进了模型上下文")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
