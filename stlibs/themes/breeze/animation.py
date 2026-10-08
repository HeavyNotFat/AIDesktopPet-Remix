
from __future__ import annotations

from stlibs import Animation, AnimationLoader, SharingData

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)

from .. import base
from .primitives import (
    BreezeButton,
    BreezeCard,
    BreezeComboBox,
    BreezeLabel,
    BreezeLineEdit,
    BreezeScrollArea,
    BreezeSwitch,
    BreezeTabWidget,
)
from .theme import SURFACE
from .window import PageHint, PageTitle


class Live2D(QWidget):
    """Live2D 页签的内容本体。

    卡片竖着排下来比页签高（本机实测要 529px，页签只给 451px），**必须放进滚动区**：
    直接塞进页签的话 Qt 会把卡片压扁、控件互相重叠（"录入坐标"被输入框盖掉、
    播放表情整块看不见）。滚动区在 `AnimationPage` 里套，这里只管内容。
    """

    live2d_mot_signal = Signal(list)
    live2d_exp_signal = Signal(list)

    def __init__(self, parent):
        super().__init__(parent)
        from .chrome import MAPPING_ANIMATION, MAPPING_SPECTIAL_ANIMATION

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(8)

        # 智能 / AI 控制
        self.smart_control = BreezeSwitch()
        self.smart_control.setChecked(bool(Animation.smart_control))
        self.smart_control.stateChanged.connect(self.check_smart_control)
        root.addWidget(BreezeCard("智能控制", self.smart_control, "按交互自动挑动作与表情"))

        self.ai_control = BreezeSwitch()
        self.ai_control.setChecked(bool(Animation.ai_control))
        self.ai_control.stateChanged.connect(self.check_ai_control)
        root.addWidget(BreezeCard("AI 控制", self.ai_control, "允许模型自己决定播放什么"))

        # 坐标录入：一行动作下拉 + 一行 4 个坐标，用布局排（不是 QGridLayout 叠格子，
        # 那样在卡片高度不够时两行会互相压住，按钮文字被输入框盖掉一半）
        self.action_combo = BreezeComboBox()
        self.action_combo.addItems(list(MAPPING_ANIMATION.keys()))
        self.action_combo.addItems(list(MAPPING_SPECTIAL_ANIMATION.keys()))
        self.action_combo.currentTextChanged.connect(self.fill_info_by_act)

        coords = QWidget()
        coords_box = QVBoxLayout(coords)
        coords_box.setContentsMargins(0, 0, 0, 0)
        coords_box.setSpacing(8)

        pick_row = QHBoxLayout()
        pick_row.setSpacing(8)
        pick_row.addWidget(BreezeLabel("动作"))
        pick_row.addWidget(self.action_combo, 1)
        self.record_button = BreezeButton("录入坐标")
        self.record_button.set_border()
        self.record_button.setMinimumWidth(96)
        self.record_button.clicked.connect(self.record)
        pick_row.addWidget(self.record_button)
        coords_box.addLayout(pick_row)

        value_row = QHBoxLayout()
        value_row.setSpacing(8)
        self.x_input = BreezeLineEdit("X 坐标")
        self.y_input = BreezeLineEdit("Y 坐标")
        self.dx_input = BreezeLineEdit("偏移 X")
        self.dy_input = BreezeLineEdit("偏移 Y")
        for name, field in (("X", self.x_input), ("Y", self.y_input),
                            ("DX", self.dx_input), ("DY", self.dy_input)):
            value_row.addWidget(BreezeLabel(name))
            field.setMinimumWidth(70)
            value_row.addWidget(field, 1)
        coords_box.addLayout(value_row)

        root.addWidget(BreezeCard("自定义动作坐标", coords, "先选动作，再点录入，然后在桌宠上点一下", stacked=True))

        # 动画 / 表情试播：两个下拉互斥（选了一个就把另一个清空）
        self._switching = False
        self.motion_combo = BreezeComboBox()
        self.expression_combo = BreezeComboBox()
        self.motion_combo.currentTextChanged.connect(self.play_mot_example)
        self.expression_combo.currentTextChanged.connect(self.play_exp_example)
        self.motion_combo.currentTextChanged.connect(self.clear_expression)
        self.expression_combo.currentTextChanged.connect(self.clear_motion)
        root.addWidget(BreezeCard("播放动画", self.motion_combo, "选中即让桌宠播一次", stacked=True))
        root.addWidget(BreezeCard("播放表情", self.expression_combo, "选中即让桌宠做一次表情", stacked=True))

        root.addWidget(PageHint("坐标录入：点「录入坐标」后到桌宠身上点一下，X/Y/DX/DY 会自动填进来。"))

        QTimer.singleShot(500, self.get_motion_and_expression)
        self.startTimer(200)

    # -- 信号 ---------------------------------------------------------------
    def play_mot_example(self, mot: str):
        if not mot:
            return
        current = self.motion_combo.itemText(self.motion_combo.currentIndex())
        target_type = current.split(";")[0]
        index_in_group = 0
        for i in range(self.motion_combo.currentIndex()):
            text = self.motion_combo.itemText(i)
            if ";" in text and text.split(";")[0] == target_type:
                index_in_group += 1
        self.live2d_mot_signal.emit([mot.split(";")[0], index_in_group])

    def play_exp_example(self, exp: str):
        if not exp:
            return
        self.live2d_exp_signal.emit([exp.split(";")[0], self.expression_combo.currentIndex()])

    def clear_expression(self, *_args):
        """选动作时清掉表情，避免两个一起播。"""
        if self._switching or not self.expression_combo.currentText():
            return
        self._switching = True
        self.expression_combo.setCurrentText("")
        self._switching = False

    def clear_motion(self, *_args):
        if self._switching or not self.motion_combo.currentText():
            return
        self._switching = True
        self.motion_combo.setCurrentText("")
        self._switching = False

    # -- 数据 ---------------------------------------------------------------
    def get_motion_and_expression(self):
        """从 Live2D 模型参数里读出动作与表情清单（模型没加载就安静跳过）。"""
        from ... import architecture

        path = getattr(SharingData, "model_json_path", "")
        if not path:
            return
        try:
            param = architecture.addon.Live2DParameters(path)
        except Exception as exc:  # noqa: BLE001 - 静态形象 / 模型没起来时不该炸设置页
            print(f"[theme] 读取 Live2D 动作失败：{exc}")
            return

        motions = []
        for group, items in param.get_motions.items():
            for item in items:
                motions.append(f"{group if group else ' '};{item}")
        SharingData.motions = motions
        SharingData.expressions = param.get_expressions

        self.motion_combo.addItems(motions)
        self.expression_combo.addItems(param.get_expressions)
        self.motion_combo.addItem("")
        self.expression_combo.addItem("")

    @staticmethod
    def check_smart_control(boo: bool):
        Animation.smart_control = boo
        AnimationLoader.save_animation()

    @staticmethod
    def check_ai_control(boo: bool):
        Animation.ai_control = boo
        AnimationLoader.save_animation()

    def fill_info_by_act(self, value: str):
        from .chrome import MAPPING_ANIMATION, MAPPING_SPECTIAL_ANIMATION

        if value in MAPPING_ANIMATION:
            data = getattr(Animation, MAPPING_ANIMATION[value])
            self.x_input.setText(str(data['x']))
            self.y_input.setText(str(data['y']))
            self.dx_input.setText(str(data['dx']))
            self.dy_input.setText(str(data['dy']))
        elif value in MAPPING_SPECTIAL_ANIMATION:
            getattr(Animation, MAPPING_SPECTIAL_ANIMATION[value])

    def timerEvent(self, event, /):
        """轮询坐标录入结果：用户在桌宠上点完，这里把值落到 Animation 上。"""
        from .chrome import MAPPING_ANIMATION, MAPPING_SPECTIAL_ANIMATION

        if SharingData.coordinates[0] not in (-1, 0):
            self.x_input.setText(str(SharingData.coordinates[0]))
            self.y_input.setText(str(SharingData.coordinates[1]))
        if SharingData.coordinates[3] not in (-1, 0):
            self.dx_input.setText(str(SharingData.coordinates[2]))
            self.dy_input.setText(str(SharingData.coordinates[3]))

            action = self.action_combo.currentText().strip()
            if action in MAPPING_ANIMATION:
                setattr(Animation, MAPPING_ANIMATION[action], {
                    "x": int(self.x_input.text()), "y": int(self.y_input.text()),
                    "dx": int(self.dx_input.text()), "dy": int(self.dy_input.text()),
                    "anim": "", "expr": "",
                })
                AnimationLoader.save_animation()
            elif action in MAPPING_SPECTIAL_ANIMATION:
                setattr(Animation, MAPPING_SPECTIAL_ANIMATION[action], "")
                AnimationLoader.save_animation()
            else:
                raise NotImplementedError("Invalid data")

            SharingData.coordinates = [0, 0, 0, 0, ""]

    @staticmethod
    def record():
        SharingData.coordinates = [-1, -1, -1, -1, "live2d"]


class Static(QWidget):
    """静态形象的动画页：目前只提示改用序列帧目录。"""

    def __init__(self, parent):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(PageHint("静态形象的动作由 resources/static.json 的序列帧目录决定，"
                                  "换形象请在「常规设置」里选。"))
        layout.addStretch()


def scroll_wrap(widget: QWidget, parent: QWidget) -> BreezeScrollArea:
    """把内容套进滚动区：比页签高的内容才不会被压扁、重叠。

    用 `setWidgetResizable(True)`（不是 setFixedHeight）：这样内容有多高就滚多高，
    页签变小也不会反过来挤内容。
    """
    scroll = BreezeScrollArea(parent)
    scroll.setWidgetResizable(True)
    scroll.setWidget(widget)
    return scroll


class AnimationPage(QWidget, base.AnimationABS, metaclass=base.CombinedMeta):
    live2d_mot_signal = Signal(list)
    live2d_exp_signal = Signal(list)

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("AnimationPage")
        self.setWindowTitle("动画设置")
        self.setStyleSheet(f"QWidget#AnimationPage {{ background: {SURFACE}; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)
        root.addWidget(PageTitle(self.windowTitle()))

        self.live2d = Live2D(self)
        self.live2d.live2d_mot_signal.connect(self.live2d_mot_signal.emit)
        self.live2d.live2d_exp_signal.connect(self.live2d_exp_signal.emit)

        self.tab_widget = BreezeTabWidget(self)
        self.tab_widget.addTab(scroll_wrap(self.live2d, self), "Live2D 动画")
        self.tab_widget.addTab(Static(self), "静态动画")
        root.addWidget(self.tab_widget, 1)


__all__ = ["AnimationPage", "Live2D", "Static"]
