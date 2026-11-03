import ctypes
import json
import os
import sys
import webbrowser

from PySide6.QtCore import QPoint, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QCursor, QIcon
from PySide6.QtWidgets import QWidget

try:
    from .. import stlibs
    from ..stlibs.action_map import MAPPING_ANIMATION
    from ..stlibs.animation_utils import random_motion
    from ..stlibs.emote import bootstrap, discover_models, find_model
    from ..stlibs.graphics import settings
except ImportError:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import stlibs
    from stlibs.action_map import MAPPING_ANIMATION
    from stlibs.animation_utils import random_motion
    from stlibs.emote import bootstrap, discover_models, find_model
    from stlibs.graphics import settings

try:
    from stlibs.emote.scheme import BASE_URL, install_handler, register_scheme

    _SCHEME_AVAILABLE = True
except Exception:  # noqa: BLE001 - 没有 QtWebEngine 时退回 HTTP
    BASE_URL = ""
    install_handler = None
    register_scheme = None
    _SCHEME_AVAILABLE = False


GWL_EX_STYLE = -20
WS_EX_TRANSPARENT = 0x00000020

WINDOW_WIDTH = 720
WINDOW_HEIGHT = 1000


def normalized_opacity(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return 1.0
    if value <= 1.0:
        return max(0.0, min(1.0, value))
    return max(0.0, min(1.0, value / 100.0))


class _Overlay(QWidget):
    def __init__(self, host):
        super().__init__(host)
        self.host = host
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setMouseTracking(True)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(host.show_context_menu)

    def paintEvent(self, event):
        return

    def mousePressEvent(self, event):
        self.host.handle_press(event)

    def mouseMoveEvent(self, event):
        self.host.handle_move(event)

    def mouseReleaseEvent(self, event):
        self.host.handle_release(event)

    def wheelEvent(self, event):
        self.host.handle_wheel(event)


class PublicShader(QWidget):
    def __init__(self):
        super().__init__()
        try:
            from PySide6.QtWebEngineCore import QWebEngineSettings
            from PySide6.QtWebEngineWidgets import QWebEngineView
        except ImportError as exc:
            raise RuntimeError('Emote 形象需要 PySide6-WebEngine') from exc

        self.setWindowTitle('DesktopPetRemix - Character Mainloop')
        self.setWindowIcon(QIcon('logo.ico'))
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self.setFixedSize(WINDOW_WIDTH, WINDOW_HEIGHT)

        self.is_transparent_raise = False
        self.is_dragging = False
        self.drag_position = None
        self.drag_start_position = None
        self.click_in_area = False
        self._hit = True
        self._ready = False
        self._state = {}
        self._page_loaded = False
        self._handler = None
        self._http_server = None
        self._http_bootstrap = {}
        self._tried_http = False
        self._tried_content = False
        self._current_model = None
        self._actions_signature = ""
        self._last_mouse_transparent = None
        self._hover_action = ''
        self._press_moved = False
        self._last_interaction = __import__('time').monotonic()
        self._last_smart = __import__('time').monotonic()

        if _SCHEME_AVAILABLE:
            try:
                register_scheme()
            except Exception as exc:  # noqa: BLE001 - 协议注册失败时给出可见提示
                print(f"[emote] 注册私有协议失败：{exc}")

        self._view = QWebEngineView(self)
        self._view.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._view.setContextMenuPolicy(Qt.NoContextMenu)
        self._view.setStyleSheet('background: transparent;')
        self._page = self._view.page()
        self._page.setBackgroundColor(QColor(0, 0, 0, 0))
        settings_obj = self._page.settings()
        settings_obj.setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)
        settings_obj.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings_obj.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, False)
        try:
            settings_obj.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
        except AttributeError:
            pass
        self._view.loadFinished.connect(self._on_load_finished)
        self._page.renderProcessTerminated.connect(self._on_render_terminated)

        self._overlay = _Overlay(self)
        self._overlay.setGeometry(self.rect())
        self._overlay.raise_()
        self._overlay.show()

        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

        self._state_timer = QTimer(self)
        self._state_timer.timeout.connect(self._poll_state)
        self._state_timer.start(250)

        self._track_timer = QTimer(self)
        self._track_timer.timeout.connect(self._track_cursor)
        self._track_timer.start(max(20, int(getattr(stlibs.Config, 'emote_tracking_interval', 50) or 50)))

        self.setWindowOpacity(normalized_opacity(stlibs.Config.opacity))
        self.startTimer(100)
        self._setup_windows()
        self._load_model(stlibs.Config.model_emote)

    def _setup_windows(self):
        if getattr(stlibs.SharingData, 'setting_window', None) is None:
            stlibs.SharingData.setting_window = settings.Settings()
        setting_window = stlibs.SharingData.setting_window
        if hasattr(setting_window, 'general_changed'):
            setting_window.general_changed.connect(self.realtime_revise_config)
        if hasattr(setting_window, 'live2d_mot_signal'):
            setting_window.live2d_mot_signal.connect(lambda data: self.play(*data, type_='mot'))
        if hasattr(setting_window, 'live2d_exp_signal'):
            setting_window.live2d_exp_signal.connect(lambda data: self.play(*data, type_='exp'))
        if hasattr(setting_window, 'emote_timeline_signal'):
            setting_window.emote_timeline_signal.connect(self.play_emote_timeline)
        if hasattr(setting_window, 'static_anim_signal'):
            setting_window.static_anim_signal.connect(lambda name: self.play(name))
        if stlibs.ai_enabled():
            self._ensure_chat_window()

    @staticmethod
    def _ensure_chat_window():
        if not stlibs.ai_enabled():
            return None
        window = stlibs.SharingData.chat_window
        if window is None:
            from stlibs.graphics import chat

            window = chat.Chat()
            stlibs.SharingData.chat_window = window
        return window

    def reload_model(self):
        self._load_model(stlibs.Config.model_emote)

    def _load_model(self, name=None):
        model = find_model(name) or (discover_models()[0] if discover_models() else None)
        if model is None:
            self._show_error('没有找到 Emote 模型，请把 .psb / .psb.zip 放进 resources/character/emote')
            return
        self._current_model = model
        stlibs.Config.model_emote = model.name
        data = bootstrap(
            model,
            stlibs.Config.size,
            1.0,
            stlibs.Config.rotate,
            stlibs.Config.emote_render_ratio,
            stlibs.Config.emote_tracking_interval,
        )
        self._http_bootstrap = dict(data)
        self._tried_http = False
        self._tried_content = False
        self._ready = False
        self._page_loaded = False
        self._actions_signature = ""
        stlibs.SharingData.emote_state = {}
        if not _SCHEME_AVAILABLE:
            self._start_http_fallback()
            return
        data["modelUrl"] = BASE_URL + data["modelUrl"]
        data["configUrl"] = BASE_URL + data["configUrl"] if data.get("configUrl") else ""
        try:
            if self._handler is None:
                self._handler = install_handler(data)
            else:
                self._handler.set_bootstrap(data)
            self._ready = False
            self._page_loaded = False
            self._view.load(QUrl(BASE_URL + 'index.html'))
        except Exception as exc:  # noqa: BLE001
            self._show_error(f'Emote 页面初始化失败：{exc}')

    def _show_error(self, message):
        print(f'[emote] {message}')
        stlibs.notify(message, 'error', 5000)

    def _on_load_finished(self, ok):
        self._page_loaded = bool(ok)
        self._overlay.raise_()
        print(f'[emote] loadFinished={ok} url={self._view.url().toString()} '
              f'error={self._state.get("error", "")}')
        if ok:
            return
        if not self._tried_http:
            self._start_http_fallback()
            return
        if not self._tried_content:
            self._start_content_fallback()
            return
        self._show_error('Emote 页面加载失败（WebEngine 无法访问本地资源）')

    def _start_content_fallback(self):
        """HTTP 也不可用时，把运行时/模型/config 全内联进页面加载。"""
        self._tried_content = True
        try:
            from PySide6.QtCore import QByteArray

            from stlibs.emote.render import inline_page

            html = inline_page(
                self._current_model,
                stlibs.Config.size,
                1.0,
                stlibs.Config.rotate,
                stlibs.Config.emote_render_ratio,
                stlibs.Config.emote_tracking_interval,
            )
            self._ready = False
            self._page_loaded = False
            self._page.setContent(QByteArray(html), 'text/html', QUrl('about:blank'))
        except Exception as exc:  # noqa: BLE001
            self._show_error(f'Emote 内联页面加载失败：{exc}')

    def _start_http_fallback(self):
        """私有协议不可用时退回本地 HTTP，和参考实现一致。"""
        self._tried_http = True
        try:
            from stlibs.emote.server import EmoteAssetServer

            if self._http_server is None:
                self._http_server = EmoteAssetServer(self._http_bootstrap).start()
            else:
                self._http_server.set_bootstrap(self._http_bootstrap)
            self._view.load(QUrl(self._http_server.base_url + '/'))
        except Exception as exc:  # noqa: BLE001
            self._show_error(f'Emote 本地服务启动失败：{exc}')

    def _on_render_terminated(self, status, code):
        self._page_loaded = False
        print(f'[emote] render terminated status={status} code={code} '
              f'url={self._view.url().toString()} error={self._state.get("error", "")}')
        self._show_error(f'Emote 渲染进程退出（{status}, {code}）')

    def _poll_state(self):
        if not self._page_loaded or self._view.page() is None:
            return
        self._view.page().runJavaScript('window.emoteStateJson ? window.emoteStateJson() : \'\'', self._on_state)

    def _on_state(self, raw):
        if not raw:
            return
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            return
        self._sync_actions()
        self._state = data
        stlibs.SharingData.emote_state = data
        self._smart_control()
        if data.get('error') and not data.get('ready'):
            self._state['last_error'] = data.get('error')
            return
        if not data.get('ready') or self._ready:
            return
        self._ready = True
        stlibs.SharingData.motions = list(data.get('mainTimelines') or [])
        stlibs.SharingData.expressions = list(data.get('diffTimelines') or [])
        self._sync_actions()
        self._apply_appearance()
        self._play_app_initial()

    def _sync_actions(self):
        if not self._page_loaded or self._view.page() is None:
            return
        payload = {}
        for attr in MAPPING_ANIMATION.values():
            value = getattr(stlibs.Animation, attr, None)
            if isinstance(value, dict):
                payload[attr] = value
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        if serialized == self._actions_signature:
            return
        self._actions_signature = serialized
        script = 'window.emoteUpdateActions(' + serialized + ');'
        self._view.page().runJavaScript(script)

    def _play_app_initial(self):
        value = str(getattr(stlibs.Animation, 'AppInitial', '') or '').strip()
        if value:
            self.play_emote_timeline([value, 0])

    def _apply_appearance(self):
        if self._view.page() is None:
            return
        self.setWindowOpacity(normalized_opacity(stlibs.Config.opacity))
        size = max(10, min(200, int(stlibs.Config.size)))
        rotate = float(stlibs.Config.rotate)
        self._view.page().runJavaScript(f'window.emoteSetScale && emoteSetScale({size});')
        self._view.page().runJavaScript(f'window.emoteSetRotation && emoteSetRotation({rotate});')

    def realtime_revise_config(self, config):
        if not isinstance(config, dict):
            return
        if 'opacity' in config:
            stlibs.Config.opacity = config['opacity']
            self.setWindowOpacity(normalized_opacity(config['opacity']))
        if 'size' in config:
            stlibs.Config.size = config['size']
            if self._view.page() is not None:
                self._view.page().runJavaScript(f'window.emoteSetScale && emoteSetScale({int(config["size"])});')
        if 'rotate' in config:
            stlibs.Config.rotate = config['rotate']
            if self._view.page() is not None:
                self._view.page().runJavaScript(f'window.emoteSetRotation && emoteSetRotation({float(config["rotate"])});')
            
        target = config.get('model_live2d')
        if target:
            from stlibs import character

            selected = character.resolve(target)
            if selected is not None and selected.kind == character.EMOTE:
                self._load_model(selected.name)
            elif selected is not None:
                stlibs.notify('形象类型已切换，重启程序后生效', 'warning', 3000)
        self._sync_actions()

    def _track_cursor(self):
        if not self.isVisible() or self._view.page() is None:
            return
        cursor = QCursor.pos()
        local_x = cursor.x() - self.x()
        local_y = cursor.y() - self.y()
        inside = 0 <= local_x < self.width() and 0 <= local_y < self.height()
        if inside:
            center_x = self.x() + self.width() / 2
            center_y = self.y() + self.height() / 2
            nx = max(-1.0, min(1.0, (cursor.x() - center_x) / 1000.0))
            ny = max(-1.0, min(1.0, (cursor.y() - center_y) / 800.0))
            self._view.page().runJavaScript(f'window.emoteSetEyeTracking && emoteSetEyeTracking({nx:.3f}, {ny:.3f});')
            self._view.page().runJavaScript(
                f'window.emoteHitTest && emoteHitTest({local_x}, {local_y})', self._on_hit_test
            )
        elif self._last_mouse_transparent is not True:
            self.set_mouse_transparent(True)

    def _on_hit_test(self, value):
        self._hit = bool(value)
        self.click_in_area = self._hit
        self.set_mouse_transparent(not self._hit)

    def _smart_control(self):
        if not self._ready or not getattr(stlibs.Animation, 'smart_control', False):
            return
        import time

        now = time.monotonic()
        if now - self._last_interaction < 12 or now - self._last_smart < 20:
            return
        values = list(getattr(stlibs.SharingData, 'motions', None) or [])
        if not values:
            return
        self._last_smart = now
        self.play_emote_timeline([random_motion(values), 0])

    def set_mouse_transparent(self, is_transparent):
        if self.is_transparent_raise or self._last_mouse_transparent == is_transparent:
            return
        self._last_mouse_transparent = is_transparent
        if sys.platform != 'win32':
            return
        try:
            handle = int(self.winId())
            current = ctypes.windll.user32.GetWindowLongW(handle, GWL_EX_STYLE)
            if is_transparent:
                new_style = current | WS_EX_TRANSPARENT
            else:
                new_style = current & ~WS_EX_TRANSPARENT
            ctypes.windll.user32.SetWindowLongW(handle, GWL_EX_STYLE, new_style)
        except Exception:  # noqa: BLE001
            self.is_transparent_raise = True

    def is_in_animation_area(self, click_x=None, click_y=None):
        if click_x is None or click_y is None:
            return self._hit
        return self._hit

    is_in_live2d_area = is_in_animation_area

    def handle_press(self, event):
        global_x, global_y = event.globalPosition().x(), event.globalPosition().y()
        local_x, local_y = event.position().x(), event.position().y()
        self.set_mouse_transparent(False)
        if event.button() == Qt.LeftButton:
            if self._hit:
                self.is_dragging = True
                self.click_in_area = True
                self._record_coordinates(int(local_x), int(local_y))
            else:
                self.is_dragging = False
            self.drag_position = event.globalPosition() - self.frameGeometry().topLeft()
            self.drag_start_position = QPoint(int(global_x), int(global_y))
            self._press_moved = False
        else:
            self.is_dragging = False
            self.drag_position = None
            self.drag_start_position = None
        self._last_press = (local_x, local_y)
        event.accept()

    def handle_move(self, event):
        if event.buttons() & Qt.LeftButton and self.drag_position is not None and self.is_dragging:
            new_pos = event.globalPosition() - self.drag_position
            if (new_pos - self.frameGeometry().topLeft()).manhattanLength() > 3:
                self._press_moved = True
            self.move(int(new_pos.x()), int(new_pos.y()))
            event.accept()
            return
        local_x, local_y = event.position().x(), event.position().y()
        if self._view.page() is not None:
            self._view.page().runJavaScript(f'window.emoteHitTest && emoteHitTest({local_x}, {local_y})', self._on_hit_test)
        event.accept()

    def handle_release(self, event):
        was_click = event.button() == Qt.LeftButton and self.is_dragging and not self._press_moved
        if event.button() == Qt.LeftButton:
            self.drag_position = None
            self.drag_start_position = None
            self.is_dragging = False
        local_x, local_y = event.position().x(), event.position().y()
        if was_click and self._hit and self._view.page() is not None:
            import time

            self._last_interaction = time.monotonic()
            self._view.page().runJavaScript(f'window.emoteHandleClick && emoteHandleClick({local_x}, {local_y})')
            self.notify_clicked(event)
        event.accept()

    def handle_wheel(self, event):
        if event.modifiers() & Qt.ControlModifier and self._hit:
            step = 5 if event.angleDelta().y() > 0 else -5
            value = max(10, min(110, int(stlibs.Config.size) + step))
            stlibs.Config.size = value
            if self._view.page() is not None:
                self._view.page().runJavaScript(f'window.emoteSetScale && emoteSetScale({value});')
            stlibs.ConfigLoader.save_config()
            event.accept()
            return
        event.ignore()

    def _record_coordinates(self, x, y):
        coordinates = stlibs.SharingData.coordinates
        if coordinates[0] == -1:
            coordinates[0], coordinates[1] = x, y
        elif coordinates[2] == -1:
            coordinates[2], coordinates[3] = x, y
        coordinates[4] = 'emote'

    def timerEvent(self, event):
        return

    def play_emote_timeline(self, data):
        if not isinstance(data, (list, tuple)) or not data:
            return
        label = str(data[0] or '')
        try:
            slot = int(data[1]) if len(data) > 1 else 0
        except (TypeError, ValueError):
            slot = 0
        self._run_js('emotePlayTimeline', json.dumps(label, ensure_ascii=False), slot)

    def play(self, name, index=0, *, type_='mot'):
        if type_ == 'exp':
            self.play_emote_timeline([name, 1])
        else:
            self.play_emote_timeline([name, 0])

    def pause(self):
        self._run_js('emoteSetSpeed', 0)

    def resume(self):
        self._run_js('emoteSetSpeed', 1)

    def stop(self):
        self.play_emote_timeline(['', 0])
        self.play_emote_timeline(['', 1])

    pause_animation = pause
    resume_animation = resume
    stop_animation = stop

    def _run_js(self, function, *args):
        if self._view.page() is None:
            return
        payload = ', '.join(str(item) for item in args)
        self._view.page().runJavaScript(f'window.{function} && {function}({payload});')

    def setCanvasOpacity(self, value):
        self.setWindowOpacity(normalized_opacity(value))

    def setRotationAngle(self, angle):
        stlibs.Config.rotate = angle
        self._run_js('emoteSetRotation', float(angle))

    def set_emote_variable(self, name, value, duration=0, module=""):
        if module:
            self._run_js('emoteSetVariableDiff', json.dumps(str(module), ensure_ascii=False),
                         json.dumps(str(name), ensure_ascii=False), float(value), duration)
        else:
            self._run_js('emoteSetVariable', json.dumps(str(name), ensure_ascii=False),
                         float(value), duration)

    def notify_clicked(self, event):
        self.emit_sdk_event('pet_click', {
            'x': event.globalPosition().x(), 'y': event.globalPosition().y(), 'source': 'emote',
        })
        try:
            stlibs.plugin_manager().emit_event('pet_click', {'source': 'emote'})
        except Exception:  # noqa: BLE001
            pass

    @staticmethod
    def emit_sdk_event(name, data=None):
        stlibs.emit_sdk_event(name, data)

    def show_context_menu(self, position):
        self.reset_drag_state()
        context_menu = stlibs.SharingData.theme.Menu(self)
        self.connect_menu_closed(context_menu)

        settings_action = stlibs.SharingData.theme.Action('设置', self, stlibs.SharingData.theme.IconList.SETTING)
        settings_action.triggered.connect(self.show_settings)
        context_menu.addAction(settings_action)

        context_menu.addSeparator()
        if stlibs.ai_enabled():
            chat_action = stlibs.SharingData.theme.Action('聊天', self, stlibs.SharingData.theme.IconList.CHAT)
            chat_action.triggered.connect(self.show_chat)
            context_menu.addAction(chat_action)
            online_action = stlibs.SharingData.theme.Action('网页聊天', self, stlibs.SharingData.theme.IconList.CHAT)
            online_action.triggered.connect(lambda: webbrowser.open('http://127.0.0.1:52493'))
            context_menu.addAction(online_action)
            context_menu.addSeparator()

        play_action = stlibs.SharingData.theme.Action('随机动作', self)
        play_action.triggered.connect(self.play_random)
        context_menu.addAction(play_action)

        reload_action = stlibs.SharingData.theme.Action('重载模型', self)
        reload_action.triggered.connect(lambda: self._load_model(stlibs.Config.model_emote))
        context_menu.addAction(reload_action)

        self.add_plugin_actions(context_menu)
        shut_action = stlibs.SharingData.theme.Action('关闭', self, stlibs.SharingData.theme.IconList.SHUTDOWN)
        shut_action.triggered.connect(self.exit_program)
        context_menu.addAction(shut_action)
        context_menu.exec(self.mapToGlobal(position))

    def show_settings(self):
        window = stlibs.SharingData.setting_window
        if window is None:
            return
        if window.isHidden():
            window.show()
            window.raise_()
            window.activateWindow()
        else:
            window.hide()

    def show_chat(self):
        window = self._ensure_chat_window()
        if window is None:
            return
        if window.isHidden():
            window.show()
            window.raise_()
            window.activateWindow()
        else:
            window.hide()

    def play_random(self):
        value = random_motion(getattr(stlibs.SharingData, 'motions', None))
        if value:
            self.play(value)

    def add_plugin_actions(self, context_menu):
        from stlibs.graphics import menu as menu_module

        return menu_module.add_plugin_menu(context_menu, action_factory=self.plugin_menu_action)

    def connect_menu_closed(self, context_menu):
        signal = getattr(context_menu, 'menu_closed', None)
        if signal is None or getattr(context_menu, '_pet_drag_reset_hooked', False):
            return
        signal.connect(self.reset_drag_state)
        context_menu._pet_drag_reset_hooked = True

    def reset_drag_state(self):
        self.drag_position = None
        self.drag_start_position = None
        self.is_dragging = False
        host_reset = getattr(self, 'reset_host_drag_state', None)
        if callable(host_reset):
            host_reset()

    def plugin_menu_action(self, text, icon):
        return stlibs.SharingData.theme.Action(text, self, icon)

    def run_plugin_action(self, action):
        from stlibs.graphics import menu as menu_module

        return menu_module.trigger_plugin_action(action)

    def mousePressEvent(self, event):
        self.handle_press(event)

    def mouseMoveEvent(self, event):
        self.handle_move(event)

    def mouseReleaseEvent(self, event):
        self.handle_release(event)

    def wheelEvent(self, event):
        self.handle_wheel(event)

    def resizeEvent(self, event):
        if hasattr(self, '_view'):
            self._view.setGeometry(self.rect())
        if hasattr(self, '_overlay'):
            self._overlay.setGeometry(self.rect())
            self._overlay.raise_()
        super().resizeEvent(event)

    def closeEvent(self, event):
        self._state_timer.stop()
        self._track_timer.stop()
        if self._http_server is not None:
            self._http_server.stop()
            self._http_server = None
        super().closeEvent(event)

    def exit_program(self):
        value = str(getattr(stlibs.Animation, 'AppExit', '') or '').strip()
        if value:
            self.play_emote_timeline([value, 0])
            QTimer.singleShot(800, self._finish_exit)
        else:
            self._finish_exit()

    def _finish_exit(self):
        if self._http_server is not None:
            self._http_server.stop()
            self._http_server = None
        self.close()
        os.kill(os.getpid(), __import__('signal').SIGINT)
