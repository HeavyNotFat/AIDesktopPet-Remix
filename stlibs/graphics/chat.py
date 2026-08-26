from .. import SharingData, Config
from .. import analyze_signature, get_model_lists


class Chat(SharingData.theme.Window):
    def __init__(self):
        super().__init__()
        self.setTitle(f"AI桌宠 · 重置版 | 聊天 | Hacker(黑客)样式")
        self.init_model()

    def init_model(self):
        if hasattr(self, "create_category"): self.create_category("本地")
        for model in get_model_lists():
            _model_ = SharingData.theme.ModelChat(model.split("/")[-1], model, True, parent=self)
            analyze_signature(self.addNavigation, text=_model_.windowTitle(), widget=_model_, category="本地").run()

        if hasattr(self, "create_category"): self.create_category("云端")
        for model, parameters in Config.models.items():
            _model_ = SharingData.theme.ModelChat(model, parameters['name'], False, parameters['apikey'], parameters['baseurl'], self)
            analyze_signature(self.addNavigation, text=_model_.windowTitle(), widget=_model_, category="云端").run()

    def closeEvent(self, event):
        self.hide()
        event.ignore()

