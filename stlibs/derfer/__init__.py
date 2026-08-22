from ..ai import local
from ..ai import cloud

from PySide6.QtCore import QThread, Signal


class LLMAICallback(QThread):
    text_chunk = Signal(str)
    tool_event = Signal(dict)
    finished = Signal()

    def __init__(self, llm_property: local.LLM | cloud.LLM, query: str, parent):
        super().__init__(parent)
        self.llm = llm_property
        self.query = query

    def run(self):
        for event in self.llm.chat(self.query):
            if isinstance(event, str):
                self.text_chunk.emit(event)
            elif isinstance(event, dict):
                self.tool_event.emit(event)
        self.finished.emit()

