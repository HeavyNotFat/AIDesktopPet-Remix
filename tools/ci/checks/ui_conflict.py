from __future__ import annotations

import ast
import re
from collections import defaultdict
from typing import Iterable, Iterator

from ..core import Finding, Location, Severity
from ..source import SourceFile, iter_calls

# 样式选择器里允许出现的 Qt 类名（常用集合，不是全集；未知的 Q* 只给提示）
QT_CLASSES: frozenset[str] = frozenset(
    """
    QObject QWidget QFrame QLabel QAbstractButton QPushButton QToolButton QRadioButton QCheckBox
    QLineEdit QTextEdit QPlainTextEdit QSpinBox QDoubleSpinBox QComboBox QSlider QScrollBar
    QScrollArea QAbstractScrollArea QAbstractItemView QListView QTreeView QTableView QHeaderView
    QTableWidget QTableWidgetItem QListWidget QTreeWidget QTabWidget QTabBar QStackedWidget
    QGroupBox QDialog QMainWindow QMenu QMenuBar QStatusBar QToolBar QDockWidget QSplashScreen
    QProgressBar QSplitter QToolBox QCalendarWidget QLCDNumber QGraphicsView QGraphicsScene
    QShortcut QAction QSizeGrip QRubberBand QFileDialog QMessageBox QInputDialog QColorDialog
    QFontDialog QWizard QMdiArea QMdiSubWindow QTextBrowser QCommandLinkButton QFocusFrame
    QColumnView QUndoView QOpenGLWidget QVideoWidget QAbstractSpinBox
    """.split()
)

# 互斥的 window flag
EXCLUSIVE_FLAGS: tuple[tuple[str, str], ...] = (
    ("WindowStaysOnTopHint", "WindowStaysOnBottomHint"),
)

SIZE_FIXED = {"setFixedSize", "setFixedWidth", "setFixedHeight"}
SIZE_RANGE = {
    "setMinimumSize",
    "setMaximumSize",
    "setMinimumWidth",
    "setMaximumWidth",
    "setMinimumHeight",
    "setMaximumHeight",
}

CONTAINER_METHODS = {"addWidget", "insertWidget", "addTab", "insertTab"}
POPULATE_METHODS = {"addItem", "addItems", "addItemText"}
CONNECT_METHODS = {"connect", "connectSlotsByName"}

_SELECTOR_ID_RE = re.compile(r"#([A-Za-z_][\w-]*)")
_SELECTOR_TYPE_RE = re.compile(r"(?:^|[\s,>+~(])([A-Z][A-Za-z0-9_]*)\s*(?=[#:.{\s,])")
_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_HEX_COLOR_RE = re.compile(r"^[0-9A-Fa-f]{3,8}$")

# Qt 自带信号名。同名信号在项目里也有定义时（例如 HackerSwitch.stateChanged），
# 只有在接收者类型能确定的情况下才按项目信号算，否则放过，避免误报。
QT_SIGNAL_NAMES: frozenset[str] = frozenset(
    """
    clicked pressed released toggled triggered hovered destroyed
    textChanged textEdited editingFinished returnPressed selectionChanged
    currentTextChanged currentIndexChanged currentRowChanged currentChanged activated highlighted
    valueChanged sliderMoved itemChanged itemSelectionChanged cellChanged itemClicked itemDoubleClicked
    finished stateChanged windowTitleChanged tabCloseRequested timeout readyRead linkActivated
    anchorClicked customContextMenuRequested doubleClicked accepted rejected
    """.split()
)


# 通用小工具
def _dotted(node: ast.AST) -> str:
    return ast.unparse(node)


def _receiver(node: ast.Call) -> str | None:
    value = node.func.value if isinstance(node.func, ast.Attribute) else None
    if isinstance(value, (ast.Name, ast.Attribute)):
        return _dotted(value)
    if isinstance(value, ast.Call):
        return _dotted(value)
    return None


def _iter_functions(sources) -> Iterator[tuple[SourceFile, ast.AST]]:
    for src in sources.files:
        for node in ast.walk(src.tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                yield src, node


def _class_owner_map(sources) -> dict[int, str]:
    owners: dict[int, str] = {}
    for record in sources.classes:
        for node in ast.walk(record.node):
            owners[id(node)] = record.name
    return owners


# ui/duplicate-class
def check_duplicate_class(ctx) -> Iterator[Finding]:
    for src in ctx.sources.files:
        seen: dict[str, ast.ClassDef] = {}
        for node in src.tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            if node.name in seen:
                yield Finding(
                    check="ui/duplicate-class",
                    severity=Severity.ERROR,
                    message=(
                        f"{src.rel} 里 {node.name} 定义了两次"
                        f"（第 {seen[node.name].lineno} 行与第 {node.lineno} 行），后者会覆盖前者"
                    ),
                    location=Location.of(node, src.rel, node.name),
                    hint="删掉旧定义，或把其中一个改名/拆到独立模块",
                )
            seen[node.name] = node


# 样式表相关
def _stylesheet_literals(ctx) -> Iterator[tuple[SourceFile, ast.AST, str]]:
    constants: dict[str, str] = {}
    declared: list[tuple[SourceFile, ast.AST, str]] = []

    def remember(src: SourceFile, name: str, value: ast.AST, *, reportable: bool) -> None:
        text = _string_of(value)
        if text is None:
            return
        constants.setdefault(name, text)
        if reportable and "style" in name.lower() and "{" in text:
            declared.append((src, value, text))

    for record in ctx.sources.classes:
        for name, value in record.attributes.items():
            remember(record.file, name, value, reportable=True)
            remember(record.file, f"{record.name}.{name}", value, reportable=False)
    for src in ctx.sources.files:
        for name, value in ctx.sources.assignments_by_module().get(src.module, {}).items():
            remember(src, name, value, reportable=True)

    seen: set[tuple[str, int]] = set()
    for src, node in ctx.sources.iter_nodes(ast.Call):
        if isinstance(node.func, ast.Attribute) and node.func.attr == "setStyleSheet" and node.args:
            arg = node.args[0]
            text = _string_of(arg)
            if text is None and isinstance(arg, (ast.Name, ast.Attribute)):
                text = constants.get(_dotted(arg)) or constants.get(_dotted(arg).rpartition(".")[2])
            if text is not None:
                key = (src.rel, node.lineno)
                if key not in seen:
                    seen.add(key)
                    yield src, node, text

    for src, node, text in declared:
        key = (src.rel, getattr(node, "lineno", 0))
        if key in seen:
            continue
        seen.add(key)
        yield src, node, text


def _string_of(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts = [p.value for p in node.values if isinstance(p, ast.Constant) and isinstance(p.value, str)]
        return "".join(parts) if parts else None
    return None


def _strip_blocks(qss: str) -> str:
    qss = _COMMENT_RE.sub(" ", qss)
    out: list[str] = []
    depth = 0
    for char in qss:
        if char == "{":
            depth += 1
        elif char == "}":
            depth = max(0, depth - 1)
        elif depth == 0:
            out.append(char)
    return "".join(out)


def _object_names(ctx) -> dict[str, list[Location]]:
    names: dict[str, list[Location]] = defaultdict(list)
    owners = _class_owner_map(ctx.sources)
    for src, node in ctx.sources.iter_nodes(ast.Call):
        if not isinstance(node.func, ast.Attribute) or node.func.attr != "setObjectName":
            continue
        text = _string_of(node.args[0]) if node.args else None
        if text:
            names[text].append(Location.of(node, src.rel, owners.get(id(node))))
    return names


def check_object_name_collision(ctx) -> Iterator[Finding]:
    for name, locations in _object_names(ctx).items():
        owners = {loc.symbol for loc in locations}
        if len(locations) < 2 or len(owners) < 2:
            continue
        yield Finding(
            check="ui/object-name-collision",
            severity=Severity.ERROR,
            message=(
                f"objectName {name!r} 被 {len(owners)} 个类同时使用"
                f"（{'、'.join(sorted(o for o in owners if o))}），"
                "#id 样式选择器会打到所有同名控件上"
            ),
            location=locations[0],
            hint="objectName 保持全局唯一，或改用属性选择器区分",
        )


def check_stylesheet_class(ctx) -> Iterator[Finding]:
    """样式里引用了不存在的类选择器（最典型的是类名拼错一个字母）。"""
    project_classes = {record.name for record in ctx.sources.classes}
    allowed = ctx.settings.allow_tokens("ui/stylesheet-class")
    reported: set[tuple[str, str]] = set()

    for src, node, qss in _stylesheet_literals(ctx):
        for match in _SELECTOR_TYPE_RE.finditer(_strip_blocks(qss)):
            name = match.group(1)
            if name in QT_CLASSES or name in project_classes or name in allowed:
                continue
            key = (src.rel, name)
            if key in reported:
                continue
            reported.add(key)
            if name.startswith("Q"):
                yield Finding(
                    check="ui/stylesheet-class",
                    severity=Severity.WARNING,
                    message=f"样式里的 {name} 不在已知 Qt 类清单里，选择器可能整条不生效",
                    location=Location.of(node, src.rel),
                    hint=f'确认无误就把 "ui/stylesheet-class:{name}" 加进 pyproject 的 allow',
                )
            else:
                yield Finding(
                    check="ui/stylesheet-class",
                    severity=Severity.ERROR,
                    message=f"样式里的类选择器 {name} 在项目中不存在，整条规则会被 Qt 忽略",
                    location=Location.of(node, src.rel),
                    hint="检查类名拼写；自定义控件要用它真实的类名",
                )


def check_stylesheet_dead_id(ctx) -> Iterator[Finding]:
    known = set(_object_names(ctx))
    allowed = ctx.settings.allow_tokens("ui/stylesheet-dead-id")
    reported: set[str] = set()
    for src, node, qss in _stylesheet_literals(ctx):
        for match in _SELECTOR_ID_RE.finditer(_strip_blocks(qss)):
            name = match.group(1)
            if name in known or name in allowed or name in reported:
                continue
            if _HEX_COLOR_RE.match(name):
                continue  # 无花括号的样式里 "#00FF00" 是颜色，不是 id 选择器
            reported.add(name)
            yield Finding(
                check="ui/stylesheet-dead-id",
                severity=Severity.WARNING,
                message=f"样式引用了 #{name}，但项目里没有任何 setObjectName({name!r})",
                location=Location.of(node, src.rel),
                hint=f"补上 setObjectName({name!r})，或删掉这条死规则",
            )


# 布局 / 几何 / 尺寸
def _scope_calls(func: ast.AST) -> dict[tuple[str, ...], dict[str, list[ast.Call]]]:
    """分支路径 → 接收者 → 该接收者上的调用。"""
    scopes: dict[tuple[str, ...], dict[str, list[ast.Call]]] = defaultdict(lambda: defaultdict(list))
    for path, node in iter_calls(func):
        receiver = _receiver(node)
        if receiver is None:
            continue
        scopes[path][receiver].append(node)
    return scopes


def check_double_parent(ctx) -> Iterator[Finding]:
    """同一个控件被 addWidget/insertWidget/addTab 到两个不同容器。"""
    for src, func in _iter_functions(ctx.sources):
        for path, receivers in _scope_calls(func).items():
            parents: dict[str, set[str]] = defaultdict(set)
            first: dict[str, ast.Call] = {}
            for container, calls in receivers.items():
                for call in calls:
                    method = call.func.attr
                    if method not in CONTAINER_METHODS:
                        continue
                    index = 1 if method in {"insertWidget", "insertTab"} else 0
                    if len(call.args) <= index:
                        continue
                    child = _dotted(call.args[index])
                    parents[child].add(container)
                    first.setdefault(child, call)
            for child, containers in parents.items():
                if len(containers) < 2:
                    continue
                yield Finding(
                    check="ui/double-parent",
                    severity=Severity.ERROR,
                    message=(
                        f"{child} 被加进多个布局/容器（{'、'.join(sorted(containers))}），"
                        "Qt 会把它从前者摘走，界面莫名少控件"
                    ),
                    location=Location.of(first[child], src.rel, getattr(func, "name", "")),
                    hint="一个控件只属于一个布局；要复用就各自新建一个",
                )


def check_layout_vs_geometry(ctx) -> Iterator[Finding]:
    for src, func in _iter_functions(ctx.sources):
        for path, receivers in _scope_calls(func).items():
            geometry: dict[str, ast.Call] = {}
            in_layout: set[str] = set()
            for receiver, calls in receivers.items():
                for call in calls:
                    method = call.func.attr
                    if method == "setGeometry":
                        geometry[receiver] = call
                    elif method in CONTAINER_METHODS:
                        index = 1 if method in {"insertWidget", "insertTab"} else 0
                        if len(call.args) > index:
                            in_layout.add(_dotted(call.args[index]))
                    elif method == "setLayout":
                        in_layout.add(receiver)
            for name, call in geometry.items():
                if name not in in_layout:
                    continue
                yield Finding(
                    check="ui/layout-vs-geometry",
                    severity=Severity.WARNING,
                    message=f"{name} 既被布局接管又手工 setGeometry，实际位置由布局决定，setGeometry 会被忽略",
                    location=Location.of(call, src.rel, getattr(func, "name", "")),
                    hint="二选一：交给布局，或去掉 setLayout/addWidget",
                )


def check_duplicate_setlayout(ctx) -> Iterator[Finding]:
    for src, func in _iter_functions(ctx.sources):
        for path, receivers in _scope_calls(func).items():
            for receiver, calls in receivers.items():
                layouts = [call for call in calls if call.func.attr == "setLayout"]
                if len(layouts) < 2:
                    continue
                yield Finding(
                    check="ui/duplicate-setlayout",
                    severity=Severity.ERROR,
                    message=f"{receiver} 在同一分支里调用了 {len(layouts)} 次 setLayout，只有最后一次生效",
                    location=Location.of(layouts[1], src.rel, getattr(func, "name", "")),
                    hint="合并成一个布局，或用 QStackedWidget 承载多套布局",
                )


def check_size_constraint(ctx) -> Iterator[Finding]:
    for src, func in _iter_functions(ctx.sources):
        for path, receivers in _scope_calls(func).items():
            for receiver, calls in receivers.items():
                fixed = [call for call in calls if call.func.attr in SIZE_FIXED]
                ranged = [call for call in calls if call.func.attr in SIZE_RANGE]
                if not fixed or not ranged:
                    continue
                yield Finding(
                    check="ui/size-constraint",
                    severity=Severity.WARNING,
                    message=(
                        f"{receiver} 同时用了 {fixed[0].func.attr} 与 {ranged[0].func.attr}，"
                        "固定尺寸和尺寸范围会互相覆盖"
                    ),
                    location=Location.of(ranged[0], src.rel, getattr(func, "name", "")),
                    hint="只保留一种尺寸策略",
                )


def check_window_flags(ctx) -> Iterator[Finding]:
    for src, func in _iter_functions(ctx.sources):
        for path, node in iter_calls(func):
            text = _dotted(node)
            for left, right in EXCLUSIVE_FLAGS:
                if left in text and right in text:
                    yield Finding(
                        check="ui/window-flags",
                        severity=Severity.ERROR,
                        message=f"同时设置了 Qt.{left} 与 Qt.{right}，两者互斥",
                        location=Location.of(node, src.rel, getattr(func, "name", "")),
                        hint="只保留一个",
                    )


def check_style_overwrite(ctx) -> Iterator[Finding]:
    for src, func in _iter_functions(ctx.sources):
        for path, receivers in _scope_calls(func).items():
            for receiver, calls in receivers.items():
                styles = [call for call in calls if call.func.attr == "setStyleSheet"]
                if len(styles) < 2:
                    continue
                yield Finding(
                    check="ui/style-overwrite",
                    severity=Severity.WARNING,
                    message=(
                        f"{receiver} 在同一分支里调用了 {len(styles)} 次 setStyleSheet，"
                        "前一次的样式会被整体替换"
                    ),
                    location=Location.of(styles[1], src.rel, getattr(func, "name", "")),
                    hint="合并成一份样式表，或按状态二选一",
                )


# 控件接线
def check_dead_control(ctx) -> Iterator[Finding]:
    """下拉框/列表填了数据却没有任何信号连接，用户点了不会有反应。"""
    for src, func in _iter_functions(ctx.sources):
        for path, receivers in _scope_calls(func).items():
            connected: set[str] = set()
            populated: dict[str, ast.Call] = {}
            for receiver, calls in receivers.items():
                for call in calls:
                    method = call.func.attr
                    if method == "connect":
                        # 连的是「接收者」而不是槽函数：self.x.sig.connect(slot)
                        connected.add(_dotted(call.func.value).rpartition(".")[0])
                    elif method in POPULATE_METHODS:
                        populated.setdefault(receiver, call)
            for receiver, call in populated.items():
                if receiver in connected:
                    continue
                # 同名属性可能在别的方法里接线
                if _connected_anywhere(ctx, receiver.rpartition(".")[2]):
                    continue
                yield Finding(
                    check="ui/dead-control",
                    severity=Severity.WARNING,
                    message=f"{receiver} 填了选项但没有任何信号连接（currentTextChanged/activated…），交互不会生效",
                    location=Location.of(call, src.rel, getattr(func, "name", "")),
                    hint="接上对应的信号，或把这个控件去掉",
                )


def _connected_anywhere(ctx, attribute: str) -> bool:
    """项目里是否有 ``<某控件>.<信号>.connect(...)`` 指向这个属性名。"""
    for _, node in ctx.sources.iter_nodes(ast.Call):
        if not (isinstance(node.func, ast.Attribute) and node.func.attr == "connect"):
            continue
        # self.x.sig.connect → 去掉信号名，剩下 self.x
        receiver = _dotted(node.func.value).rpartition(".")[0]
        if receiver.rpartition(".")[2] == attribute:
            return True
    return False


# 信号
def _declared_signals(ctx) -> tuple[dict[str, int], dict[str, ast.AST], set[str]]:
    arity: dict[str, int] = {}
    nodes: dict[str, ast.AST] = {}
    qualified: set[str] = set()
    for record in ctx.sources.classes:
        for name, value in record.attributes.items():
            if not _is_signal(value):
                continue
            arity.setdefault(name, len(value.args))
            nodes.setdefault(name, value)
            qualified.add(f"{record.name}.{name}")
    return arity, nodes, qualified


def _is_signal(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and _dotted(node.func).rpartition(".")[2] == "Signal"


def check_signal_clash(ctx) -> Iterator[Finding]:
    for record in ctx.sources.classes:
        signals: dict[str, ast.AST] = {}
        for name, value in record.attributes.items():
            if not _is_signal(value):
                continue
            if name in signals:
                yield Finding(
                    check="ui/signal-clash",
                    severity=Severity.ERROR,
                    message=f"{record.name}.{name} 声明了两个 Signal，前一个会丢失",
                    location=Location.of(value, record.file.rel, f"{record.name}.{name}"),
                    hint="删掉重复声明",
                )
            if name in record.methods:
                yield Finding(
                    check="ui/signal-clash",
                    severity=Severity.ERROR,
                    message=f"{record.name}.{name} 既是 Signal 又是方法，信号会被方法覆盖",
                    location=Location.of(record.methods[name], record.file.rel, f"{record.name}.{name}"),
                    hint="改掉其中一个名字",
                )
            signals[name] = value


def check_signal_slot(ctx) -> Iterator[Finding]:
    arity_by_class: dict[str, dict[str, int]] = defaultdict(dict)
    bare_arity: dict[str, int] = {}
    for record in ctx.sources.classes:
        for name, value in record.attributes.items():
            if not _is_signal(value):
                continue
            arity_by_class[record.name][name] = len(value.args)
            if name not in QT_SIGNAL_NAMES:
                bare_arity.setdefault(name, len(value.args))

    methods: dict[str, ast.AST] = {}
    for record in ctx.sources.classes:
        for name, node in record.methods.items():
            methods.setdefault(name, node)

    for src, func in _iter_functions(ctx.sources):
        local_types = _local_types(func)
        owner = _owning_class_name(ctx, func)
        for path, node in iter_calls(func):
            if not (isinstance(node.func, ast.Attribute) and node.func.attr == "connect"):
                continue
            if not node.args:
                continue

            receiver = _dotted(node.func.value)
            signal_name = receiver.rpartition(".")[2]
            expected = _signal_arity(arity_by_class, bare_arity, receiver, signal_name, local_types, owner)
            if expected is None:
                continue

            slot_name = _dotted(node.args[0]).rpartition(".")[2]
            target = methods.get(slot_name)
            if not isinstance(target, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            needed = len(_required_positional(target))
            if needed <= expected:
                continue
            yield Finding(
                check="ui/signal-slot",
                severity=Severity.ERROR,
                message=(
                    f"{signal_name} 只有 {expected} 个参数，但槽函数 {slot_name} 需要 {needed} 个必填参数，"
                    "触发时会 TypeError"
                ),
                location=Location.of(node, src.rel, getattr(func, "name", "")),
                hint="给槽函数多余的参数加默认值，或换成签名匹配的信号",
            )


def _signal_arity(
    arity_by_class: dict[str, dict[str, int]],
    bare_arity: dict[str, int],
    receiver: str,
    signal_name: str,
    local_types: dict[str, str],
    owner: str | None,
) -> int | None:
    object_part = receiver.rpartition(".")[0]
    receiver_type = _receiver_type(object_part, local_types, owner)
    if receiver_type:
        found = arity_by_class.get(receiver_type, {}).get(signal_name)
        if found is not None:
            return found
        # 类型确定但该类没有这个信号 → 是 Qt 继承来的，不猜
        return None
    return bare_arity.get(signal_name)


def _receiver_type(receiver: str, local_types: dict[str, str], owner: str | None) -> str | None:
    if receiver in {"self", ""}:
        return owner
    if receiver in local_types:
        return local_types[receiver]
    return None


def _local_types(func: ast.AST) -> dict[str, str]:
    """``x = HackerSwitch(...)`` / ``self.x = HackerComboBox(...)`` → 变量类型。"""
    types: dict[str, str] = {}
    for node in ast.walk(func):
        if not isinstance(node, ast.Assign):
            continue
        if not isinstance(node.value, ast.Call) or not isinstance(node.value.func, ast.Name):
            continue
        for target in node.targets:
            if isinstance(target, (ast.Name, ast.Attribute)):
                types[_dotted(target)] = node.value.func.id
    return types


def _owning_class_name(ctx, func: ast.AST) -> str | None:
    for record in ctx.sources.classes:
        if any(child is func for child in ast.walk(record.node)):
            return record.name
    return None


def _required_positional(node: ast.AST) -> list[ast.arg]:
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return []
    args = [*node.args.posonlyargs, *node.args.args]
    if args and args[0].arg in {"self", "cls"}:
        args = args[1:]
    defaults = len(node.args.defaults)
    if defaults:
        args = args[: len(args) - defaults]
    return args


# 父子关系
def check_missing_super_init(ctx) -> Iterator[Finding]:
    """QWidget 子类把 parent 收下却没交给 super()，控件会脱离父子树。"""
    for record in ctx.sources.classes:
        init = record.methods.get("__init__")
        if init is None or not init.args.args:
            continue
        params = {arg.arg for arg in init.args.args if arg.arg not in {"self", "cls"}}
        if "parent" not in params:
            continue
        if not any(_looks_like_widget(base) for base in record.bases):
            continue

        forwarded = False
        for node in ast.walk(init):
            if not _is_super_init_call(node):
                continue
            candidates = [*node.args, *(kw.value for kw in node.keywords)]
            if any(
                isinstance(sub, ast.Name) and sub.id == "parent"
                for candidate in candidates
                for sub in ast.walk(candidate)
            ):
                forwarded = True
        if forwarded:
            continue
        yield Finding(
            check="ui/missing-super-init",
            severity=Severity.WARNING,
            message=f"{record.name}.__init__ 收了 parent 却没有传给 super().__init__，控件不会挂到父对象上",
            location=Location.of(init, record.file.rel, f"{record.name}.__init__"),
            hint="在 __init__ 开头调用 super().__init__(parent)",
        )


def _is_super_init_call(node: ast.AST) -> bool:
    """``super().__init__(...)`` / ``super(X, self).__init__(...)``。"""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if not (isinstance(func, ast.Attribute) and func.attr == "__init__"):
        return False
    target = func.value
    if isinstance(target, ast.Call) and isinstance(target.func, ast.Name):
        return target.func.id == "super"
    return False


def _looks_like_widget(base: str) -> bool:
    name = base.rpartition(".")[2]
    return name.startswith("Q") or name.endswith(("Window", "Widget", "Page", "Bubble", "Card"))
