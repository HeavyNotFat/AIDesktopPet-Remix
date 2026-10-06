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
        """
        每一帧更新物理状态
        """
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

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True

            self.physics.dragging = True
            self._drag_last_pos = event.globalPosition().toPoint()
            self._drag_velocity_x = 0.0
            self._drag_velocity_y = 0.0

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging:
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
