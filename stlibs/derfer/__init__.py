import base64
import io

from ..ai import local
from ..ai import cloud

import soundfile
import sounddevice
from PySide6.QtCore import QThread, Signal


def decode_audio(data: str, dtype="float32"):
    """base64 音频（云端给的是 mp3）-> (波形, 采样率)。"""
    raw = base64.b64decode(data)
    return soundfile.read(io.BytesIO(raw), dtype=dtype)


def play_audio(data: str):
    samples, samplerate = decode_audio(data)
    sounddevice.play(samples, samplerate)
    return samples, samplerate


class LLMAICallback(QThread):
    tool_event = Signal(dict)
    text_chunk = Signal(str)
    finished = Signal(str)

    def __init__(self, llm_property: local.LLM | cloud.LLM, query: str, parent, skill=None, attachments=None):
        super().__init__(parent)
        self.llm = llm_property
        self.query = query
        self.skill = skill
        self.attachments = attachments or []

    def run(self):
        cache_text = ""
        for event in self.llm.chat(self.query, skill=self.skill, attachments=self.attachments):
            if isinstance(event, str):
                cache_text += event
                self.text_chunk.emit(event)
            elif isinstance(event, dict):
                # 音频也走 tool_event：交给界面决定什么时候播（不再自动播）
                self.tool_event.emit(event)
        self.finished.emit(cache_text)
