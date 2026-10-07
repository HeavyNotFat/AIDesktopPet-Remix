from typing import Any, Generator

from .. import Config

import httpx
from openai import OpenAI
from PySide6.QtCore import Signal, QObject


class LLM(QObject):
    memory_signal = Signal(list)

    def __init__(self, model: str, api_key: str, base_url: str, system_prompt: str = ""):
        super().__init__()
        from . import LTMemory, Memory

        self.model = model
        self.memory = Memory()
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            http_client=httpx.Client(trust_env=True)
        )
        self.lt_memory = LTMemory(scope=f"cloud:{model}") if Config.memory["longterm"] else None
        if system_prompt.strip(): self.memory.add_system_msg(system_prompt)

    def chat(self, query) -> Generator[dict[str, str | None] | str | dict[str, str | Any] | Any, Any, None]:
        from . import inject_memory_context

        if not Config.memory['shortterm']: self.memory.clear()
        self.memory.add_user_msg(query)
        messages = self.memory.messages
        if self.lt_memory is not None:
            messages = inject_memory_context(messages, self.lt_memory.build_context(query))
        reply_parts = []

        # noinspection PyTypeChecker
        completion = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            extra_body={"enable_thinking": False},
            stream=True,
            modalities=["text", "audio"],
            audio={"voice": "default", "format": "mp3"},
        )
        for chunk in completion:
            # noinspection PyUnresolvedReferences
            if not chunk.choices: continue

            try:
                # noinspection PyUnresolvedReferences
                delta = chunk.choices[0].delta
            except AttributeError:
                # noinspection PyUnresolvedReferences
                delta = chunk.choices[0].message

            # 工具调用
            function_call = getattr(delta, "function_call", None)
            if function_call:
                yield {"type": "tool_call",
                       "name": function_call.name,
                       "args": function_call.arguments}
                continue

            # 音频（流式文本结束后，服务端会推一个带完整 audio 的 chunk）
            audio = getattr(delta, "audio", None)
            if audio:
                audio_data = audio.get("data") if isinstance(audio, dict) else getattr(audio, "data", None)
                transcript = audio.get("transcript") if isinstance(audio, dict) else getattr(audio, "transcript", None)
                if audio_data:
                    yield {"type": "audio", "data": audio_data, "transcript": transcript}
                continue

            ans = getattr(delta, "content", None)
            if ans is None: continue
            reply_parts.append(ans)
            yield ans

        reply = "".join(reply_parts)
        if reply:
            self.memory.add_assistant_msg(reply)
            if self.lt_memory is not None:
                self.lt_memory.remember_turn(query, reply)
        self.memory_signal.emit([self.model, self.memory.messages])

