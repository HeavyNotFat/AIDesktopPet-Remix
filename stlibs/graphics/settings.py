from .. import SharingData
from .. import analyze_signature
from ..plugins.pages import PLUGIN_CATEGORY
from .plugin_page import build_plugin_page
from .theme_label import theme_label

from PySide6.QtCore import Qt, Signal


class Settings(SharingData.theme.Window):
    general_changed = Signal(dict)
    live2d_mot_signal = Signal(list)
    live2d_exp_signal = Signal(list)

    def __init__(self):
        super().__init__()
        self.setTitle(f"AI桌宠 · 重置版 | 设置 | {theme_label()}")
        # 页面 id -> (generation, 控件)
        self.plugin_pages = {}

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

        animation_page = SharingData.theme.animation.AnimationPage(self)
        animation_page.live2d_mot_signal.connect(self.live2d_mot_signal.emit)
        animation_page.live2d_exp_signal.connect(self.live2d_exp_signal.emit)
        analyze_signature(self.addNavigation, text=animation_page.windowTitle(), widget=animation_page,
                          shortcut_keys=(Qt.Key_Control, Qt.Key_4)).run()

        # 插件相关的一切都收在「插件」分类下
        self.create_category(PLUGIN_CATEGORY)
        plugins_page = SharingData.theme.plugins.PluginsPage(self)
        analyze_signature(self.addNavigation, text=plugins_page.windowTitle(), widget=plugins_page,
                          shortcut_keys=(Qt.Key_Control, Qt.Key_5), category=PLUGIN_CATEGORY).run()
        self.plugins_page = plugins_page

        settings_page = SharingData.theme.settings.SettingsPage(self)
        analyze_signature(self.addNavigation, text=settings_page.windowTitle(), widget=settings_page,
                          shortcut_keys=(Qt.Key_Control, Qt.Key_0), position="bottom").run()

        registry = plugin_pages_registry()
        if registry is not None:
            registry.bind(self.refresh_plugin_pages)
        self.refresh_plugin_pages()

    def refresh_plugin_pages(self, rebuild: bool = False):
        """同步插件注册的页面到「插件」分类：新增、重建、摘除。"""
        registry = plugin_pages_registry()
        wanted = {spec.id: spec for spec in registry.pages()} if registry is not None else {}

        for page_id, (generation, widget) in list(self.plugin_pages.items()):
            spec = wanted.get(page_id)
            if spec is not None and spec.generation == generation:
                continue
            self.removeNavigation(widget)
            self.plugin_pages.pop(page_id, None)

        for page_id, spec in wanted.items():
            if page_id in self.plugin_pages:
                continue
            widget = build_plugin_page(spec, self)
            analyze_signature(
                self.addNavigation, text=plugin_page_title(spec), widget=widget,
                category=PLUGIN_CATEGORY, position="bottom", icon=plugin_page_icon(spec),
            ).run()
            self.plugin_pages[page_id] = (spec.generation, widget)

    def plugin_page(self, page_id: str):
        """已挂上的插件页面控件。"""
        entry = self.plugin_pages.get(page_id)
        return entry[1] if entry else None

    def show_plugin_page(self, page_id: str) -> bool:
        """切到某个插件页面。"""
        widget = self.plugin_page(page_id)
        if widget is None:
            return False
        self._set_active(widget)
        return True

    def closeEvent(self, event):
        self.hide()
        event.ignore()


def plugin_pages_registry():
    """当前的插件页面注册表，插件系统不可用时返回 None。"""
    from .. import plugin_manager

    try:
        return plugin_manager().pages
    except Exception:  # noqa: BLE001 - 插件系统坏了也要能打开设置窗
        return None


def plugin_page_title(spec) -> str:
    """导航文字：插件名 · 页面标题（标题含插件名就不加前缀）。"""
    name = ""
    from .. import plugin_manager

    try:
        name = plugin_manager().menu_title(spec.plugin)
    except Exception:  # noqa: BLE001
        name = ""

    if not name or name in spec.title:
        return spec.title
    return f"{name} · {spec.title}"


def plugin_page_icon(spec):
    """导航项左边的插件图标，拿不到就是 None。"""
    from .. import plugin_manager

    try:
        return plugin_manager().plugin_icon(spec.plugin, 18)
    except Exception:  # noqa: BLE001 - 图标只是装饰
        return None


__all__ = ["Settings", "plugin_page_icon", "plugin_page_title", "plugin_pages_registry"]
