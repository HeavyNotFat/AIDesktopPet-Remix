import ctypes
import os
import random
import sys
import time

from PIL import Image

from PySide6.QtCore import Qt, QPoint, QTimer
from PySide6.QtGui import QIcon, QCursor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QWidget

try:
    from .. import stlibs
    from ..stlibs.animation_utils import action_at
    from ..stlibs.graphics import settings
except ImportError:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import stlibs
    from stlibs.animation_utils import action_at
    from stlibs.graphics import settings


GWL_EX_STYLE = -20
WS_EX_TRANSPARENT = 0x00000020


def _opacity(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return 1.0
    if value <= 1.0:
        return max(0.0, min(1.0, value))
    return max(0.0, min(1.0, value / 100.0))


class PublicShader(QWidget):
    IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".bmp")

    def __init__(self, frames: dict | None = None, fps: int = 12, parent=None):
        super().__init__(parent)
        self.setWindowTitle("DesktopPetRemix - Character Mainloop")
        self.setWindowIcon(QIcon("logo.ico"))
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)

        self.is_transparent_raise = False
        self.current_size = 1000
        self.click_in_area = False
        self.click_x = -1
        self.click_y = -1
        self.drag_position = None
        self.drag_start_position = None
        self.is_dragging = False
        self.amount = 0
        self._current_kind = stlibs.character.kind()
        self._press_moved = False
        self._last_hover_action = ""
        self._hovered_at = 0.0
        self._last_interaction = time.monotonic()
        self._last_smart = time.monotonic()
        self._paused = False

        if frames is None:
            try:
                models = stlibs.SharingData.static_models
                frames = models.get(stlibs.Config.static_model) or {}
            except Exception:  # noqa: BLE001
                frames = {}
        self.frames_config = frames or {}
        self.animations = {}
        self.current_animation = None
        self.current_frames = []
        self.current_frame = 0
        self.current_op = None
        self.fps = max(1, int(fps))
        self.animation_loop = True
        self.animation_playing = False

        self.current_image = None
        self.current_pixmap = None
        self.image_cache = {}

        self.offset_x = 0
        self.offset_y = 0

        self.animation_timer = QTimer(self)
        self.animation_timer.timeout.connect(self.next_frame)

        self.setFixedSize(self.current_size, self.current_size)

        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

        self.startTimer(50)

        new_size = int(self.current_size * float(stlibs.Config.size) / 100)
        new_size = max(100, min(new_size, 2000))
        self.setFixedSize(new_size, new_size)
        self.setWindowOpacity(_opacity(stlibs.Config.opacity))
        self._init_sharing_data()
        self._load_animation_frames()
        self._play_app_initial()

    def _play_app_initial(self):
        value = str(getattr(stlibs.Animation, "AppInitial", "") or "").strip()
        name = value or ("idle" if "idle" in self.animations else next(iter(self.animations), ""))
        if not name:
            return
        try:
            self.play(name)
        except (KeyError, ValueError):
            pass

    def _init_sharing_data(self):
        if getattr(stlibs.SharingData, "setting_window", None) is None:
            stlibs.SharingData.setting_window = settings.Settings()

        window = stlibs.SharingData.setting_window
        if hasattr(window, "general_changed"):
            window.general_changed.connect(self.realtime_revise_config)
        if hasattr(window, "static_anim_signal"):
            window.static_anim_signal.connect(self.play)
        if hasattr(window, "live2d_mot_signal"):
            window.live2d_mot_signal.connect(lambda data: self.play(data[0]) if data else None)
        if stlibs.ai_enabled() and getattr(stlibs.SharingData, "chat_window", None) is None:
            from stlibs.graphics import chat

            stlibs.SharingData.chat_window = chat.Chat()

    def realtime_revise_config(self, config: dict):
        if not isinstance(config, dict):
            return

        opacity = config.get("opacity")
        size = config.get("size")
        rotate = config.get("rotate")
        model_live2d = config.get("model_live2d")

        if opacity is not None:
            stlibs.Config.opacity = opacity
            self.setWindowOpacity(_opacity(opacity))

        if size is not None:
            stlibs.Config.size = size
            try:
                new_size = int(1000 * float(size) / 100)
                new_size = max(100, min(new_size, 2000))
                self.setFixedSize(new_size, new_size)
            except (TypeError, ValueError):
                pass

        if rotate is not None:
            stlibs.Config.rotate = rotate
            self.update()

        if model_live2d is not None:
            from stlibs import character

            selected = character.resolve(model_live2d)
            if selected is not None and selected.kind != self._current_kind:
                stlibs.notify("形象类型已切换，重启程序后生效", "warning", 3000)
            elif selected is not None and selected.kind == character.STATIC:
                self.reload_animations(selected.name)

    def _load_animation_frames(self):
        self.animations.clear()
        model = stlibs.Config.static_model
        if not model:
            return

        for animation_name, frame_list in self.frames_config.items():
            if not isinstance(frame_list, dict):
                continue
            folder = os.path.join("./resources/character/static", model, animation_name)
            if not os.path.isdir(folder):
                continue
            frames = frame_list.get("frames")
            if not frames:
                self.animations[animation_name] = {"frames": [], "op": None, "fps": self.fps, "loop": True}
                continue

            has_extension = any(os.path.splitext(str(frame))[1].lower() in self.IMAGE_EXTENSIONS
                                for frame in frames)
            if has_extension:
                self.animations[animation_name] = self._parse_file_list(folder, frame_list)
            else:
                self.animations[animation_name] = self._parse_prefix_list(folder, frame_list)

    @staticmethod
    def _parse_file_list(folder: str, frame_list: list[str]) -> dict:
        result = []
        for filename in frame_list.get("frames") or []:
            path = os.path.join(folder, str(filename))
            if os.path.isfile(path):
                result.append(path)
        return {
            "frames": result,
            "op": frame_list.get("op"),
            "fps": max(1, int(frame_list.get("fps") or 12)),
            "loop": bool(frame_list.get("loop", True)),
        }

    def _parse_prefix_list(self, folder: str, frame_list: list[str]) -> dict:
        result = []
        for prefix in frame_list.get("frames") or []:
            prefix = str(prefix)
            matched = []
            try:
                names = os.listdir(folder)
            except OSError:
                continue
            for filename in names:
                name, ext = os.path.splitext(filename)
                if ext.lower() not in self.IMAGE_EXTENSIONS or not name.startswith(prefix):
                    continue
                suffix = name[len(prefix):]
                number_text = suffix.lstrip("_-")
                if not number_text.isdigit():
                    continue
                matched.append((int(number_text), filename))
            matched.sort(key=lambda item: item[0])
            result.extend(os.path.join(folder, filename) for _index, filename in matched)
        return {
            "frames": result,
            "op": frame_list.get("op"),
            "fps": max(1, int(frame_list.get("fps") or 12)),
            "loop": bool(frame_list.get("loop", True)),
        }

    def reload_animations(self, model: str | None = None):
        if model:
            stlibs.Config.static_model = model
            self.frames_config = stlibs.SharingData.static_models.get(model) or {}
        self._load_animation_frames()
        if not self.animations:
            self.current_frames = []
            self.current_pixmap = None
            self.current_image = None
            self.update()
            return

        target = self.current_animation if self.current_animation in self.animations else next(iter(self.animations))
        self.image_cache.clear()
        try:
            self.play(target, restart=True)
        except (KeyError, ValueError):
            pass

    def set_fps(self, fps: int):
        fps = int(fps)

        if fps <= 0:
            raise ValueError("FPS 必须大于 0")

        self.fps = fps

        if self.animation_timer.isActive():
            self.animation_timer.setInterval(max(1, round(1000 / self.fps)))

    def get_fps(self) -> int:
        return self.fps

    def play(self, animation_name: str, /, *, loop: bool = True, restart: bool = True):
        if animation_name not in self.animations:
            raise KeyError(f"不存在动画: {animation_name}")

        frames = self.animations[animation_name]['frames']

        if not frames:
            raise ValueError(f"动画没有可播放的帧: {animation_name}")

        entry = self.animations[animation_name]
        self.current_op = entry.get("op")
        self.fps = max(1, int(entry.get("fps") or self.fps))
        loop = bool(entry.get("loop", loop))

        if self.current_animation == animation_name and not restart:
            self.animation_loop = loop
            self.animation_timer.setInterval(max(1, round(1000 / self.fps)))
            if not self.animation_timer.isActive() and not self._paused:
                self.animation_timer.start(max(1, round(1000 / self.fps)))
            return

        self.current_animation = animation_name
        self.current_frames = frames
        self.current_frame = 0
        self.animation_loop = loop
        self.animation_playing = True
        self._paused = False

        self._show_current_frame()
        self.animation_timer.start(max(1, round(1000 / self.fps)))
        self.startTimer(5)

    def next_frame(self):
        if not self.current_frames:
            return

        if self.current_op:
            func = getattr(
                self,
                f"_{self.current_op}",
                None
            )
            if func:
                func()

        self.current_frame += 1

        if self.current_frame >= len(self.current_frames):
            if self.animation_loop:
                self.current_frame = 0
            else:
                self.current_frame = len(self.current_frames) - 1
                self.animation_timer.stop()
                self.animation_playing = False

        self._show_current_frame()
        self.update()

    def _show_current_frame(self):
        if not self.current_frames:
            return

        if self.current_frame < 0 or self.current_frame >= len(self.current_frames):
            return

        path = self.current_frames[self.current_frame]
        image = self.image_cache.get(path)

        if image is None:
            try:
                with Image.open(path) as pil_image:
                    pil_image = pil_image.convert("RGBA")
                    raw = pil_image.tobytes("raw", "RGBA")
                    image = QImage(raw, pil_image.width, pil_image.height, pil_image.width * 4, QImage.Format_RGBA8888).copy()

                self.image_cache[path] = image
            except Exception as e:
                print(f"无法读取动画帧: {path}")
                print(e)
                return

        self.current_image = image
        self.current_pixmap = QPixmap.fromImage(image)

    def get_current_frame(self) -> str | None:
        if not self.current_frames:
            return None

        return self.current_frames[self.current_frame]

    def get_current_animation(self) -> str | None:
        return self.current_animation

    def pause(self):
        self._paused = True
        self.animation_timer.stop()
        self.animation_playing = False

    pause_animation = pause

    def resume(self):
        if not self.current_frames:
            return

        self._paused = False
        self.animation_playing = True
        self.animation_timer.start(max(1, round(1000 / self.fps)))

    resume_animation = resume

    def stop(self):
        self.animation_timer.stop()
        self.animation_playing = False

        # 清除持续行为
        self.current_op = None

        self.current_frame = 0

        if self.current_frames:
            self._show_current_frame()

        self.update()

    stop_animation = stop

    def set_mouse_transparent(self, is_transparent: bool):
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

    def is_in_animation_area(self, click_x: int | None = None, click_y: int | None = None) -> bool:
        if self.current_image is None:
            return False

        if click_x is None:
            click_x = QCursor.pos().x() - self.x()

        if click_y is None:
            click_y = QCursor.pos().y() - self.y()

        image = self.current_image

        if image.width() <= 0 or image.height() <= 0:
            return False

        scale = min(self.width() / image.width(), self.height() / image.height())
        draw_width = int(image.width() * scale)
        draw_height = int(image.height() * scale)
        offset_x = (self.width() - draw_width) // 2
        offset_y = (self.height() - draw_height) // 2

        if not offset_x <= click_x < offset_x + draw_width:
            return False

        if not offset_y <= click_y < offset_y + draw_height:
            return False

        image_x = int((click_x - offset_x) / scale)
        image_y = int((click_y - offset_y) / scale)

        image_x = max(0, min(image_x, image.width() - 1))
        image_y = max(0, min(image_y, image.height() - 1))

        return image.pixelColor(image_x, image_y).alpha() > 0

    def is_in_live2d_area(self, click_x: int | None = None, click_y: int | None = None):
        return self.is_in_animation_area(click_x, click_y)

    def _play_action(self, action) -> bool:
        if not isinstance(action, dict):
            return False
        name = str(action.get("anim") or "").strip()
        if not name:
            return False
        try:
            self.play(name)
            return True
        except (KeyError, ValueError):
            return False

    def _smart_control(self, now):
        if not getattr(stlibs.Animation, "smart_control", False):
            return
        if now - self._last_interaction < 12 or now - self._last_smart < 20:
            return
        names = [name for name, item in self.animations.items() if item.get("frames")]
        if names:
            self._last_smart = now
            try:
                self.play(random.choice(names))
            except (KeyError, ValueError):
                pass

    def timerEvent(self, event):
        if self.is_dragging:
            self.update()
            return
        local_x = QCursor.pos().x() - self.x()
        local_y = QCursor.pos().y() - self.y()

        inside = self.is_in_animation_area(local_x, local_y)
        self.click_in_area = inside
        self.set_mouse_transparent(not inside)

        now = time.monotonic()
        if inside:
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
        self.update()

    def setCanvasOpacity(self, value):
        self.setWindowOpacity(_opacity(value))

    def setRotationAngle(self, angle):
        stlibs.Config.rotate = angle

    def show_context_menu(self, position):
        def window_visible(window, ui_class):
            if window is None:
                window = ui_class()

            if window.isHidden():
                window.show()
                window.raise_()
                window.activateWindow()
            else:
                window.hide()

        # 开菜单前先清掉拖拽残留状态
        self.reset_drag_state()

        context_menu = stlibs.SharingData.theme.Menu(self)
        self.connect_menu_closed(context_menu)

        setting_visible_action = stlibs.SharingData.theme.Action("设置", self, stlibs.SharingData.theme.IconList.SETTING)
        setting_visible_action.triggered.connect(lambda: window_visible(stlibs.SharingData.setting_window, settings.Settings))
        context_menu.addAction(setting_visible_action)

        context_menu.addSeparator()

        if stlibs.ai_enabled():
            from stlibs.graphics import chat

            chat_action = stlibs.SharingData.theme.Action("聊天", self, stlibs.SharingData.theme.IconList.CHAT)
            chat_action.triggered.connect(lambda: window_visible(stlibs.SharingData.chat_window, chat.Chat))
            context_menu.addAction(chat_action)

            import webbrowser

            online_action = stlibs.SharingData.theme.Action("网页聊天", self, stlibs.SharingData.theme.IconList.CHAT)
            online_action.triggered.connect(lambda: webbrowser.open("http://127.0.0.1:52493"))
            context_menu.addAction(online_action)

            context_menu.addSeparator()

        self.add_plugin_actions(context_menu)

        shut_program_action = stlibs.SharingData.theme.Action("关闭", self, stlibs.SharingData.theme.IconList.SHUTDOWN)
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
        """清掉拖拽残留状态，并通知宿主一起复位。"""
        self.drag_position = None
        self.drag_start_position = None
        self.is_dragging = False

        host_reset = getattr(self, "reset_host_drag_state", None)
        if callable(host_reset):
            host_reset()

    def plugin_menu_action(self, text, icon):
        """主题的 Action 工厂。"""
        return stlibs.SharingData.theme.Action(text, self, icon)

    def run_plugin_action(self, action: str):
        from stlibs.graphics import menu as menu_module

        return menu_module.trigger_plugin_action(action)

    def mousePressEvent(self, event):
        global_x = event.globalPosition().x()
        global_y = event.globalPosition().y()

        local_x = global_x - self.x()
        local_y = global_y - self.y()
        self.set_mouse_transparent(False)

        if event.button() == Qt.MouseButton.LeftButton:
            if self.is_in_animation_area(local_x, local_y):
                if stlibs.SharingData.coordinates[0] == -1 and stlibs.SharingData.coordinates[1] == -1:
                    stlibs.SharingData.coordinates[0] = int(local_x)
                    stlibs.SharingData.coordinates[1] = int(local_y)
                elif stlibs.SharingData.coordinates[2] == -1 and stlibs.SharingData.coordinates[3] == -1:
                    stlibs.SharingData.coordinates[2] = int(local_x)
                    stlibs.SharingData.coordinates[3] = int(local_y)
                stlibs.SharingData.coordinates[4] = "static"

                self.is_dragging = True
                self.click_in_area = True
                self.click_x = int(global_x)
                self.click_y = int(global_y)
                self._last_interaction = time.monotonic()
            else:
                self.is_dragging = False

            self._press_moved = False
            self.drag_position = event.globalPosition() - self.frameGeometry().topLeft()
            self.drag_start_position = QPoint(int(global_x), int(global_y))
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
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        was_click = (
            event.button() == Qt.MouseButton.LeftButton
            and self.is_dragging
            and not self._press_moved
        )
        local_x, local_y = event.position().x(), event.position().y()
        self.set_mouse_transparent(True)
        if event.button() == Qt.LeftButton:
            self.drag_position = None
            self.drag_start_position = None
            self.is_dragging = False

        event.accept()

        if was_click:
            label, action = action_at(stlibs.Animation, local_x, local_y, "Click")
            self._play_action(action)
            self._last_interaction = time.monotonic()
            self.notify_clicked(event, label)

    def notify_clicked(self, event, action=""):
        """点一下桌宠：通知插件与 SDK 订阅者。"""
        self.emit_sdk_event("pet_click", {
            "x": event.globalPosition().x(), "y": event.globalPosition().y(),
            "source": "static", "action": action,
        })
        try:
            stlibs.plugin_manager().emit_event("pet_click", {"source": "static", "action": action})
        except Exception:  # noqa: BLE001 - 插件系统的问题不该影响点击
            pass

    @staticmethod
    def emit_sdk_event(name: str, data=None):
        stlibs.emit_sdk_event(name, data)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier and self.is_in_animation_area():
            step = 5 if event.angleDelta().y() > 0 else -5
            value = max(10, min(110, int(stlibs.Config.size) + step))
            stlibs.Config.size = value
            self.setFixedSize(int(1000 * value / 100), int(1000 * value / 100))
            stlibs.ConfigLoader.save_config()
            self.update()
            event.accept()
            return

        super().wheelEvent(event)

    def paintEvent(self, event):
        if self.current_pixmap is None:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        pixmap = self.current_pixmap.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)

        x = (self.width() - pixmap.width()) // 2
        y = (self.height() - pixmap.height()) // 2

        painter.drawPixmap(
            x + self.offset_x,
            y + self.offset_y,
            pixmap
        )
        painter.end()

    def resizeEvent(self, event):
        self.update()
        super().resizeEvent(event)

    def clear_image_cache(self):
        self.image_cache.clear()
        self.current_image = None
        self.current_pixmap = None
        self.update()

    def exit_program(self):
        self.animation_timer.stop()
        value = str(getattr(stlibs.Animation, "AppExit", "") or "").strip()
        if value:
            try:
                self.play(value, loop=False)
            except (KeyError, ValueError):
                pass
            QTimer.singleShot(800, self._finish_exit)
        else:
            self._finish_exit()

    def _finish_exit(self):
        self.close()
        os.kill(os.getpid(), __import__("signal").SIGINT)

