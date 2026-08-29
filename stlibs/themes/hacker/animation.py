from stlibs import SharingData, Animation, AnimationLoader
from .. import base

from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtCore import QTimer, Signal


class Live2D(QWidget):
    live2d_mot_signal = Signal(list)
    live2d_exp_signal = Signal(list)

    def __init__(self, parent):
        super().__init__(parent)
        from . import HackerLabel, HackerSwitch, HackerComboBox, HackerLineEdit, HackerButton
        from . import MAPPING_ANIMATION, MAPPING_SPECTIAL_ANIMATION

        HackerLabel("智能控制", self).setGeometry(10, 10, 180, 30)
        smart_control = HackerSwitch(self)
        smart_control.stateChanged.connect(self.check_smart_control)
        smart_control.setGeometry(100, 5, 80, 30)

        HackerLabel("AI 控制", self).setGeometry(10, 45, 180, 30)
        ai_control = HackerSwitch(self)
        ai_control.stateChanged.connect(self.check_ai_control)
        ai_control.setGeometry(100, 40, 80, 30)

        # 自定义
        HackerLabel("自定义", self).setGeometry(10, 110, 180, 30)
        HackerLabel("动作",  self).setGeometry(10, 140, 180, 30)
        self.action_combo = HackerComboBox(self)
        self.action_combo.addItems(MAPPING_ANIMATION.keys())
        self.action_combo.addItems(MAPPING_SPECTIAL_ANIMATION.keys())
        self.action_combo.currentTextChanged.connect(self.fill_info_by_act)
        self.action_combo.setGeometry(90, 135, 200, 30)
        # X, Y, DX, DY
        HackerLabel("X", self).setGeometry(10, 180, 100, 30)
        self.x_input = HackerLineEdit("X 坐标", self)
        self.x_input.setGeometry(30, 176, 70, 30)
        HackerLabel("Y", self).setGeometry(110, 180, 100, 30)
        self.y_input = HackerLineEdit("Y 坐标", self)
        self.y_input.setGeometry(130, 176, 70, 30)
        HackerLabel("DX", self).setGeometry(215, 180, 100, 30)
        self.dx_input = HackerLineEdit("偏移 X", self)
        self.dx_input.setGeometry(250, 176, 70, 30)
        HackerLabel("DY", self).setGeometry(330, 180, 100, 30)
        self.dy_input = HackerLineEdit("偏移 Y", self)
        self.dy_input.setGeometry(365, 176, 70, 30)
        # 录入
        self.record_button = HackerButton("录入", parent=self)
        self.record_button.set_border()
        self.record_button.clicked.connect(self.record)
        self.record_button.setGeometry(470, 173, 60, 30)

        # Animation & Expressions
        HackerLabel("播放动画：", self).setGeometry(10, 220, 150, 30)
        self.motion_combo = HackerComboBox(self)
        self.motion_combo.setGeometry(120, 215, 500, 30)
        HackerLabel("播放表情：", self).setGeometry(10, 260, 150, 30)
        self.expression_combo = HackerComboBox(self)
        self.expression_combo.setGeometry(120, 255, 300, 30)
        self.expression_combo.currentTextChanged.connect(self.clear_motion)
        self.motion_combo.currentTextChanged.connect(self.clear_expression)
        self.expression_combo.currentTextChanged.connect(self.play_exp_example)
        self.motion_combo.currentTextChanged.connect(self.play_mot_example)

        QTimer.singleShot(500, self.get_motion_and_expression)
        self.startTimer(200)

    # SIGNALs
    def play_mot_example(self, mot: str):
        current_text = self.motion_combo.itemText(self.motion_combo.currentIndex())
        target_type = current_text.split(";")[0]
        index_in_group = 0
        for i in range(self.motion_combo.currentIndex()):
            text = self.motion_combo.itemText(i)
            if ";" in text and text.split(";")[0] == target_type:
                index_in_group += 1

        self.live2d_mot_signal.emit([mot.split(";")[0], index_in_group])

    def play_exp_example(self, exp: str):
        self.live2d_exp_signal.emit([exp.split(";")[0], self.expression_combo.currentIndex()])

    def clear_expression(self):
        self.expression_combo.currentTextChanged.disconnect(self.clear_motion)
        self.motion_combo.currentTextChanged.disconnect(self.clear_expression)

        self.expression_combo.setCurrentText("")

        self.expression_combo.currentTextChanged.connect(self.clear_motion)
        self.motion_combo.currentTextChanged.connect(self.clear_expression)

    def clear_motion(self):
        self.expression_combo.currentTextChanged.disconnect(self.clear_motion)
        self.motion_combo.currentTextChanged.disconnect(self.clear_expression)

        self.motion_combo.setCurrentText("")

        self.expression_combo.currentTextChanged.connect(self.clear_motion)
        self.motion_combo.currentTextChanged.connect(self.clear_expression)

    # 数据
    def get_motion_and_expression(self):
        from ... import architecture

        param = architecture.addon.Live2DParameters(SharingData.model_json_path)
        motions = []
        for t, items in param.get_motions.items():
            for item in items:
                motions.append(f"{t if t else ' '};{item}")
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
        from . import MAPPING_ANIMATION, MAPPING_SPECTIAL_ANIMATION

        if value in MAPPING_ANIMATION.keys():
            data = getattr(Animation, MAPPING_ANIMATION[value])
            self.x_input.setText(str(data['x']))
            self.y_input.setText(str(data['y']))
            self.dx_input.setText(str(data['dx']))
            self.dy_input.setText(str(data['dy']))
        elif value in MAPPING_SPECTIAL_ANIMATION.keys():
            data = getattr(Animation, MAPPING_SPECTIAL_ANIMATION[value])

    def timerEvent(self, event, /):
        from . import MAPPING_ANIMATION, MAPPING_SPECTIAL_ANIMATION
        
        if SharingData.coordinates[0] != -1 and SharingData.coordinates[0] != -0:
            self.x_input.setText(str(SharingData.coordinates[0]))
            self.y_input.setText(str(SharingData.coordinates[1]))
        if SharingData.coordinates[3] != -1 and SharingData.coordinates[3] != 0:
            self.dx_input.setText(str(SharingData.coordinates[2]))
            self.dy_input.setText(str(SharingData.coordinates[3]))
            
            if self.action_combo.currentText().strip() in MAPPING_ANIMATION.keys():
                setattr(Animation, MAPPING_ANIMATION[self.action_combo.currentText().strip()], {
                    "x": int(self.x_input.text()), "y": int(self.y_input.text()), 
                    "dx": int(self.dx_input.text()), "dy": int(self.dy_input.text()), 
                    "anim": "", "expr": ""
                })
                AnimationLoader.save_animation()
            elif self.action_combo.currentText().strip() in MAPPING_SPECTIAL_ANIMATION.keys():
                setattr(Animation, MAPPING_SPECTIAL_ANIMATION[self.action_combo.currentText().strip()], "")
                AnimationLoader.save_animation()
            else: raise NotImplementedError("Invalid data")

            SharingData.coordinates = [0, 0, 0, 0, ""]

    @staticmethod
    def record():
        SharingData.coordinates = [-1, -1, -1, -1, "live2d"]


class Static(QWidget):
    def __init__(self, parent):
        super().__init__(parent)


class AnimationPage(QWidget, base.AnimationABS, metaclass=base.CombinedMeta):
    live2d_mot_signal = Signal(list)
    live2d_exp_signal = Signal(list)

    def __init__(self, parent):
        super().__init__(parent)
        from . import HackerLabel, HackerTabWidget

        self.setObjectName("AnimationPage")
        self.setWindowTitle("动画设置")
        self.window_title = HackerLabel(self.windowTitle(), self)
        self.window_title.set_center()
        self.window_title.setGeometry(0, 0, self.width(), 30)

        layout = QVBoxLayout()
        layout.setContentsMargins(20, 40, 20, 20)

        self.live2d = Live2D(self)
        self.live2d.live2d_mot_signal.connect(self.live2d_mot_signal.emit)
        self.live2d.live2d_exp_signal.connect(self.live2d_exp_signal.emit)

        self.tab_widget = HackerTabWidget(self)
        self.tab_widget.addTab(self.live2d, "Live2D 动画")
        self.tab_widget.addTab(Static(self), "静态 动画")
        layout.addWidget(self.tab_widget)
        self.setLayout(layout)

    def resizeEvent(self, event, /):
        super().resizeEvent(event)
        self.window_title.setGeometry(0, 0, self.width(), 30)
