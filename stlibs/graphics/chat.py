from .. import SharingData, Config
from .. import analyze_signature, get_model_lists, get_translation
from .theme_label import theme_label


class Chat(SharingData.theme.Window):
    def __init__(self):
        super().__init__()
        self.setTitle(f"AI桌宠 · 重置版 | 聊天 | {theme_label()}")
        self.model_widgets = {}
        self.init_model()

    def init_model(self):
        if hasattr(self, "create_category"): self.create_category(get_translation("graphics.chat.local"))
        for model in get_model_lists():
            self.add_model(model.split("/")[-1], model, True)

        if hasattr(self, "create_category"): self.create_category(get_translation("graphics.chat.api"))
        for model, parameters in Config.models.items():
            self.add_model(model, parameters['name'], False, parameters['apikey'], parameters['baseurl'])

    def add_model(self, ai_name, model, is_local, api_key=None, base_url=None):
        widget = SharingData.theme.ModelChat(ai_name, model, is_local, api_key, base_url, self)
        analyze_signature(
            self.addNavigation,
            text=widget.windowTitle(),
            widget=widget,
            category=get_translation("graphics.chat.local" if is_local else "graphics.chat.api"),
        ).run()
        # 键用界面上显示的名字
        self.model_widgets[ai_name] = widget
        return widget

    def find_model(self, select: str | None):
        """按别名找，找不到再按模型名找（本地模型两个名字可能不一样）。"""
        if not select:
            return None
        widget = self.model_widgets.get(select)
        if widget is not None:
            return widget
        for candidate in self.model_widgets.values():
            if getattr(candidate, "model", None) == select:
                return candidate
        return None

    def reload_models(self, select: str | None = None):
        """重新扫描本地与 API 模型。"""
        for widget in list(self.model_widgets.values()):
            self.removeNavigation(widget)
            widget.deleteLater()
        self.model_widgets.clear()

        for text in (get_translation("graphics.chat.local"), get_translation("graphics.chat.api")):
            if hasattr(self, "remove_category"):
                self.remove_category(text)

        self.init_model()

        target = self.find_model(select)
        if target is not None and hasattr(self, "_set_active"):
            self._set_active(target)

        return sorted(self.model_widgets)

    def closeEvent(self, event):
        self.hide()
        event.ignore()
