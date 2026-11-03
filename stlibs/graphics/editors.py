import os

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QMessageBox, QPushButton, QScrollArea,
    QSpinBox, QVBoxLayout, QWidget,
)

from .. import (
    ANIMATION_EMOTE_PATH, ANIMATION_LIVE2D_PATH, ANIMATION_STATIC_PATH, Config, ConfigLoader,
    SharingData, AnimationLoader, ai_enabled, notify, reload_animation_config,
)
from ..action_map import MAPPING_ANIMATION, MAPPING_SPECIAL_ANIMATION
from ..character import IMAGE_EXTENSIONS, STATIC
from ..emote import discover_models, import_model
from ..static_animation import (
    find_animation, import_images, list_animations, list_models,
    refresh_sharing_data, remove_animation, sort_paths,
)
def _palette():
    from .palette import palette

    return palette()


def _style(widget):
    p = _palette()
    widget.setStyleSheet(f"""
        QWidget {{ background: {p.bg}; color: {p.text}; font-size: 13px; }}
        QLabel {{ background: transparent; color: {p.text}; }}
        QPushButton {{ background: {p.surface}; color: {p.text}; border: 1px solid {p.border};
                       border-radius: {p.radius_small}px; padding: 5px 10px; min-height: 24px; }}
        QPushButton:hover {{ background: {p.hover}; border-color: {p.primary}; }}
        QPushButton:pressed {{ background: {p.surface_soft}; }}
        QPushButton:disabled {{ color: {p.text_faint}; border-color: {p.border}; }}
        QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox {{ background: {p.surface_sunk}; color: {p.text};
                       border: 1px solid {p.border}; border-radius: {p.radius_small}px; padding: 3px 6px; min-height: 24px; }}
        QComboBox QAbstractItemView {{ background: {p.bg}; color: {p.text}; }}
        QCheckBox {{ background: transparent; color: {p.text}; }}
        QListWidget {{ background: {p.surface_sunk}; color: {p.text}; border: 1px solid {p.border}; }}
        QScrollArea {{ border: none; background: transparent; }}
        QFrame#Card {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: {p.radius}px; }}
    """)
    return widget


def _label(text, dim=False):
    label = QLabel(text)
    p = _palette()
    label.setStyleSheet(f"QLabel {{ color: {p.text_dim if dim else p.text}; background: transparent; }}")
    label.setWordWrap(True)
    return label


def _button(text, on_click=None):
    button = QPushButton(text)
    if on_click is not None:
        button.clicked.connect(on_click)
    return button


def _combo():
    combo = QComboBox()
    combo.setMinimumWidth(150)
    return combo


def _card(title, body):
    card = QFrame()
    card.setObjectName('Card')
    layout = QVBoxLayout(card)
    layout.setContentsMargins(10, 8, 10, 10)
    layout.setSpacing(6)
    layout.addWidget(_label(title))
    layout.addWidget(body)
    return card


def _row(*widgets):
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)
    for widget in widgets:
        layout.addWidget(widget)
    layout.addStretch()
    return row


def _scroll(widget):
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setWidget(widget)
    return scroll


class _ActionEditor(QWidget):
    """动作坐标与绑定，Live2D / Emote 共用。"""

    changed = Signal()

    def __init__(self, animation_path, kind, playable_provider, expression_provider=None,
                 animation=None, parent=None):
        super().__init__(parent)
        self.animation_path = animation_path
        self.kind = kind
        self.playable_provider = playable_provider
        self.expression_provider = expression_provider
        self.animation = animation or AnimationLoader.load_animation(animation_path)
        self._filling = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.action_combo = _combo()
        self.action_combo.addItems(list(MAPPING_ANIMATION.keys()) + list(MAPPING_SPECIAL_ANIMATION.keys()))
        self.action_combo.currentTextChanged.connect(self.fill_action)
        layout.addWidget(_row(_label('动作'), self.action_combo, _button('刷新动作列表', self.refresh_playables)))

        self.x_input = QSpinBox(); self.x_input.setRange(0, 9999)
        self.y_input = QSpinBox(); self.y_input.setRange(0, 9999)
        self.dx_input = QSpinBox(); self.dx_input.setRange(0, 9999)
        self.dy_input = QSpinBox(); self.dy_input.setRange(0, 9999)
        self.record_button = _button('录入坐标', self.record)
        layout.addWidget(_row(_label('X'), self.x_input, _label('Y'), self.y_input,
                               _label('DX'), self.dx_input, _label('DY'), self.dy_input,
                               self.record_button))

        self.playable_combo = _combo()
        self.expression_combo = _combo()
        self.bind_button = _button('绑定到动作', self.bind)
        self.clear_button = _button('清除绑定', self.clear_binding)
        self.preview_button = _button('试播', self.preview)
        layout.addWidget(_row(_label('动画'), self.playable_combo, self.bind_button, self.clear_button))
        layout.addWidget(_row(_label('表情'), self.expression_combo, self.preview_button))

        self.hint = _label('先选动作，再点录入坐标；坐标点两次桌宠即可。', dim=True)
        layout.addWidget(self.hint)

        self.refresh_playables()
        self.fill_action(self.action_combo.currentText())
        self.startTimer(200)

    def refresh_playables(self):
        self._filling = True
        self.playable_combo.clear()
        self.playable_combo.addItems([str(item) for item in (self.playable_provider() or [])])
        self.playable_combo.addItem('')
        self.expression_combo.clear()
        if self.expression_provider is not None:
            self.expression_combo.addItems([str(item) for item in (self.expression_provider() or [])])
            self.expression_combo.addItem('')
            self.expression_combo.setEnabled(True)
        else:
            self.expression_combo.setEnabled(False)
        self._filling = False

    def _attr(self, label):
        return MAPPING_ANIMATION.get(label) or MAPPING_SPECIAL_ANIMATION.get(label)

    def fill_action(self, label):
        self._filling = True
        attr = self._attr(label)
        value = getattr(self.animation, attr, None) if attr else None
        special = label in MAPPING_SPECIAL_ANIMATION
        for widget in (self.x_input, self.y_input, self.dx_input, self.dy_input, self.record_button):
            widget.setEnabled(not special)
        self.expression_combo.setEnabled(not special and self.expression_provider is not None)
        if special:
            self.playable_combo.setCurrentText(str(value or ''))
            self.expression_combo.setCurrentText('')
        elif isinstance(value, dict):
            self.x_input.setValue(int(value.get('x', 0) or 0))
            self.y_input.setValue(int(value.get('y', 0) or 0))
            self.dx_input.setValue(int(value.get('dx', 0) or 0))
            self.dy_input.setValue(int(value.get('dy', 0) or 0))
            self.playable_combo.setCurrentText(str(value.get('anim') or ''))
            self.expression_combo.setCurrentText(str(value.get('expr') or ''))
        self._filling = False

    def _save(self):
        label = self.action_combo.currentText().strip()
        attr = self._attr(label)
        if not attr:
            return
        if label in MAPPING_SPECIAL_ANIMATION:
            setattr(self.animation, attr, self.playable_combo.currentText().strip())
        else:
            setattr(self.animation, attr, {
                'x': self.x_input.value(), 'y': self.y_input.value(),
                'dx': self.dx_input.value(), 'dy': self.dy_input.value(),
                'anim': self.playable_combo.currentText().strip(),
                'expr': self.expression_combo.currentText().strip() if self.expression_combo.isEnabled() else '',
            })
        AnimationLoader.save_animation(self.animation)
        from .. import character

        if character.kind() == self.kind:
            reload_animation_config(self.animation_path)
        self.changed.emit()
        self.hint.setText(f'已保存：{label}')

    def bind(self):
        self._save()

    def clear_binding(self):
        self.playable_combo.setCurrentText('')
        self.expression_combo.setCurrentText('')
        self._save()

    def preview(self):
        label = self.action_combo.currentText().strip()
        if label in MAPPING_SPECIAL_ANIMATION:
            return
        motion = self.playable_combo.currentText().strip()
        expression = self.expression_combo.currentText().strip() if self.expression_combo.isEnabled() else ''
        if motion:
            self.motion_preview.emit([motion])
        if expression:
            self.expression_preview.emit([expression])

    motion_preview = Signal(list)
    expression_preview = Signal(list)

    def record(self):
        SharingData.coordinates = [-1, -1, -1, -1, self.kind]
        self.hint.setText('坐标录入中：在桌宠身上点一下起点，再点一下终点。')

    def timerEvent(self, event):
        coordinates = list(SharingData.coordinates)
        if coordinates[4] != self.kind:
            return
        if coordinates[0] not in (-1, 0):
            self.x_input.setValue(int(coordinates[0]))
            self.y_input.setValue(int(coordinates[1]))
        if coordinates[2] not in (-1, 0):
            self.dx_input.setValue(int(coordinates[2]))
            self.dy_input.setValue(int(coordinates[3]))
            self._save()
            SharingData.coordinates = [0, 0, 0, 0, '']


class Live2DEditor(QWidget):
    motion_preview = Signal(list)
    expression_preview = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.animation = AnimationLoader.load_animation(ANIMATION_LIVE2D_PATH)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(8)

        self.smart = QCheckBox('智能控制：空闲时自动播动作')
        self.smart.setChecked(bool(self.animation.smart_control))
        self.smart.stateChanged.connect(self.set_smart)
        layout.addWidget(self.smart)
        self.ai = QCheckBox('AI 控制：允许模型自己决定播放什么')
        self.ai.setChecked(bool(self.animation.ai_control))
        self.ai.stateChanged.connect(self.set_ai_control)
        layout.addWidget(self.ai)

        providers = (lambda: getattr(SharingData, 'motions', None) or [],
                     lambda: getattr(SharingData, 'expressions', None) or [])
        self.actions = _ActionEditor(ANIMATION_LIVE2D_PATH, 'live2d', providers[0], providers[1],
                                     animation=self.animation)
        self.actions.motion_preview.connect(self.motion_preview.emit)
        self.actions.expression_preview.connect(self.expression_preview.emit)
        layout.addWidget(_card('自定义动作', self.actions))
        layout.addStretch()
        _style(self)
        self._playable_signature = ()
        self.startTimer(1500)

    def set_smart(self, value):
        self.animation.smart_control = bool(value)
        AnimationLoader.save_animation(self.animation)

    def set_ai_control(self, value):
        self.animation.ai_control = bool(value) and ai_enabled()
        if not self.animation.ai_control and self.ai.isChecked():
            self.ai.setChecked(False)
        AnimationLoader.save_animation(self.animation)

    def set_ai_enabled(self, enabled):
        self.ai.setVisible(bool(enabled))
        if not enabled and self.ai.isChecked():
            self.ai.setChecked(False)

    def refresh(self):
        self.actions.refresh_playables()

    def timerEvent(self, event):
        signature = (
            len(getattr(SharingData, 'motions', None) or []),
            len(getattr(SharingData, 'expressions', None) or []),
        )
        if signature != self._playable_signature:
            self._playable_signature = signature
            self.actions.refresh_playables()


class StaticEditor(QWidget):
    play_animation = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pending_paths = []
        self.preview_paths = []
        self.preview_index = 0
        self.saved_animation = ''
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.next_preview)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(8)

        self.model_combo = _combo()
        self.model_combo.currentTextChanged.connect(self.load_model)
        self.new_model = QLineEdit()
        self.new_model.setPlaceholderText('没有现成形象时，在这里输入新名字')
        layout.addWidget(_card('目标形象', _row(_label('形象'), self.model_combo, self.new_model,
                                                  _button('刷新', self.refresh_models))))

        self.animation_combo = _combo()
        self.animation_combo.currentTextChanged.connect(self.select_saved)
        self.import_button = _button('导入一组图片', self.import_images)
        self.save_button = _button('保存为动画', self.save_images)
        self.delete_button = _button('删除动画', self.delete_animation)
        layout.addWidget(_card('动画库', _row(_label('动画'), self.animation_combo,
                                               self.import_button, self.save_button, self.delete_button)))

        self.animation_name = QLineEdit()
        self.animation_name.setPlaceholderText('动画名，例如 idle')
        self.fps = QSpinBox(); self.fps.setRange(1, 60); self.fps.setValue(12)
        self.loop = QCheckBox('循环'); self.loop.setChecked(True)
        self.overwrite = QCheckBox('覆盖同名动画')
        layout.addWidget(_card('保存设置', _row(_label('名字'), self.animation_name,
                                                  _label('FPS'), self.fps, self.loop, self.overwrite)))

        self.action_animation = AnimationLoader.load_animation(ANIMATION_STATIC_PATH)
        self.actions = _ActionEditor(ANIMATION_STATIC_PATH, 'static', self._animation_names, None,
                                     animation=self.action_animation)
        self.actions.motion_preview.connect(lambda data: self.play_animation.emit(data[0]))
        layout.addWidget(_card('点击动作', self.actions))

        self.preview = QLabel('还没有导入图片')
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumHeight(240)
        p = _palette()
        self.preview.setStyleSheet(f'QLabel {{ background: {p.surface_sunk}; border: 1px solid {p.border}; }}')
        layout.addWidget(self.preview, 1)

        self.frame_label = _label('0 / 0', dim=True)
        self.prev_button = _button('上一张', self.prev_preview)
        self.next_button = _button('下一张', self.next_preview)
        self.play_button = _button('播放预览', self.toggle_preview)
        self.pet_button = _button('在桌宠上播放', self.play_on_pet)
        layout.addWidget(_row(self.prev_button, self.next_button, self.play_button,
                               self.pet_button, self.frame_label))
        self.hint = _label('导入后会按文件名自然排序，可以先逐张预览，再保存成动画。', dim=True)
        layout.addWidget(self.hint)
        _style(self)
        self.refresh_models()

    def refresh_models(self):
        current = self.model_combo.currentText() or Config.static_model
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        names = list_models()
        self.model_combo.addItems(names)
        if current in names:
            self.model_combo.setCurrentText(current)
        elif names:
            self.model_combo.setCurrentIndex(0)
        self.model_combo.blockSignals(False)
        self.load_model(self.model_combo.currentText())

    def current_model(self):
        return (self.new_model.text().strip() or self.model_combo.currentText().strip())

    def _animation_names(self):
        return [item.name for item in list_animations(self.current_model())]

    def load_model(self, _name=''):
        self.animation_combo.blockSignals(True)
        self.animation_combo.clear()
        self.animation_combo.addItems([item.name for item in list_animations(self.current_model())])
        self.animation_combo.blockSignals(False)
        self.actions.refresh_playables()
        if self.animation_combo.count():
            self.animation_combo.setCurrentIndex(0)
            self.select_saved(self.animation_combo.currentText())

    def select_saved(self, name):
        animation = find_animation(self.current_model(), str(name or ''))
        if animation is None:
            return
        self.saved_animation = animation.name
        self.preview_paths = list(animation.frames)
        self.preview_index = 0
        self.animation_name.setText(animation.name)
        self.fps.setValue(animation.fps)
        self.loop.setChecked(animation.loop)
        self.show_preview()

    def import_images(self):
        patterns = ' '.join(f'*{ext}' for ext in IMAGE_EXTENSIONS)
        paths, _ = QFileDialog.getOpenFileNames(self, '选择一组图片', '', f'图片 ({patterns})')
        if not paths:
            return
        self.pending_paths = sort_paths(paths)
        self.preview_paths = list(self.pending_paths)
        self.preview_index = 0
        self.saved_animation = ''
        self._timer.stop()
        self.play_button.setText('播放预览')
        if not self.animation_name.text().strip():
            stem = os.path.splitext(os.path.basename(self.pending_paths[0]))[0]
            self.animation_name.setText(stem.rstrip('_0123456789') or 'idle')
        self.show_preview()
        self.hint.setText(f'已导入 {len(self.pending_paths)} 张，按文件名排序；保存后会复制进形象目录。')

    def show_preview(self):
        if not self.preview_paths:
            self.preview.setText('还没有导入图片')
            self.frame_label.setText('0 / 0')
            return
        self.preview_index = max(0, min(self.preview_index, len(self.preview_paths) - 1))
        path = self.preview_paths[self.preview_index]
        pixmap = QPixmap(path)
        if pixmap.isNull():
            self.preview.setText(f'无法预览：{os.path.basename(path)}')
        else:
            self.preview.setPixmap(pixmap.scaled(self.preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.frame_label.setText(f'{self.preview_index + 1} / {len(self.preview_paths)}  ·  {os.path.basename(path)}')

    def prev_preview(self):
        if not self.preview_paths:
            return
        self.preview_index = (self.preview_index - 1) % len(self.preview_paths)
        self.show_preview()

    def next_preview(self):
        if not self.preview_paths:
            return
        self.preview_index = (self.preview_index + 1) % len(self.preview_paths)
        self.show_preview()

    def toggle_preview(self):
        if self._timer.isActive():
            self._timer.stop()
            self.play_button.setText('播放预览')
            return
        if not self.preview_paths:
            return
        self._timer.start(max(1, round(1000 / max(1, self.fps.value()))))
        self.play_button.setText('暂停预览')

    def save_images(self):
        if not self.pending_paths:
            notify('先导入一组图片', 'warning')
            return
        model = self.current_model()
        name = self.animation_name.text().strip()
        if not model or not name:
            notify('形象名和动画名都不能为空', 'warning')
            return
        try:
            animation = import_images(model, name, self.pending_paths, self.fps.value(),
                                      self.loop.isChecked(), self.overwrite.isChecked())
        except Exception as exc:  # noqa: BLE001
            notify(f'保存动画失败：{exc}', 'error', 4000)
            return
        self.pending_paths = []
        self.new_model.clear()
        refresh_sharing_data()
        self.refresh_models()
        self.model_combo.setCurrentText(animation.model)
        self.animation_combo.setCurrentText(animation.name)
        self.saved_animation = animation.name
        self.preview_paths = list(animation.frames)
        self.preview_index = 0
        self.show_preview()
        notify(f'已保存动画：{animation.model}/{animation.name}', 'success')

    def delete_animation(self):
        name = self.animation_combo.currentText().strip()
        model = self.current_model()
        if not name:
            return
        answer = QMessageBox.question(self, '删除动画', f'确定删除 {model}/{name}？')
        if answer != QMessageBox.StandardButton.Yes:
            return
        remove_animation(model, name)
        refresh_sharing_data()
        self.saved_animation = ''
        self.preview_paths = []
        self.refresh_models()
        notify('动画已删除', 'info')

    def play_on_pet(self):
        name = self.saved_animation or self.animation_combo.currentText().strip()
        if not name:
            notify('还没有可播放的动画', 'warning')
            return
        from .. import character

        if character.kind() != STATIC:
            notify('当前不是静态形象，切换到静态形象并重启后再播放', 'warning', 3500)
            return
        if self.current_model() != Config.static_model:
            notify('请先在「常规设置」切到这个形象，再播放它的动画', 'warning', 3500)
            return
        self.play_animation.emit(name)


class EmoteEditor(QWidget):
    timeline_preview = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.animation = AnimationLoader.load_animation(ANIMATION_EMOTE_PATH)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(8)

        self.model_combo = _combo()
        self.import_button = _button('导入 Emote 模型', self.import_emote)
        self.use_button = _button('设为当前形象', self.use_model)
        layout.addWidget(_card('Emote 模型', _row(_label('模型'), self.model_combo,
                                                  self.import_button, self.use_button,
                                                  _button('刷新', self.refresh_models))))

        self.status = _label('模型加载后，这里会列出主时间轴和差分时间轴。', dim=True)
        layout.addWidget(self.status)

        self.main_combo = _combo()
        self.diff_combo = _combo()
        layout.addWidget(_card('时间轴试播', _row(_label('主动画'), self.main_combo,
                                                       _button('播放', lambda: self.preview_timeline(self.main_combo, 0)))))
        layout.addWidget(_card('', _row(_label('差分'), self.diff_combo,
                                       _button('播放', lambda: self.preview_timeline(self.diff_combo, 1)))))

        self.variables = QListWidget()
        self.variables.setMaximumHeight(110)
        layout.addWidget(_card('可用变量', self.variables))

        providers = (lambda: [self.main_combo.itemText(i) for i in range(self.main_combo.count())],
                     lambda: [self.diff_combo.itemText(i) for i in range(self.diff_combo.count())])
        self.actions = _ActionEditor(ANIMATION_EMOTE_PATH, 'emote', providers[0], providers[1],
                                     animation=self.animation)
        self.actions.motion_preview.connect(lambda data: self.timeline_preview.emit([data[0], 0]))
        self.actions.expression_preview.connect(lambda data: self.timeline_preview.emit([data[0], 1]))
        layout.addWidget(_card('自定义动作', self.actions))

        self.ratio = QDoubleSpinBox(); self.ratio.setRange(0.5, 3.0); self.ratio.setSingleStep(0.1)
        self.ratio.setValue(float(getattr(Config, 'emote_render_ratio', 2.0) or 2.0))
        self.tracking = QSpinBox(); self.tracking.setRange(20, 1000); self.tracking.setSingleStep(10)
        self.tracking.setValue(int(getattr(Config, 'emote_tracking_interval', 50) or 50))
        layout.addWidget(_card('渲染参数', _row(_label('渲染倍率'), self.ratio, _label('眼动间隔(ms)'), self.tracking,
                                                  _button('保存参数', self.save_render))))
        layout.addWidget(_label('点击模型触发模型自带 config.js 的互动；没有 config.js 时随机播放主动画。', dim=True))
        _style(self)
        self._state_signature = ()
        self.refresh_models()
        self.apply_state(getattr(SharingData, 'emote_state', {}) or {})
        self.startTimer(700)

    def timerEvent(self, event):
        state = getattr(SharingData, 'emote_state', {}) or {}
        signature = (
            state.get('model'), state.get('ready'), state.get('error', ''),
            len(state.get('mainTimelines') or []),
            len(state.get('diffTimelines') or []), len(state.get('variables') or []),
        )
        if signature != self._state_signature:
            self._state_signature = signature
            self.apply_state(state)

    def refresh_models(self):
        current = Config.model_emote
        self.model_combo.clear()
        names = [model.name for model in discover_models()]
        self.model_combo.addItems(names)
        if current in names:
            self.model_combo.setCurrentText(current)

    def import_emote(self):
        path, _ = QFileDialog.getOpenFileName(self, '选择 Emote 模型', '', 'Emote (*.psb *.psb.zip *.zip)')
        if not path:
            return
        try:
            model = import_model(path)
        except Exception as exc:  # noqa: BLE001
            notify(f'导入 Emote 模型失败：{exc}', 'error', 4000)
            return
        self.refresh_models()
        self.model_combo.setCurrentText(model.name)
        notify(f'已导入：{model.name}', 'success')

    def use_model(self):
        from .. import character

        name = self.model_combo.currentText().strip()
        selected = character.select(name)
        if selected is None:
            notify('没有找到这个 Emote 模型', 'warning')
            return
        ui = getattr(SharingData, 'mainloop_ui', None)
        if character.kind() == character.EMOTE and ui is not None and hasattr(ui, 'reload_model'):
            ui.reload_model()
            notify(f'已切换到 Emote 模型：{name}', 'success')
        else:
            notify('已切换形象，重启程序后生效', 'warning', 3500)

    def preview_timeline(self, combo, slot):
        label = combo.currentText().strip()
        if label:
            self.timeline_preview.emit([label, slot])

    def apply_state(self, state):
        if not isinstance(state, dict):
            return
        main = [str(item) for item in (state.get('mainTimelines') or [])]
        diff = [str(item) for item in (state.get('diffTimelines') or [])]
        current_main = self.main_combo.currentText()
        current_diff = self.diff_combo.currentText()
        self.main_combo.clear(); self.main_combo.addItems(main)
        self.diff_combo.clear(); self.diff_combo.addItems(diff)
        if current_main in main:
            self.main_combo.setCurrentText(current_main)
        if current_diff in diff:
            self.diff_combo.setCurrentText(current_diff)
        self.variables.clear()
        for item in state.get('variables') or []:
            if isinstance(item, dict):
                self.variables.addItem(f"{item.get('label')}  [{item.get('min')} ~ {item.get('max')}]")
        self.actions.refresh_playables()
        if state.get('ready'):
            self.status.setText(f"模型已就绪：{state.get('model')}  ·  {len(main)} 个主动画 / {len(diff)} 个差分")
        elif state.get('error'):
            self.status.setText(f"模型加载失败：{state.get('error')}")

    def save_render(self):
        Config.emote_render_ratio = float(self.ratio.value())
        Config.emote_tracking_interval = int(self.tracking.value())
        ConfigLoader.save_config()
        ui = getattr(SharingData, 'mainloop_ui', None)
        if ui is not None and hasattr(ui, 'reload_model'):
            ui.reload_model()
        notify('Emote 渲染参数已保存', 'success')


__all__ = ['EmoteEditor', 'Live2DEditor', 'StaticEditor']
