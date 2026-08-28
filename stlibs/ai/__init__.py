import base64


def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        data = base64.b64encode(image_file.read()).decode("utf-8")
        image_file.close()
    return data


class LTMemory:
    """长期记忆：将历史对话压缩摘要后存入 RAG 或本地内存"""
    # TODO: LT
    pass


class Memory:
    """
    实时对话记忆
    """
    def __init__(self):
        self.messages = []

    def add_user_msg(self, msg: str):
        self.messages.append({"role": "user", "content": msg})

    def add_user_image(self, path: str):
        self.messages.append({"role": "user", "content": {"type": "image_url", "image_url": {
            "url": f"data:image/png;base64,{encode_image(path)}"}}})

    def add_assistant_msg(self, msg: str):
        self.messages.append({"role": "assistant", "content": msg})

    def add_system_msg(self, msg: str):
        self.messages.append({"role": "system", "content": msg})

    def clear(self):
        self.messages.clear()


class MultiAgentCoop:
    """
    多Agent合作
    """
    # TODO: MultiAgentCoop
    pass


class TTSEmotion:
    """
    语音情感
    """
    # TODO: TTSEmotion
    pass
