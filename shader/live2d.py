import ctypes
import os
import sys
import time
import webbrowser
from difflib import get_close_matches
from typing import Literal

from . import ADPOpenGLCanvas
try:
    from .. import stlibs
    from ..stlibs import SharingData, architecture, get_translation
    from ..stlibs.animation_utils import action_at, motion_parts, random_motion
    from ..stlibs.graphics import settings
except ImportError:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import stlibs
    from stlibs import architecture, SharingData, get_translation
    from stlibs.animation_utils import action_at, motion_parts, random_motion
    from stlibs.graphics import settings

from OpenGL import GL
from PySide6.QtGui import QGuiApplication, QIcon, QCursor
from PySide6.QtCore import Qt, QPoint, QTimer

GWL_EX_STYLE: int = -20
WS_EX_TRANSPARENT: int = 0x00000020


def _opacity(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return 1.0
    if value <= 1.0:
        return max(0.0, min(1.0, value))
    return max(0.0, min(1.0, value / 100.0))


class PublicShader(ADPOpenGLCanvas):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DesktopPetRemix - Character Mainloop")
        self.setWindowIcon(QIcon("logo.ico"))
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)

        self.is_transparent_raise = False
        self.current_size = 1000
        self.pet_model: architecture.live2d.LAppModel | None = None
        self.click_in_area, self.click_x, self.click_y = -1, -1, -1
        self.drag_position, self.drag_start_position, self.is_dragging = None, None, None
        self.amount = 0
        self._current_kind = stlibs.character.kind()
        self._press_moved = False
        self._last_hover_action = ""
        self._hovered_at = 0.0
        self._last_interaction = time.monotonic()
        self._last_smart = time.monotonic()
        self._smart_tick = 0

        self.setFixedSize(self.current_size, self.current_size)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

        if getattr(stlibs.SharingData, "setting_window", None) is None:
            stlibs.SharingData.setting_window = settings.Settings()
        window = stlibs.SharingData.setting_window
        window.live2d_mot_signal.connect(lambda data: self.play(*data, type_="mot"))
        window.live2d_exp_signal.connect(lambda data: self.play(*data, type_="exp"))
        window.general_changed.connect(self.realtime_revise_config)
        if stlibs.ai_enabled() and getattr(stlibs.SharingData, "chat_window", None) is None:
            from stlibs.graphics import chat

            stlibs.SharingData.chat_window = chat.Chat()

    def realtime_revise_config(self, config: dict):
        opacity = config.get("opacity", None)
        size = config.get("size", None)
        rotate = config.get("rotate", None)
        model_live2d = config.get("model_live2d", None)
        if opacity is not None:
            stlibs.Config.opacity = opacity
            self.setCanvasOpacity(_opacity(stlibs.Config.opacity))
        if size is not None:
            stlibs.Config.size = size
            if self.pet_model is not None:
                self.pet_model.SetScale(stlibs.Config.size / 100)
        if rotate is not None:
            stlibs.Config.rotate = rotate
            self.setRotationAngle(stlibs.Config.rotate)
        if model_live2d is not None:
            from stlibs import character

            selected = character.resolve(model_live2d)
            if selected is not None and selected.kind != self._current_kind:
                stlibs.notify("形象类型已切换，重启程序后生效", "warning", 3000)
            else:
                self.loadModelEvent(selected.name if selected is not None else model_live2d)

    def set_mouse_transparent(self, is_transparent: bool):
        """设置鼠标穿透 (透明部分可以直接穿过)"""
        if self.is_transparent_raise:
            return
        window_handle = int(self.winId())
        try:
            current_ex_style = ctypes.windll.user32.GetWindowLongW(window_handle, GWL_EX_STYLE)
            if is_transparent:
                new_ex_style = current_ex_style | WS_EX_TRANSPARENT
            else:
                new_ex_style = current_ex_style & ~WS_EX_TRANSPARENT

            ctypes.windll.user32.SetWindowLongW(window_handle, GWL_EX_STYLE, new_ex_style)
        except Exception:
            self.is_transparent_raise = True

    def is_in_live2d_area(self, click_x: int | None = None, click_y: int | None = None):
        """检查是否在模型内"""
        if click_x is None:
            click_x = QCursor.pos().x() - self.x()
        if click_y is None:
            click_y = QCursor.pos().y() - self.y()
        h = self.height()
        try:
            alpha = GL.glReadPixels(click_x * QGuiApplication.primaryScreen().devicePixelRatio(),
                                    (h - click_y) * QGuiApplication.primaryScreen().devicePixelRatio(),
                                    1, 1, GL.GL_RGBA, GL.GL_UNSIGNED_BYTE)[3]
        except GL.error.GLError:
            alpha = 0
        return alpha > 0

    def loadModelEvent(self, model, is_info: bool = False):
        try:
            model_files = os.listdir(f"./resources/character/model/{model}")
            model_json_file = get_close_matches(f"{model}.model.json", model_files)[0]
            SharingData.model_json_path = f"./resources/character/model/{model}/{model_json_file}"
            extension = model_json_file.split(".")[1]
            if extension == "model3":
                if is_info:
                    return 3, SharingData.model_json_path
                if architecture.live2d.LIVE2D_VERSION != 3:
                    architecture.reload(3)
                    self.pet_model = architecture.live2d.LAppModel()
            elif extension == "model":
                if is_info:
                    return 2, SharingData.model_json_path
                if architecture.live2d.LIVE2D_VERSION != 2:
                    architecture.reload(2)
                    self.pet_model = architecture.live2d.LAppModel()
            else:
                raise FileNotFoundError(model)

            if self.pet_model is None:
                self.pet_model = architecture.live2d.LAppModel()
            self.pet_model.LoadModelJson(SharingData.model_json_path)
            self._refresh_model_lists()
            self._play_app_initial()
        except (KeyError, FileNotFoundError, IndexError) as exc:
            stlibs.notify(f"Live2D 模型加载失败：{model}（{type(exc).__name__}）", "error", 4000)

    def _refresh_model_lists(self):
        try:
            parameters = architecture.addon.Live2DParameters(SharingData.model_json_path)
            motions = []
            for group, items in parameters.get_motions.items():
                for item in items:
                    motions.append(f"{group if group else ' '};{item}")
            SharingData.motions = motions
            SharingData.expressions = list(parameters.get_expressions)
        except Exception as exc:  # noqa: BLE001 - 模型信息读不到只影响列表
            print(f"[live2d] 读取动作列表失败：{exc}")
            SharingData.motions = []
            SharingData.expressions = []

    def _play_app_initial(self):
        value = str(getattr(stlibs.Animation, "AppInitial", "") or "").strip()
        if value:
            QTimer.singleShot(200, lambda: self.play(value, type_="mot"))

    def _play_action(self, action):
        if not isinstance(action, dict):
            return
        anim = str(action.get("anim") or "").strip()
        expr = str(action.get("expr") or "").strip()
        if anim:
            self.play(anim, type_="mot")
        if expr:
            self.play(expr, type_="exp")

    def _smart_control(self, now):
        if self.pet_model is None or not getattr(stlibs.Animation, "smart_control", False):
            return
        if now - self._last_interaction < 12 or now - self._last_smart < 18:
            return
        self._last_smart = now
        motion = random_motion(getattr(SharingData, "motions", None))
        if motion:
            self.play(motion, type_="mot")

    def timerEvent(self, a0):
        local_x, local_y = QCursor.pos().x() - self.x(), QCursor.pos().y() - self.y()
        if self.pet_model is not None:
            try:
                self.pet_model.Drag(local_x, local_y)
            except Exception:  # noqa: BLE001
                pass

        inside = self.is_in_live2d_area(local_x, local_y)
        self.click_in_area = inside
        self.set_mouse_transparent(not inside)

        now = time.monotonic()
        if inside and not self.is_dragging:
            label, action = action_at(stlibs.Animation, local_x, local_y, "Torch")
            if label and label != self._last_hover_action and now - self._hovered_at > 1.2:
                self._last_hover_action = label
                self._hovered_at = now
                self._play_action(action)
            elif not label:
                self._last_hover_action = ""
        else:
            self._last_hover_action = ""
        self._smart_control(now)

        if self.amount > 100:
            self.amount = 1
        elif self.amount == 0:
            self.current_size = 700
            self.setFixedSize(self.current_size, self.current_size)

        if self.pet_model is not None:
            self.pet_model.SetScale(stlibs.Config.size / 100)
        self.setCanvasOpacity(_opacity(stlibs.Config.opacity))
        self.setRotationAngle(stlibs.Config.rotate)

        self.amount += 1
        self.update()

    def show_context_menu(self, position):
        def window_visible(window, ui_class):
            if window is None:
                window = ui_class()

            if window.isHidden():
                window.show()
            else:
                window.hide()

        def open_browser():
            webbrowser.open("http://127.0.0.1:52493")

        # 开菜单前清掉拖拽残留，否则后续点击会被当成拖动
        self.reset_drag_state()

        context_menu = stlibs.SharingData.theme.Menu(self)
        self.connect_menu_closed(context_menu)

        setting_visible_action = stlibs.SharingData.theme.Action(get_translation("shader.menu.settings"), self, stlibs.SharingData.theme.IconList.SETTING)
        setting_visible_action.triggered.connect(lambda: window_visible(stlibs.SharingData.setting_window, settings.Settings))
        context_menu.addAction(setting_visible_action)

        context_menu.addSeparator()

        if stlibs.ai_enabled():
            from stlibs.graphics import chat

            chat_action = stlibs.SharingData.theme.Action(get_translation("shader.menu.chat"), self, stlibs.SharingData.theme.IconList.CHAT)
            chat_action.triggered.connect(lambda: window_visible(stlibs.SharingData.chat_window, chat.Chat))
            context_menu.addAction(chat_action)

            online_chat_action = stlibs.SharingData.theme.Action(get_translation("shader.menu.online_chat"), self, stlibs.SharingData.theme.IconList.CHAT)
            online_chat_action.triggered.connect(open_browser)
            context_menu.addAction(online_chat_action)

            context_menu.addSeparator()

        self.add_plugin_actions(context_menu)

        shut_program_action = stlibs.SharingData.theme.Action(get_translation("shader.menu.shut"), self, stlibs.SharingData.theme.IconList.SHUTDOWN)
        shut_program_action.triggered.connect(self.exit_program)
        context_menu.addAction(shut_program_action)

        context_menu.exec(self.mapToGlobal(position))

    def add_plugin_actions(self, context_menu):
        """把插件注册的菜单项挂到右键菜单上。"""
        from stlibs.graphics import menu as menu_module

        return menu_module.add_plugin_menu(context_menu, action_factory=self.plugin_menu_action)

    def connect_menu_closed(self, context_menu):
        """菜单收起时清一次拖拽状态。"""
        signal = getattr(context_menu, "menu_closed", None)
        if signal is None or getattr(context_menu, "_pet_drag_reset_hooked", False):
            return
        signal.connect(self.reset_drag_state)
        context_menu._pet_drag_reset_hooked = True

    def reset_drag_state(self):
        """清掉拖拽残留状态。"""
        self.is_dragging = False
        self.drag_position = None
        self.drag_start_position = None

    def plugin_menu_action(self, text, icon):
        """主题的 Action 工厂。"""
        return stlibs.SharingData.theme.Action(text, self, icon)

    def run_plugin_action(self, action: str):
        from stlibs.graphics import menu as menu_module

        return menu_module.trigger_plugin_action(action)

    @staticmethod
    def emit_sdk_event(name: str, data=None):
        """把桌宠动作广播给 SDK 事件订阅者。"""
        stlibs.emit_sdk_event(name, data)

    def mousePressEvent(self, event):
        x, y = event.globalPosition().x(), event.globalPosition().y()
        local_x, local_y = event.position().x(), event.position().y()

        if event.button() == Qt.LeftButton:
            if self.is_in_live2d_area(QCursor.pos().x() - self.x(), QCursor.pos().y() - self.y()):
                if SharingData.coordinates[0] == -1 and SharingData.coordinates[1] == -1:
                    SharingData.coordinates[0] = int(local_x)
                    SharingData.coordinates[1] = int(local_y)
                elif SharingData.coordinates[2] == -1 and SharingData.coordinates[3] == -1:
                    SharingData.coordinates[2] = int(local_x)
                    SharingData.coordinates[3] = int(local_y)
                SharingData.coordinates[4] = "live2d"

                self.is_dragging = True
                self.click_in_area = True
                self.click_x, self.click_y = x, y
                self._last_interaction = time.monotonic()
            else:
                self.is_dragging = False

            self._press_moved = False
            self.drag_position = event.globalPosition() - self.frameGeometry().topLeft()
            self.drag_start_position = QPoint(event.globalPosition().x(), event.globalPosition().y())
        else:
            self.is_dragging = False
            self.drag_position = None
            self.drag_start_position = None
        event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and self.drag_position is not None:
            if self.is_dragging:
                new_pos = event.globalPosition() - self.drag_position
                if (new_pos - self.frameGeometry().topLeft()).manhattanLength() > 3:
                    self._press_moved = True
                self.move(int(new_pos.x()), int(new_pos.y()))
            event.accept()

    def mouseReleaseEvent(self, event):
        was_click = (
            event.button() == Qt.MouseButton.LeftButton
            and self.is_dragging
            and not self._press_moved
            and self.is_in_live2d_area(QCursor.pos().x() - self.x(), QCursor.pos().y() - self.y())
        )
        local_x, local_y = event.position().x(), event.position().y()
        super().mouseReleaseEvent(event)

        if not was_click:
            return

        label, action = action_at(stlibs.Animation, local_x, local_y, "Click")
        self._play_action(action)
        self._last_interaction = time.monotonic()
        self.emit_sdk_event("pet_click", {
            "x": event.globalPosition().x(), "y": event.globalPosition().y(), "action": label,
        })
        try:
            stlibs.plugin_manager().emit_event("pet_click", {"source": "live2d", "action": label})
        except Exception:  # noqa: BLE001 - 插件系统的问题不该影响点击
            pass

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier and self.is_in_live2d_area():
            step = 5 if event.angleDelta().y() > 0 else -5
            value = max(10, min(110, int(stlibs.Config.size) + step))
            stlibs.Config.size = value
            if self.pet_model is not None:
                self.pet_model.SetScale(value / 100)
            stlibs.ConfigLoader.save_config()
            self.update()
            event.accept()
            return
        super().wheelEvent(event)

    def play(self, name, index: int = 0, *, type_: Literal['exp', 'mot']):
        if self.pet_model is None:
            return
        name = str(name or "").strip()
        if not name or name == " ":
            return
        if type_ == "mot":
            group, parsed_index = motion_parts(name)
            if parsed_index:
                index = parsed_index
            try:
                self.pet_model.StartMotion(group.strip() or name, int(index),
                                           architecture.live2d.MotionPriority.FORCE)
            except Exception as exc:  # noqa: BLE001 - 找不到动作不该崩
                print(f"[live2d] 播放动作失败：{name}：{exc}")
        else:
            try:
                self.pet_model.SetExpression(name)
            except Exception as exc:  # noqa: BLE001
                print(f"[live2d] 播放表情失败：{name}：{exc}")
        self._last_interaction = time.monotonic()

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    def stop(self):
        if self.pet_model is not None:
            try:
                self.pet_model.StopAllMotions()
            except Exception:  # noqa: BLE001 - 不同 live2d 版本方法名可能不同
                pass

    pause_animation = pause
    resume_animation = resume
    stop_animation = stop

    def on_init(self):
        architecture.live2d.glewInit()
        self.pet_model = architecture.live2d.LAppModel()
        self.loadModelEvent(stlibs.Config.model_live2d)
        self.startTimer(0)

    def on_resize(self, width, height):
        if self.pet_model is not None:
            self.pet_model.Resize(width, height)

    def on_draw(self):
        if self.pet_model is None or getattr(self, "_paused", False):
            return
        architecture.live2d.clearBuffer()
        try:
            self.pet_model.Update()
            self.pet_model.Draw()
        except SystemError:
            pass

    def exit_program(self):
        value = str(getattr(stlibs.Animation, "AppExit", "") or "").strip()
        if value:
            self.play(value, type_="mot")
            QTimer.singleShot(800, self._finish_exit)
        else:
            self._finish_exit()

    def _finish_exit(self):
        architecture.live2d.dispose()
        self.close()
        os.kill(os.getpid(), __import__("signal").SIGINT)
