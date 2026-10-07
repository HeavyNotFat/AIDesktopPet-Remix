import os
import sys
import ctypes
from difflib import get_close_matches
from typing import Literal
import webbrowser

from . import ADPOpenGLCanvas
try:
    from .. import stlibs
    from ..stlibs import architecture
    from ..stlibs.graphics import chat
    from ..stlibs.graphics import settings
except ImportError:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import stlibs
    from stlibs import architecture, SharingData, get_translation
    from stlibs.graphics import chat
    from stlibs.graphics import settings

from OpenGL import GL
from PySide6.QtGui import QGuiApplication, QIcon, QCursor
from PySide6.QtCore import Qt, QPoint

GWL_EX_STYLE: int = -20
WS_EX_TRANSPARENT: int = 0x00000020


class PublicShader(ADPOpenGLCanvas):
    def __init__(self):
        super().__init__()
        # 设置标题
        self.setWindowTitle("DesktopPetRemix - Character Mainloop")
        # 设置图标
        self.setWindowIcon(QIcon("logo.ico"))
        # 设置属性
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)

        # 初始化
        self.is_transparent_raise = False
        self.current_size = 1000
        self.pet_model: architecture.live2d.LAppModel | None = None
        self.click_in_area, self.click_x, self.click_y = -1, -1, -1
        self.drag_position, self.drag_start_position, self.is_dragging = None, None, None
        self.amount = 0

        # 调整大小
        self.setFixedSize(self.current_size, self.current_size)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

        stlibs.SharingData.setting_window = settings.Settings()
        stlibs.SharingData.setting_window.live2d_mot_signal.connect(lambda data: self.play(*data, type_="mot"))
        stlibs.SharingData.setting_window.live2d_exp_signal.connect(lambda data: self.play(*data, type_="exp"))
        stlibs.SharingData.chat_window = chat.Chat()
        stlibs.SharingData.setting_window.general_changed.connect(self.realtime_revise_config)

    def realtime_revise_config(self, config: dict):
        opacity = config.get("opacity", None)
        size = config.get("size", None)
        rotate = config.get("rotate", None)
        model_live2d = config.get("model_live2d", None)
        if opacity is not None:
            stlibs.Config.opacity = opacity
            self.setCanvasOpacity(stlibs.Config.opacity)
        if size is not None:
            stlibs.Config.size = size
            self.pet_model.SetScale(stlibs.Config.size / 100)
        if rotate is not None:
            stlibs.Config.rotate = rotate
            self.setRotationAngle(stlibs.Config.rotate)
        if model_live2d is not None:
            self.loadModelEvent(model_live2d)
            # architecture.live2d.

    def set_mouse_transparent(self, is_transparent: bool):
        """设置鼠标穿透 (透明部分可以直接穿过)"""
        if self.is_transparent_raise:
            return
        window_handle = int(self.winId())
        try:
            current_ex_style = ctypes.windll.user32.GetWindowLongW(window_handle, GWL_EX_STYLE)
            if is_transparent:
                # 添加WS_EX_TRANSPARENT样式以启用鼠标穿透
                new_ex_style = current_ex_style | WS_EX_TRANSPARENT
            else:
                # 移除WS_EX_TRANSPARENT样式以禁用鼠标穿透
                new_ex_style = current_ex_style & ~WS_EX_TRANSPARENT

            # 应用新的样式
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
        """模型加载事件"""
        try:
            model_files = os.listdir(f"./resources/character/model/{model}")
            # 寻找最像模型json文件的那一个文件
            model_json_file = get_close_matches(f"{model}.model.json", model_files)[0]
            SharingData.model_json_path = f"./resources/character/model/{model}/{model_json_file}"
            # 加载架构
            if model_json_file.split(".")[1] == "model3":
                if is_info:
                    return 3, SharingData.model_json_path
                if architecture.live2d.LIVE2D_VERSION != 3:
                    architecture.reload(3)
            elif model_json_file.split(".")[1] == "model":
                if is_info:
                    return 2, SharingData.model_json_path
                if architecture.live2d.LIVE2D_VERSION != 2:
                    architecture.reload(2)
            else:
                raise FileNotFoundError()

            self.pet_model.LoadModelJson(SharingData.model_json_path)
        except (KeyError, FileNotFoundError):
            self.exit_program()
        finally:
            return

    def timerEvent(self, a0):
        """定时器事件"""
        local_x, local_y = QCursor.pos().x() - self.x(), QCursor.pos().y() - self.y()
        self.pet_model.Drag(local_x, local_y)

        # 检查点击区域
        if self.is_in_live2d_area(local_x, local_y):
            self.click_in_area = True
            self.set_mouse_transparent(False)
        else:
            self.click_in_area = False
            self.set_mouse_transparent(True)

        if self.amount > 100:
            self.amount = 1
        elif self.amount == 0:
            self.current_size = 700
            self.setFixedSize(self.current_size, self.current_size)

        self.pet_model.SetScale(stlibs.Config.size / 100)
        self.setCanvasOpacity(stlibs.Config.opacity)
        self.setRotationAngle(stlibs.Config.rotate)

        self.amount += 1
        self.update()

    def show_context_menu(self, position):
        """显示右键菜单"""
        def window_visible(window, ui_class):
            if window is None:
                window = ui_class()

            if window.isHidden():
                window.show()
            else:
                window.hide()

        def open_browser():
            webbrowser.open("http://127.0.0.1:52493")

        context_menu = stlibs.SharingData.theme.Menu(self)

        setting_visible_action = stlibs.SharingData.theme.Action(get_translation("shader.menu.settings"), self, stlibs.SharingData.theme.IconList.SETTING)
        setting_visible_action.triggered.connect(lambda: window_visible(stlibs.SharingData.setting_window, settings.Settings))
        context_menu.addAction(setting_visible_action)

        context_menu.addSeparator()

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
        """把插件注册的菜单项挂到右键菜单上（UI Hook）：一个插件一层子菜单。"""
        from stlibs.graphics import menu as menu_module

        return menu_module.add_plugin_menu(context_menu, action_factory=self.plugin_menu_action)

    def plugin_menu_action(self, text, icon):
        """主题动作工厂：主题的 Action 签名是 (text, parent, icon)。"""
        return stlibs.SharingData.theme.Action(text, self, icon)

    def run_plugin_action(self, action: str):
        from stlibs.graphics import menu as menu_module

        return menu_module.trigger_plugin_action(action)

    @staticmethod
    def emit_sdk_event(name: str, data=None):
        """把桌宠上的动作告诉订阅了 SDK 事件的外部程序（统一走 stlibs）。"""
        stlibs.emit_sdk_event(name, data)

    def mousePressEvent(self, event):
        """鼠标拖动时间及按下事件"""
        x, y = event.globalPosition().x(), event.globalPosition().y()
        if self.is_in_live2d_area(QCursor.pos().x() - self.x(), QCursor.pos().y() - self.y()):
            if SharingData.coordinates[0] == -1 and SharingData.coordinates[1] == -1:
                SharingData.coordinates[0] = int(x)
                SharingData.coordinates[1] = int(y)
            elif SharingData.coordinates[2] == -1 and SharingData.coordinates[3] == -1:
                SharingData.coordinates[2] = int(x)
                SharingData.coordinates[3] = int(y)

            self.is_dragging = True
            self.click_in_area = True
            self.click_x, self.click_y = x, y
        else:
            self.is_dragging = False

        if event.button() == Qt.LeftButton:
            self.drag_position = event.globalPosition() - self.frameGeometry().topLeft()
            self.drag_start_position = QPoint(event.globalPosition().x(), event.globalPosition().y())
        else:
            self.is_dragging = False
        event.accept()

    def mouseMoveEvent(self, event):
        """鼠标移动事件"""
        if event.buttons() & Qt.LeftButton and self.drag_position is not None:
            if self.is_dragging:
                new_pos = event.globalPosition() - self.drag_position
                self.move(int(new_pos.x()), int(new_pos.y()))
            event.accept()

    def mouseReleaseEvent(self, event):
        """松手：没拖动就是在点桌宠 —— 通知插件与 SDK 订阅者。"""
        was_click = (
            event.button() == Qt.MouseButton.LeftButton
            and not self.is_dragging
            and self.is_in_live2d_area(QCursor.pos().x() - self.x(), QCursor.pos().y() - self.y())
        )
        super().mouseReleaseEvent(event)

        if not was_click:
            return

        self.emit_sdk_event("pet_click", {"x": event.globalPosition().x(), "y": event.globalPosition().y()})
        try:
            stlibs.plugin_manager().emit_event("pet_click", {"source": "live2d"})
        except Exception:  # noqa: BLE001 - 插件系统的问题不该影响点击
            pass

    # Ctrl + 滚轮a啊调整大小
    def wheelEvent(self, event):
        """滚轮事件"""
        if event.modifiers() == Qt.ControlModifier and self.is_in_live2d_area():
            angle_delta = event.angleDelta().y()
            if angle_delta > 0:
                self.current_size = int(self.current_size * 1.05)
            else:
                self.current_size = int(self.current_size * 0.95)

            self.current_size = max(100, min(self.current_size, 1000))
            self.setFixedSize(self.current_size, self.current_size)
            self.update()
            event.accept()
        else:
            super().wheelEvent(event)

    def play(self, name, index: int = 0, *, type_: Literal['exp', 'mot']):
        if type_ == "mot": self.pet_model.StartMotion(name, index, architecture.live2d.MotionPriority.FORCE)
        else: self.pet_model.SetExpression(name)

    def pause(self): pass
    def stop(self): pass
    def resume(self): pass

    # 渲染
    def on_init(self):
        architecture.live2d.glewInit()
        self.pet_model = architecture.live2d.LAppModel()
        self.loadModelEvent(stlibs.Config.model_live2d)
        self.startTimer(0)

    def on_resize(self, width, height):
        self.pet_model.Resize(width, height)

    def on_draw(self):
        architecture.live2d.clearBuffer()
        try:
            self.pet_model.Update()
            # 加载模型 Load Model
            self.pet_model.Draw()
        except SystemError:
            pass

    def exit_program(self):
        architecture.live2d.dispose()
        self.close()
        os.kill(os.getpid(), __import__("signal").SIGINT)
