from PySide6.QtWidgets import QWidget, QVBoxLayout

from ..ai import local
from ..ai import cloud
from .. import derfer
from .. import SharingData, Config
from .. import analyze_signature, get_model_lists

cache_llm_class = {}


class ModelChat(QWidget):
    def __init__(
        self,
        ai_name: str, model: str,
        is_local: bool,
        api_key: str = None,
        base_url: str = None,
        parent=None,
    ):
        super().__init__(parent)
        if is_local:
            if model in cache_llm_class.keys():
                self.ai_llm = cache_llm_class[model]
            else:
                self.ai_llm = local.LLM(model)
                cache_llm_class[model] = self.ai_llm
        else:
            if model in cache_llm_class.keys():
                self.ai_llm = cache_llm_class[model]
            else:
                self.ai_llm = cloud.LLM(model, api_key, base_url)
                cache_llm_class[model] = self.ai_llm
        self.ai_llm.memory_signal.connect(SharingData.add_memory_to_ui[model])

        self.setWindowTitle(ai_name)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        title = SharingData.theme.Label("AI TERMINAL")
        title.setFixedHeight(30)
        layout.addWidget(title)

        self.chat = SharingData.theme.ChatWidget()
        self.chat.userInputSignal.connect(self.add_user_msg)

        layout.addWidget(self.chat)

        self.current_assistant_bubble = None

    def chat_finished(self):
        self.chat.enable_send_button()

    def add_user_msg(self, msg: str):
        self.current_assistant_bubble = self.chat.add_assistant_msg()
        self.chat.disable_send_button()

        t = derfer.LLMAICallback(self.ai_llm, msg, self)
        t.finished.connect(self.chat_finished)
        t.text_chunk.connect(self.add_assistant_msg)
        t.start()

    def add_assistant_msg(self, msg: str):
        if not msg:
            return

        if self.current_assistant_bubble is not None:
            self.current_assistant_bubble.append_text(msg)
            self.chat.update_bubble_widths()
            self.chat.scroll_to_bottom()


class Chat(SharingData.theme.Window):
    def __init__(self):
        super().__init__()
        self.setTitle(f"AI桌宠 · 重置版 | 聊天 | Hacker(黑客)样式")
        self.init_model()

    def init_model(self):
        if hasattr(self, "create_category"): self.create_category("本地")
        for model in get_model_lists():
            _model_ = ModelChat(model.split("/")[-1], model, True, parent=self)
            analyze_signature(self.addNavigation, text=_model_.windowTitle(), widget=_model_, category="本地").run()

        if hasattr(self, "create_category"): self.create_category("云端")
        for model, parameters in Config.models.items():
            _model_ = ModelChat(model, parameters['name'], False, parameters['apikey'], parameters['baseurl'], self)
            analyze_signature(self.addNavigation, text=_model_.windowTitle(), widget=_model_, category="云端").run()

    def closeEvent(self, event):
        self.hide()
        event.ignore()

