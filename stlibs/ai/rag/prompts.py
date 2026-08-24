import json

PROMPTS_PATH = "./resources/prompts.json"


def load_prompts(path=PROMPTS_PATH):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


prompts = load_prompts()
