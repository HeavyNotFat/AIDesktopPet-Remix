from ... import SharingData


def generate(model: str, question: str) -> str:
    llm = SharingData.theme.ModelChat.return_llm_class(model)
    ct = ""
    for text in llm.chat(question, False):
        if isinstance(text, str):
            ct += text

    return ct or '（模型返回了空内容）'
