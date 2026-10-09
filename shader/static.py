import os
import sys
import ctypes

from PIL import Image

from PySide6.QtCore import Qt, QPoint, QTimer
from PySide6.QtGui import QIcon, QCursor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QWidget

try:
    from .. import stlibs
    from ..stlibs.graphics import chat
    from ..stlibs.graphics import settings
except ImportError:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import stlibs
    from stlibs.graphics import chat
    from stlibs.graphics import settings


GWL_EX_STYLE = -20
WS_EX_TRANSPARENT = 0x00000020


class PublicShader(QWidget):
    IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg")

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
        self.setWindowOpacity(float(stlibs.Config.opacity))
        self._init_sharing_data()
        self._load_animation_frames()

    def _init_sharing_data(self):
        if getattr(stlibs.SharingData, "setting_window", None) is None:
            stlibs.SharingData.setting_window = settings.Settings()

        if getattr(stlibs.SharingData, "chat_window", None) is None:
            stlibs.SharingData.chat_window = chat.Chat()

        try:
            stlibs.SharingData.setting_window.general_changed.connect(self.realtime_revise_config)
        except (AttributeError, TypeError):
            pass

    def realtime_revise_config(self, config: dict):
        if not isinstance(config, dict):
            return

        opacity = config.get("opacity")
        size = config.get("size")
        rotate = config.get("rotate")
        model_live2d = config.get("model_live2d")

        if opacity is not None:
            stlibs.Config.opacity = opacity
            self.setWindowOpacity(float(opacity))

        if size is not None:
            stlibs.Config.size = size
            try:
                new_size = int(self.current_size * float(size) / 100)
                new_size = max(100, min(new_size, 2000))
                self.setFixedSize(new_size, new_size)
            except (TypeError, ValueError):
                pass

        if rotate is not None:
            stlibs.Config.rotate = rotate
            self.update()

        if model_live2d is not None:
            stlibs.Config.model_live2d = model_live2d

    def _load_animation_frames(self):
        self.animations.clear()

        for animation_name, frame_list in self.frames_config.items():
            if not isinstance(frame_list, dict):
                raise TypeError(f"{animation_name} 的 frames 必须是 dict")

            folder = os.path.join("./resources/character/static", stlibs.Config.static_model, animation_name)

            if not os.path.isdir(folder):
                raise FileNotFoundError(f"动画文件夹不存在: {folder}")

            if not frame_list['frames']:
                self.animations[animation_name] = []
                continue

            has_extension = any(os.path.splitext(str(frame))[1].lower() in self.IMAGE_EXTENSIONS for frame in frame_list['frames'])

            if has_extension:
                self.animations[animation_name] = self._parse_file_list(folder, frame_list)
            else:
                self.animations[animation_name] = self._parse_prefix_list(folder, frame_list)

    @staticmethod
    def _parse_file_list(folder: str, frame_list: list[str]) -> list[str]:
        result = []

        for filename in frame_list['frames']:
            path = os.path.join(folder, str(filename))

            if not os.path.isfile(path):
                raise FileNotFoundError(f"找不到动画帧: {path}")

            result.append(path)

        return {"frames": result, "op": frame_list['op']}

    def _parse_prefix_list(self, folder: str, frame_list: list[str]) -> list[str]:
        result = []

        for prefix in frame_list['frames']:
            prefix = str(prefix)
            matched = []

            for filename in os.listdir(folder):
                name, ext = os.path.splitext(filename)

                if ext.lower() not in self.IMAGE_EXTENSIONS:
                    continue

                if not name.startswith(prefix):
                    continue

                number_text = name[len(prefix):]

                if not number_text.isdigit():
                    continue

                matched.append((int(number_text), filename))

            matched.sort(key=lambda item: item[0])
            result.extend(os.path.join(folder, filename) for _, filename in matched)

        return {"frames": result, "op": frame_list['op']}

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

        self.current_op = self.animations[animation_name].get("op")

        if self.current_animation == animation_name and not restart:
            self.animation_loop = loop

            if not self.animation_timer.isActive():
                self.animation_timer.start(max(1, round(1000 / self.fps)))

            return

        self.current_animation = animation_name
        self.current_frames = frames
        self.current_frame = 0
        self.animation_loop = loop
        self.animation_playing = True

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
        self.animation_timer.stop()
        self.animation_playing = False

    pause_animation = pause

    def resume(self):
        if not self.current_frames:
            return

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

    def timerEvent(self, event):
        if self.is_dragging:
            self.update()
            return
        local_x = QCursor.pos().x() - self.x()
        local_y = QCursor.pos().y() - self.y()

        if self.is_in_animation_area(local_x, local_y):
            self.click_in_area = True
            self.set_mouse_transparent(False)
        else:
            self.click_in_area = False
            self.set_mouse_transparent(True)

        self.update()

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

        chat_action = stlibs.SharingData.theme.Action("聊天", self, stlibs.SharingData.theme.IconList.CHAT)
        chat_action.triggered.connect(lambda: window_visible(stlibs.SharingData.chat_window, chat.Chat))
        context_menu.addAction(chat_action)

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
            # 只有左键才算拖拽，右键唤菜单时不会留下拖拽状态
            if self.is_in_animation_area(local_x, local_y):
                self.is_dragging = True
                self.click_in_area = True
                self.click_x = int(global_x)
                self.click_y = int(global_y)
            else:
                self.is_dragging = False

            self.drag_position = event.globalPosition() - self.frameGeometry().topLeft()
            self.drag_start_position = QPoint(int(global_x), int(global_y))
        else:
            # 右键/中键：不拖拽，也不记抓取点
            self.is_dragging = False
            self.drag_position = None
            self.drag_start_position = None

        event.accept()

    def mouseMoveEvent(self, event):
        # 只有左键真的按住才跟着走，否则状态泄漏会让桌宠追着光标漂
        if event.buttons() & Qt.LeftButton and self.drag_position is not None:
            if self.is_dragging:
                new_pos = event.globalPosition() - self.drag_position
                self.move(int(new_pos.x()), int(new_pos.y()))

            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        was_click = event.button() == Qt.MouseButton.LeftButton and not self.is_dragging
        self.set_mouse_transparent(True)
        if event.button() == Qt.LeftButton:
            self.drag_position = None
            self.drag_start_position = None
            self.is_dragging = False

        event.accept()

        if was_click:
            self.notify_clicked(event)

    def notify_clicked(self, event):
        """点一下桌宠：通知插件与 SDK 订阅者。"""
        self.emit_sdk_event("pet_click", {
            "x": event.globalPosition().x(), "y": event.globalPosition().y(), "source": "static",
        })
        try:
            stlibs.plugin_manager().emit_event("pet_click", {"source": "static"})
        except Exception:  # noqa: BLE001 - 插件系统的问题不该影响点击
            pass

    @staticmethod
    def emit_sdk_event(name: str, data=None):
        stlibs.emit_sdk_event(name, data)

    def wheelEvent(self, event):
        if event.modifiers() == Qt.ControlModifier and self.is_in_animation_area():
            angle_delta = event.angleDelta().y()

            if angle_delta > 0:
                self.current_size = int(self.current_size * 1.05)
            else:
                self.current_size = int(self.current_size * 0.95)

            self.current_size = max(100, min(self.current_size, 2000))
            self.setFixedSize(self.current_size, self.current_size)
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
        self.close()

        os.kill(os.getpid(), __import__("signal").SIGINT)

