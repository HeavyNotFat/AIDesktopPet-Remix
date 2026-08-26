import base64
import io

from ..ai import local
from ..ai import cloud

import soundfile
import sounddevice
from PySide6.QtCore import QThread, Signal


class LLMAICallback(QThread):
    tool_event = Signal(dict)
    text_chunk = Signal(str)
    finished = Signal(str)

    def __init__(self, llm_property: local.LLM | cloud.LLM, query: str, parent):
        super().__init__(parent)
        self.llm = llm_property
        self.query = query

    def run(self):
        cache_text = ""
        for event in self.llm.chat(self.query):
            if isinstance(event, str):
                cache_text += event
                self.text_chunk.emit(event)
            elif isinstance(event, dict):
                if event['type'] == "audio":
                    # noinspection PyTypeChecker
                    audio_bytes = base64.b64decode(event["data"])
                    data, samplerate = soundfile.read(io.BytesIO(audio_bytes), dtype="float32")
                    sounddevice.play(data, samplerate)
                else: self.tool_event.emit(event)
        self.finished.emit(cache_text)

