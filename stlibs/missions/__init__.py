from openai import OpenAI

from PySide6.QtCore import QThread, Signal


class SendToAssistantMission(QThread):
    answer = Signal(str)
    finished = Signal(tuple)

    def __init__(self, question: str, parent):
        super().__init__(parent)
        self.question = question

    def run(self, /):
        client = OpenAI(
            api_key="sk-02635decf9604a6192293784b15e0753",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
        # noinspection PyTypeChecker
        completion = client.chat.completions.create(
            model="qwen-plus",
            messages=[{'role': 'user', 'content': self.question}],
            stream=True,
            stream_options={"include_usage": True},
            extra_body={
                "enable_search": True,
                # 搜索配置项
                # https://help.aliyun.com/zh/model-studio/web-search?spm=a2c4g.11186623.0.0.71823c80OYbXFR#312c12c262fsr
                "search_options": {
                    # 搜索策略
                    "search_strategy": "turbo",  # Literal['turbo', 'max', 'agent', 'agent-max']
                    # 图文并茂，此参数和enable_search相互独立（当设置此项为True时enable_search也为True，不用再次设置enable_search）
                    # "enable_text_image_mixed": True,
                    # 强制联网
                    # "forced_search": True,  # 强制联网，
                    # 开启垂域搜索
                    # "enable_search_extension": True,
                    # 搜索时效性
                    # "freshness": 7,
                    # 搜索站点范围
                    # "assigned_site_list": ['bing.com', 'csdn.net', 'zhihu.com'],
                    # 搜索意图指导
                    # "intention_options": {
                    #     "prompt_intervene": "",
                    # }
                },
                # 深度思考
                # "enable_thinking": True,

            },
        )

        all_content = []
        for chunk in completion:
            if chunk.choices:
                content = chunk.choices[0].delta.content or ""
                all_content.append(content)
                self.answer.emit("".join(all_content))
            elif chunk.usage:
                self.finished.emit(("".join(all_content), chunk.usage.prompt_tokens, chunk.usage.completion_tokens, chunk.usage.total_tokens))
