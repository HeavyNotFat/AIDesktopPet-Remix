from .. import SharingData, Config
from .. import analyze_signature, get_model_lists, get_translation


class Chat(SharingData.theme.Window):
    def __init__(self):
        super().__init__()
        self.setTitle(f"AI桌宠 · 重置版 | 聊天 | Hacker(黑客)样式")
        self.init_model()

    def init_model(self):
        if hasattr(self, "create_category"): self.create_category(get_translation("graphics.chat.local"))
        for model in get_model_lists():
            _model_ = SharingData.theme.ModelChat(model.split("/")[-1], model, True, parent=self)
            analyze_signature(self.addNavigation, text=_model_.windowTitle(), widget=_model_, category=get_translation("graphics.chat.local")).run()

        if hasattr(self, "create_category"): self.create_category(get_translation("graphics.chat.api"))
        for model, parameters in Config.models.items():
            _model_ = SharingData.theme.ModelChat(model, parameters['name'], False, parameters['apikey'], parameters['baseurl'], self)
            analyze_signature(self.addNavigation, text=_model_.windowTitle(), widget=_model_, category=get_translation("graphics.chat.api")).run()

    def closeEvent(self, event):
        self.hide()
        event.ignore()

