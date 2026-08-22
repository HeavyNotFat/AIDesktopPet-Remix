from .. import Config

import httpx
from openai import OpenAI
from PySide6.QtCore import Signal, QObject


class LLM(QObject):
    memory_signal = Signal(list)

    def __init__(self, model: str, api_key: str, base_url: str,  system_prompt: str = ""):
        super().__init__()
        from . import Memory

        self.model = model
        self.memory = Memory()
        self.model = model
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            http_client=httpx.Client(trust_env=True)
        )
        if system_prompt.strip(): self.memory.add_system_msg(system_prompt)

    def chat(self, query) -> dict | None:
        if not Config.memory['shortterm']: self.memory.clear()
        self.memory.add_user_msg(query)
        reply_parts = []

        completion = self.client.chat.completions.create(
            model=self.model,
            messages=self.memory.messages,
            extra_body={"enable_thinking": False},
            stream=True,
        )
        for chunk in completion:
            if not chunk.choices: continue

            try:
                if chunk.choices[0].delta.function_call:
                    yield {"type": "tool_call",
                           "name": chunk.choices[0].delta.function_call.name,
                           "args": chunk.choices[0].delta.function_call.arguments}
                    continue
                ans = chunk.choices[0].delta.content
                if ans is None: continue
                reply_parts.append(ans)
                yield ans
            except AttributeError:
                if chunk.choices[0].message.function_call:
                    yield {"type": "tool_call",
                           "name": chunk.choices[0].message.function_call.name,
                           "args": chunk.choices[0].message.function_call.arguments}
                    continue
                ans = chunk.choices[0].message.content
                if ans is None: continue
                reply_parts.append(ans)
                yield ans

        reply = "".join(reply_parts)
        if reply:
            self.memory.add_assistant_msg(reply)
        self.memory_signal.emit([self.model, self.memory.messages])
