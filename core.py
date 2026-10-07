import sys
import threading
import traceback

from stlibs.sdk import server as sdk_server


def console(msg):
    print(msg)


# 初始化SDK
server = sdk_server.SDKServer()
server.start()

import stlibs
# 主题必须在 stlibs.graphics / shader 之前绑定：
# 那些模块在导入期就拿 SharingData.theme.Window 当基类
stlibs.SharingData.theme = stlibs.load_theme(stlibs.Config.theme)
# 让界面/插件也能推 SDK 事件（桌宠被点了一下、聊天结束之类）
stlibs.SharingData.sdk_server = server
from stlibs.mproc import onlinechat
if stlibs.Config.model_live2d.strip(): from shader import live2d as shader
else: from shader import static as shader

from PySide6.QtCore import Qt, QTimer, QPoint


def handle_exception(exc_type, exc_value, exc_traceback):
    """捕获全局未处理异常并打印"""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    print("".join(traceback.format_exception(exc_type, exc_value, exc_traceback)))


class DesktopPetRemix(shader.PublicShader):
    def __init__(self):
        if stlibs.Config.static_model.strip(): super().__init__(stlibs.SharingData.static_models[stlibs.Config.static_model])
        else: super().__init__()
        self.physics = stlibs.Physics()
        self.physics.enabled = False

        self.physics.reset(
            self.x(),
            self.y(),
        )

        self.physics_timer = QTimer(self)

        self.physics_timer.timeout.connect(
            self.update_physics
        )

        self.physics_timer.start(16)

        self._last_physics_time = None
        self._dragging = False

        self._drag_last_pos = QPoint()

        self._drag_velocity_x = 0.0
        self._drag_velocity_y = 0.0

        if stlibs.Config.static_model.strip(): self.play("idle")

    def update_physics(self):
        if self._dragging:
            return

        dt = 1.0 / 60.0

        screen = self.screen()

        self.physics.update(
            dt=dt,
            bounds=screen.availableGeometry(),
            width=self.width(),
            height=self.height(),
        )

        self.move(round(self.physics.x), round(self.physics.y))

    def _reset_drag(self):
        """清掉拖拽状态。

        右键弹出菜单后鼠标事件会被 Popup 接走，桌宠再也收不到那一下 release——
        留着 ``_dragging=True`` 的话，之后鼠标随手一动桌宠就跟着漂。
        """
        self._dragging = False
        self.drag_position = None
        self.drag_start_position = None
        self.is_dragging = False
        self._drag_velocity_x = 0.0
        self._drag_velocity_y = 0.0
        self.physics.dragging = False
        self.physics.set_position(self.x(), self.y())

    # shader 那边（PublicShader.reset_drag_state）在菜单收起时回调这个复位桌宠状态
    reset_host_drag_state = _reset_drag

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True

            self.physics.dragging = True
            self._drag_last_pos = event.globalPosition().toPoint()
            self._drag_velocity_x = 0.0
            self._drag_velocity_y = 0.0

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        # 只在左键真的按住时才跟着走：鼠标移过桌宠（没按键）也会进来，
        # 光看 _dragging 的话一次状态泄漏就会让桌宠追着光标漂
        if self._dragging and event.buttons() & Qt.MouseButton.LeftButton:
            current_pos = event.globalPosition().toPoint()
            dx = (current_pos.x() - self._drag_last_pos.x())
            dy = (current_pos.y() - self._drag_last_pos.y())
            self._drag_velocity_x = dx * 60.0
            self._drag_velocity_y = dy * 60.0

            new_x = self.x() + dx
            new_y = self.y() + dy
            self.move(
                new_x,
                new_y,
            )
            # 同步 Physics
            self.physics.set_position(
                new_x,
                new_y,
            )
            self._drag_last_pos = current_pos

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False

            self.physics.dragging = False
            self.physics.set_velocity(
                self._drag_velocity_x,
                self._drag_velocity_y,
            )

        super().mouseReleaseEvent(event)


sys.excepthook = handle_exception
# 这里为什么不用多进程？
# 因为这傻逼多进程的通信给我弄的头要烧了
proc_onlinechat = threading.Thread(target=onlinechat.main)
proc_onlinechat.start()
stlibs.SharingData.theme.IconList.init()

desktop = DesktopPetRemix()
stlibs.SharingData.mainloop_ui = desktop
desktop.show()

# 插件在界面起来之后再加载：插件的 on_load 里可以直接碰窗口/托盘/菜单
try:
    loaded = stlibs.plugin_manager().load_all()
    if loaded:
        names = "、".join(info.manifest.name for info in loaded if info.loaded)
        print(f"[plugin] 已加载 {sum(1 for info in loaded if info.loaded)}/{len(loaded)} 个插件：{names}")
except Exception as exc:  # noqa: BLE001 - 插件系统坏了不能挡住程序启动
    print(f"[plugin] 插件系统初始化失败：{type(exc).__name__}: {exc}")
