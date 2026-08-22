from .. import SharingData
from .. import analyze_signature

from PySide6.QtCore import Qt, Signal


class Settings(SharingData.theme.Window):
    general_changed = Signal(dict)

    def __init__(self):
        super().__init__()
        self.setTitle(f"AI桌宠 · 重置版 | 设置 | Hacker(黑客)样式")

        general_page = SharingData.theme.general.GeneralPage(self)
        general_page.opacity_changed.connect(lambda value: self.general_changed.emit({"opacity": value}))
        general_page.size_changed.connect(lambda value: self.general_changed.emit({"size": value}))
        general_page.rotate_changed.connect(lambda value: self.general_changed.emit({"rotate": value}))
        general_page.model_live2d.connect(lambda value: self.general_changed.emit({"model_live2d": value}))
        analyze_signature(self.addNavigation, text=general_page.windowTitle(), widget=general_page,
                          shortcut_keys=(Qt.Key_Control, Qt.Key_1)).run()
        llm_page = SharingData.theme.llm.LLMPage(self)
        analyze_signature(self.addNavigation, text=llm_page.windowTitle(), widget=llm_page,
                          shortcut_keys=(Qt.Key_Control, Qt.Key_2)).run()
        tts_page = SharingData.theme.tts.TTSPage(self)
        analyze_signature(self.addNavigation, text=tts_page.windowTitle(), widget=tts_page,
                          shortcut_keys=(Qt.Key_Control, Qt.Key_3)).run()
        animation_pag = SharingData.theme.animation.AnimationPage(self)
        analyze_signature(self.addNavigation, text=animation_pag.windowTitle(), widget=animation_pag,
                          shortcut_keys=(Qt.Key_Control, Qt.Key_4)).run()

        settings_page = SharingData.theme.settings.SettingsPage(self)
        analyze_signature(self.addNavigation, text=settings_page.windowTitle(), widget=settings_page,
                          shortcut_keys=(Qt.Key_Control, Qt.Key_0), position="bottom").run()

    def closeEvent(self, event):
        self.hide()
        event.ignore()
