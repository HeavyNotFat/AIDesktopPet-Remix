
import pytest

import stlibs
from stlibs.ai import build_llm


pytestmark = pytest.mark.ui


def test_ai_off_blocks_llm_construction(monkeypatch):
    monkeypatch.setattr(stlibs.Config, 'ai_enabled', False, raising=False)

    with pytest.raises(RuntimeError):
        build_llm('anything')


def test_ai_off_skips_model_scan(monkeypatch):
    monkeypatch.setattr(stlibs.Config, 'ai_enabled', False, raising=False)

    assert stlibs.get_model_lists() == []


def test_set_ai_enabled_starts_and_stops_service(tmp_path, monkeypatch):
    monkeypatch.setattr(stlibs, 'CONFIG_PATH', str(tmp_path / 'configure.json'))
    monkeypatch.setattr(stlibs.Config, 'ai_enabled', False, raising=False)
    started, stopped = [], []
    monkeypatch.setattr(stlibs, 'start_onlinechat', lambda: started.append(True))
    monkeypatch.setattr(stlibs, 'stop_onlinechat', lambda: stopped.append(True))
    monkeypatch.setattr(stlibs.AnimationLoader, 'save_animation', lambda *args, **kwargs: None)

    class Chat:
        hidden = False

        def hide(self):
            self.hidden = True

        def deleteLater(self):
            return None

    chat = Chat()
    monkeypatch.setattr(stlibs.SharingData, 'chat_window', chat, raising=False)

    assert stlibs.set_ai_enabled(True) is True
    assert started == [True]

    assert stlibs.set_ai_enabled(False) is False
    assert stopped == [True]
    assert chat.hidden is True
    assert stlibs.SharingData.chat_window is None
    assert stlibs.Config.ai_enabled is False


def test_sdk_ai_methods_are_gated(monkeypatch):
    from stlibs.sdk.methods import HostMethods
    from stlibs.sdk.base import SDKMethodError

    monkeypatch.setattr(stlibs.Config, 'ai_enabled', False, raising=False)

    with pytest.raises(SDKMethodError):
        HostMethods.send_to_chat('hi')
    with pytest.raises(SDKMethodError):
        HostMethods.get_chat_history()
    with pytest.raises(SDKMethodError):
        HostMethods.memory_stats()


def test_settings_hides_and_shows_ai_pages(tmp_path, monkeypatch):
    qt = pytest.importorskip('PySide6.QtWidgets')
    monkeypatch.setenv('QT_QPA_PLATFORM', 'offscreen')
    application = qt.QApplication.instance() or qt.QApplication([])

    import importlib

    previous_theme = stlibs.SharingData.theme
    stlibs.Config.ai_enabled = False
    stlibs.SharingData.theme = stlibs.load_theme('breeze')
    module = importlib.import_module('stlibs.graphics.settings')
    monkeypatch.setattr(module, 'set_ai_enabled', lambda value: (setattr(stlibs.Config, 'ai_enabled', bool(value)) or bool(value)))
    window = module.Settings()
    try:
        assert window.llm_page is None and window.tts_page is None
        window.apply_ai_state(True)
        assert window.llm_page is not None and window.tts_page is not None
        assert window.nav_buttons[window.llm_page].isVisibleTo(window)
        window.apply_ai_state(False)
        assert not window.nav_buttons[window.llm_page].isVisibleTo(window)
        assert not window.llm_page.isVisibleTo(window)
    finally:
        window.hide()
        window.deleteLater()
        stlibs.SharingData.theme = previous_theme
        stlibs.Config.ai_enabled = False
        application.processEvents()
