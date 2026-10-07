"""桌宠的拖拽状态机：菜单弹出来之后不能再跟着鼠标漂。

历史 bug：右键菜单是 ``Qt.Popup``，弹出后鼠标事件归它管，桌宠收不到那一下
``release``，``_dragging`` 就留在 True；之后鼠标随手在桌宠上移一下（没按任何
键）桌宠就跟着光标跑，看起来就是"点别处桌宠就漂移"。

``core.py`` 是"导入即执行"的（起 SDK 服务、起网页聊天线程、建窗口），所以这里
用 AST 只取 ``DesktopPetRemix`` 的那份真实源码，和真的 ``shader.static.PublicShader``
拼成一个测试用桌宠，两边都是线上代码。
"""

import ast
import os

import pytest

pytestmark = pytest.mark.ui

QtCore = pytest.importorskip("PySide6.QtCore", reason="桌宠拖拽测试需要 PySide6")
QtGui = pytest.importorskip("PySide6.QtGui", reason="桌宠拖拽测试需要 PySide6")
QtWidgets = pytest.importorskip("PySide6.QtWidgets", reason="桌宠拖拽测试需要 PySide6")

import stlibs  # noqa: E402

Qt = QtCore.Qt
QPoint = QtCore.QPoint

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 桌宠身上（不透明像素区）在窗口内的坐标，见下面 is_in_animation_area
BODY_LOCAL = QPoint(70, 70)


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    yield QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture(scope="module")
def real_theme(qapp):
    """导入 shader.static 会连带建设置窗/聊天窗，这些全局状态用完要还原。

    ``tests/test_sdk.py`` 里有用例依赖"全局还没有设置窗口"，不还原就会互相打架。
    """
    previous_theme = stlibs.SharingData.theme
    stlibs.SharingData.theme = stlibs.load_theme(stlibs.Config.theme)
    previous = {name: getattr(stlibs.SharingData, name, None)
                for name in ("setting_window", "chat_window")}

    yield stlibs.SharingData.theme

    for name, value in previous.items():
        setattr(stlibs.SharingData, name, value)
    stlibs.SharingData.theme = previous_theme


@pytest.fixture(scope="module")
def shader_module(qapp, real_theme):
    """真的 shader.static（导入期就要 SharingData.theme，所以先绑主题）。"""
    import shader.static as static

    return static


def load_pet_class(shader_module):
    """从 core.py 取出真实 DesktopPetRemix（去掉 __init__，不跑模块级副作用）。

    必须真的继承 ``shader.PublicShader``：方法体里用的是零参 ``super()``，
    它靠定义处的 ``__class__`` 闭包，拼错基类会直接 TypeError。
    """
    with open(os.path.join(ROOT, "core.py"), encoding="utf-8") as handle:
        tree = ast.parse(handle.read())

    for node in tree.body:
        if not (isinstance(node, ast.ClassDef) and node.name == "DesktopPetRemix"):
            continue
        node.body = [
            item for item in node.body
            if not (isinstance(item, ast.FunctionDef) and item.name == "__init__")
        ]
        # 基类换成真的 PublicShader（core.py 里写的是 shader.PublicShader）
        node.bases = [ast.Attribute(value=ast.Name(id="shader", ctx=ast.Load()),
                                    attr="PublicShader", ctx=ast.Load())]
        ast.fix_missing_locations(node)

        module = ast.Module(body=[node], type_ignores=[])
        ast.fix_missing_locations(module)
        namespace = {
            "Qt": Qt,
            "QPoint": QPoint,
            "QTimer": QtCore.QTimer,
            "stlibs": stlibs,
            "shader": shader_module,
            "__name__": "test_pet_drag",
        }
        exec(compile(module, "core.py<DesktopPetRemix>", "exec"), namespace)  # noqa: S102
        return namespace["DesktopPetRemix"]

    raise AssertionError("core.py 里找不到 DesktopPetRemix")


@pytest.fixture
def make_pet(qapp, shader_module):
    """真 PublicShader 的类 + 真 core 拖拽方法拼出来的桌宠。"""
    pet_type = load_pet_class(shader_module)
    created = []

    def build():
        # 不用 PublicShader.__init__：别的用例会 reload stlibs.graphics.chat，
        # shader.static 因此被重新导入，模块里的类对象与 PySide6 绑定可能不是同一份，
        # shiboken 会直接报 "QWidget.__init__ called with wrong argument types"。
        # 这里只做 QWidget 那一层初始化（必须做，否则一 move 就报 "__init__ not called"），
        # 再把 shader 方法真正用到的字段补齐。
        widget = pet_type.__new__(pet_type)
        QtWidgets.QWidget.__init__(widget)

        widget.frames_config = {"idle": {"frames": ["idle_"], "op": None}}
        widget.animations = {"idle": {"frames": ["idle_1.png"], "op": None}}
        widget.current_animation = "idle"
        widget.current_frames = ["idle_1.png"]
        widget.current_frame = 0
        widget.current_op = None
        widget.fps = 12
        widget.animation_loop = True
        widget.animation_playing = False
        widget.current_image = None
        widget.current_pixmap = None
        widget.image_cache = {}
        widget.animation_timer = QtCore.QTimer(widget)
        widget.animation_timer.timeout.connect(widget.next_frame)
        widget.offset_x = 0
        widget.offset_y = 0
        widget.is_transparent_raise = True   # set_mouse_transparent 直接返回
        widget.click_in_area = False
        widget.click_x = -1
        widget.click_y = -1

        def is_in_animation_area(local_x=None, local_y=None):
            if local_x is None:
                local_x, local_y = BODY_LOCAL.x(), BODY_LOCAL.y()
            return (BODY_LOCAL.x() - 30 <= local_x <= BODY_LOCAL.x() + 30
                    and BODY_LOCAL.y() - 30 <= local_y <= BODY_LOCAL.y() + 30)

        widget.is_in_animation_area = is_in_animation_area
        widget.is_in_live2d_area = is_in_animation_area

        widget._dragging = False
        widget._drag_last_pos = QPoint()
        widget._drag_velocity_x = 0.0
        widget._drag_velocity_y = 0.0
        widget.physics = FakePhysics()
        widget.move(400, 300)
        widget.show()
        qapp.processEvents()
        created.append(widget)
        return widget

    yield build
    for widget in created:
        widget.hide()
        widget.deleteLater()


class FakePhysics:
    dragging = False

    def __init__(self):
        self.x = 0.0
        self.y = 0.0

    def set_position(self, x, y):
        self.x, self.y = float(x), float(y)

    def set_velocity(self, vx, vy):
        pass


def make_event(kind, button, buttons, global_pos):
    point = QtCore.QPointF(global_pos)
    return QtGui.QMouseEvent(kind, point, point, button, buttons, Qt.KeyboardModifier.NoModifier)


def press(button, global_pos, buttons=None):
    return make_event(QtCore.QEvent.Type.MouseButtonPress, button, buttons or button, global_pos)


def release(button, global_pos):
    return make_event(QtCore.QEvent.Type.MouseButtonRelease, button, Qt.MouseButton.NoButton, global_pos)


def move(global_pos, buttons=Qt.MouseButton.NoButton):
    return make_event(QtCore.QEvent.Type.MouseMove, Qt.MouseButton.NoButton, buttons, global_pos)


def offset(point, dx, dy):
    """QPoint + 偏移（QPoint 不支持直接和元组相加）。"""
    return QPoint(point.x() + dx, point.y() + dy)


def body_point(pet):
    """桌宠身上（不透明像素区）的一个全局坐标。"""
    return pet.mapToGlobal(BODY_LOCAL)


def origin_of(pet):
    return (pet.x(), pet.y())


def test_left_press_in_area_starts_dragging(make_pet):
    pet = make_pet()

    pet.mousePressEvent(press(Qt.MouseButton.LeftButton, body_point(pet)))

    assert pet._dragging is True
    assert pet.is_dragging is True, "摸到身上才该进入拖拽"
    assert pet.drag_position is not None


def test_right_press_never_starts_dragging(make_pet):
    """右键是唤菜单的，不该把桌宠置成"正在拖拽"。"""
    pet = make_pet()

    pet.mousePressEvent(press(Qt.MouseButton.RightButton, body_point(pet)))

    assert pet._dragging is False
    assert pet.is_dragging is False
    assert pet.drag_position is None, "右键不该记抓取点"


def test_move_follows_cursor_while_left_button_is_held(make_pet):
    pet = make_pet()
    start = body_point(pet)
    origin = origin_of(pet)

    pet.mousePressEvent(press(Qt.MouseButton.LeftButton, start))
    pet.mouseMoveEvent(move(offset(start, 30, 20), Qt.MouseButton.LeftButton))

    assert (pet.x(), pet.y()) == (origin[0] + 30, origin[1] + 20), "按住左键拖动：桌宠要跟着走"


def test_move_without_button_held_never_moves_the_pet(make_pet):
    """状态泄漏（_dragging 卡在 True）时也不能跟着光标漂：没按键就不该动。"""
    pet = make_pet()
    start = body_point(pet)
    origin = origin_of(pet)

    # 模拟"release 被菜单吃掉"：两边状态都还留在拖拽中
    pet._dragging = True
    pet.is_dragging = True
    pet.drag_position = QtCore.QPointF(BODY_LOCAL.x(), BODY_LOCAL.y())

    for step in range(3):
        pet.mouseMoveEvent(move(offset(start, (step + 1) * 25, (step + 1) * 15)))

    assert (pet.x(), pet.y()) == origin, "没按任何键时桌宠不能漂"


def test_reset_drag_clears_every_leaked_field(make_pet):
    pet = make_pet()
    pet._dragging = True
    pet.is_dragging = True
    pet.drag_position = QtCore.QPointF(BODY_LOCAL.x(), BODY_LOCAL.y())
    pet.drag_start_position = QPoint(470, 370)
    pet._drag_velocity_x = 120.0
    pet._drag_velocity_y = 120.0

    pet._reset_drag()

    assert pet._dragging is False
    assert pet.is_dragging is False
    assert pet.drag_position is None
    assert pet.drag_start_position is None
    assert (pet._drag_velocity_x, pet._drag_velocity_y) == (0.0, 0.0)
    assert pet.physics.dragging is False


def show_without_grab(menu, monkeypatch):
    """让菜单"逻辑上可见"但不真的走平台弹出。

    offscreen 平台上真弹一个 ``Qt.Popup`` 会留下键盘/鼠标 grab 和活动弹窗，
    后面的菜单用例就再也 show 不出来了。这里只把窗口标记成可见，
    ``hide()``/``close()`` 照样会走 hideEvent/closeEvent。
    """
    monkeypatch.setattr(type(menu), "show", lambda self: QtWidgets.QWidget.setVisible(self, True))


def test_menu_closed_signal_resets_the_pet(make_pet, monkeypatch):
    """菜单收起时桌宠要复位拖拽状态（Popup 吃掉 release 的兜底）。"""
    from stlibs.themes import hacker

    pet = make_pet()
    menu = hacker.HackerMenu(pet)
    pet.connect_menu_closed(menu)
    assert getattr(menu, "_pet_drag_reset_hooked", False), "关闭钩子要挂上"

    pet._dragging = True
    pet.is_dragging = True
    pet.drag_position = QtCore.QPointF(1, 1)

    show_without_grab(menu, monkeypatch)
    menu.show()
    QtWidgets.QApplication.processEvents()
    menu.close()
    QtWidgets.QApplication.processEvents()

    assert pet._dragging is False, "菜单关掉后不能还留在拖拽状态"
    assert pet.is_dragging is False
    assert pet.drag_position is None


def test_hook_is_not_connected_twice(make_pet, monkeypatch):
    """菜单是每次右键新建的，不能每开一次就多接一根线。"""
    from stlibs.themes import hacker

    pet = make_pet()
    calls = []
    pet.reset_drag_state = lambda: calls.append(1)

    for _ in range(3):
        menu = hacker.HackerMenu(pet)
        pet.connect_menu_closed(menu)
        show_without_grab(menu, monkeypatch)
        menu.show()
        QtWidgets.QApplication.processEvents()
        menu.close()
        QtWidgets.QApplication.processEvents()

    assert calls == [1, 1, 1], f"每次关闭各复位一次，不能重复接（实际 {calls}）"


def test_menu_opening_wipes_the_leftover_drag_state(make_pet, monkeypatch):
    """开菜单前必须先把拖拽状态清干净（Popup 一起来就收不到 release 了）。"""
    from stlibs.themes import hacker

    pet = make_pet()
    pet.is_dragging = True
    pet.drag_position = QtCore.QPointF(1, 1)
    pet.drag_start_position = QPoint(1, 1)

    opened = {}

    class FakeMenu:
        def __init__(self, parent=None):
            opened["menu"] = self

        def addAction(self, action):
            pass

        def addSeparator(self):
            pass

        def addMenu(self, title, pixmap=None):
            return FakeMenu(self)

        def exec(self, pos=None):
            pass

    monkeypatch.setattr(hacker, "HackerMenu", FakeMenu)
    monkeypatch.setattr(stlibs.SharingData.theme, "Menu", FakeMenu, raising=False)

    pet.show_context_menu(QPoint(10, 10))

    assert "menu" in opened, "菜单应该被建出来"
    assert pet.is_dragging is False, "开菜单时要把 is_dragging 清掉"
    assert pet.drag_position is None, "开菜单时要把抓取点清掉"
    assert pet.drag_start_position is None


def test_real_context_menu_wipes_host_drag_state_on_open_and_close(make_pet, monkeypatch):
    """走真实路径：show_context_menu 建真的 HackerMenu，开与关都要清干净桌宠状态。"""
    from stlibs.themes import hacker

    pet = make_pet()
    pet._dragging = True
    pet.is_dragging = True
    pet.drag_position = QtCore.QPointF(1, 1)
    pet.drag_start_position = QPoint(1, 1)

    created = []
    original_init = hacker.HackerMenu.__init__

    def spy_init(self, parent=None):
        original_init(self, parent)
        created.append(self)

    monkeypatch.setattr(hacker.HackerMenu, "__init__", spy_init)
    # exec 会阻塞在模态循环里，而且真弹 Popup 会留下 grab（后面的菜单用例就废了）
    monkeypatch.setattr(hacker.HackerMenu, "show", lambda self: QtWidgets.QWidget.setVisible(self, True))
    monkeypatch.setattr(hacker.HackerMenu, "exec", lambda self, pos=None: self.show())

    pet.show_context_menu(QPoint(10, 10))
    QtWidgets.QApplication.processEvents()

    assert created, "应该建出了一个真菜单"
    menu = created[-1]
    assert getattr(menu, "_pet_drag_reset_hooked", False), "关闭钩子要挂上"

    assert pet.is_dragging is False, "开菜单时要先清干净"
    assert pet.drag_position is None
    assert pet._dragging is False, "桌宠自己的拖拽标志也要清（它才是漂移的元凶）"

    # 菜单收起：钩子再清一次，保证"被 Popup 吃掉 release"之后不会卡住
    pet._dragging = True
    pet.is_dragging = True
    menu.close()
    QtWidgets.QApplication.processEvents()
    assert pet._dragging is False
    assert pet.is_dragging is False
