from typing import Any, Generator

from .. import Config, SharingData

import httpx
from openai import OpenAI
from PySide6.QtCore import Signal, QObject


class LLM(QObject):
    memory_signal = Signal(list)
    coop_signal = Signal(dict)

    def __init__(self, model: str, api_key: str, base_url: str, system_prompt: str = "", coop: bool | None = None):
        super().__init__()
        from . import LTMemory, Memory, MultiAgentCoop

        self.model = model
        self.memory = Memory()
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            http_client=httpx.Client(trust_env=True)
        )
        self.lt_memory = LTMemory(scope=f"cloud:{model}") if Config.memory["longterm"] else None
        self.coop_disabled = coop is False
        self.coop = None if self.coop_disabled else (MultiAgentCoop() if (coop or Config.coop.get("enable")) else None)
        SharingData.llm_instances[f"cloud:{model}"] = self
        if system_prompt.strip(): self.memory.add_system_msg(system_prompt)

    def chat(self, query, skill=None, attachments=None) -> Generator[dict[str, str | None] | str | dict[str, str | Any] | Any, Any, None]:
        from . import inject_memory_context, inject_skill

        if not Config.memory['shortterm']: self.memory.clear()
        self.memory.add_user_msg(query, attachments, target="openai")
        messages = self.memory.messages
        if skill:
            messages = inject_skill(messages, skill)
        if self.lt_memory is not None:
            messages = inject_memory_context(messages, self.lt_memory.build_context(query))

        if self.coop is not None and self.coop.enable:
            stream = self.coop.run(query, self, base_messages=messages)
        else:
            stream = self._completion(messages)

        reply_parts = []
        for event in stream:
            if isinstance(event, str):
                reply_parts.append(event)
                yield event
                continue

            if isinstance(event, dict) and event.get("type") == "coop":
                self.coop_signal.emit(event)
            yield event

        reply = "".join(reply_parts)
        if reply:
            self.memory.add_assistant_msg(reply)
            if self.lt_memory is not None:
                self.lt_memory.remember_turn(query, reply)
        self.memory_signal.emit([self.model, self.memory.messages])

    def complete(self, messages: list):
        """按给定消息跑一轮，不读写短期记忆。"""
        yield from self._completion(messages)

    def _completion(self, messages: list):
        completion = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            extra_body={"enable_thinking": False},
            stream=True,
            modalities=["text", "audio"],
            audio={"voice": "default", "format": "mp3"},
        )
        for chunk in completion:
            if not chunk.choices: continue

            try:
                delta = chunk.choices[0].delta
            except AttributeError:
                delta = chunk.choices[0].message

            function_call = getattr(delta, "function_call", None)
            if function_call:
                yield {"type": "tool_call",
                       "name": function_call.name,
                       "args": function_call.arguments}
                continue

            # 服务端在流式文本结束后会推一个带完整音频的 chunk
            audio = getattr(delta, "audio", None)
            if audio:
                audio_data = audio.get("data") if isinstance(audio, dict) else getattr(audio, "data", None)
                transcript = audio.get("transcript") if isinstance(audio, dict) else getattr(audio, "transcript", None)
                if audio_data:
                    yield {"type": "audio", "data": audio_data, "transcript": transcript}
                continue

            ans = getattr(delta, "content", None)
            if ans is None: continue
            yield ans
