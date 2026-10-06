"""UI 冲突检测的行为验证。

每条检查都配一组「应该报」和「不该报」的样例——后者更重要，
误报会让 CI 门禁失去信任。
"""

from __future__ import annotations

from conftest import findings_of, run_checks

WIDGET_IMPORTS = "from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout\nfrom PySide6.QtCore import Signal\n\n\n"


def test_duplicate_class(mini_repo):
    root = mini_repo(
        {
            "pkg/mod.py": (
                "class Widget(QWidget):\n"
                "    pass\n"
                "\n"
                "\n"
                "class Widget(QWidget):\n"
                "    pass\n"
            ).replace("QWidget", "object")
        }
    )
    findings = findings_of(root, "ui/duplicate-class")
    assert len(findings) == 1
    assert "第 5 行" in findings[0].message


def test_object_name_collision(mini_repo):
    root = mini_repo(
        {
            "pkg/mod.py": WIDGET_IMPORTS + (
                "class PageA(QWidget):\n"
                "    def __init__(self):\n"
                "        super().__init__()\n"
                "        self.setObjectName('shared')\n"
                "\n"
                "\n"
                "class PageB(QWidget):\n"
                "    def __init__(self):\n"
                "        super().__init__()\n"
                "        self.setObjectName('shared')\n"
            )
        }
    )
    findings = findings_of(root, "ui/object-name-collision")
    assert len(findings) == 1
    assert "PageA" in findings[0].message and "PageB" in findings[0].message


def test_unknown_stylesheet_class_is_error(mini_repo):
    root = mini_repo(
        {
            "pkg/mod.py": WIDGET_IMPORTS + (
                "class Bubble(QWidget):\n"
                "    def __init__(self):\n"
                "        super().__init__()\n"
                "        self.setStyleSheet('HackerBubbl { background: #000; }')\n"
            )
        }
    )
    findings = findings_of(root, "ui/stylesheet-class")
    assert len(findings) == 1
    assert findings[0].severity.value == "error"
    assert "HackerBubbl" in findings[0].message


def test_known_classes_and_comments_are_ignored(mini_repo):
    root = mini_repo(
        {
            "pkg/mod.py": WIDGET_IMPORTS + (
                "class Bubble(QWidget):\n"
                "    def __init__(self):\n"
                "        super().__init__()\n"
                "        self.setStyleSheet('''\n"
                "            /* Hover 状态，Tab 切换 */\n"
                "            Bubble { background: rgba(0, 0, 0, 150); }\n"
                "            Bubble:hover { border: 1px solid #00FF00; }\n"
                "            QScrollBar::handle:vertical { min-height: 30px; }\n"
                "            QComboBox QAbstractItemView { color: #00FF00; }\n"
                "        ''')\n"
            )
        }
    )
    assert findings_of(root, "ui/stylesheet-class") == []


def test_stylesheet_dead_id_and_hex_colors(mini_repo):
    root = mini_repo(
        {
            "pkg/mod.py": WIDGET_IMPORTS + (
                "class Menu(QWidget):\n"
                "    def __init__(self):\n"
                "        super().__init__()\n"
                "        self.box = QWidget(self)\n"
                "        self.box.setObjectName('box')\n"
                "        self.setStyleSheet('#box { background: #0a0a0a; }')\n"
                "        self.setStyleSheet('color: #BDC3C7;')\n"
                "        self.setStyleSheet('#ghost { color: red; }')\n"
            )
        }
    )
    findings = findings_of(root, "ui/stylesheet-dead-id")
    assert len(findings) == 1
    assert "ghost" in findings[0].message


def test_stylesheet_from_attribute_is_scanned(mini_repo):
    root = mini_repo(
        {
            "pkg/mod.py": WIDGET_IMPORTS + (
                "class Button(QWidget):\n"
                "    normal_style = 'QPushButton { color: #000; }'\n"
                "    active_style = 'WrongName { color: #fff; }'\n"
                "\n"
                "    def setActive(self, active):\n"
                "        self.setStyleSheet(self.active_style if active else self.normal_style)\n"
            )
        }
    )
    findings = findings_of(root, "ui/stylesheet-class")
    assert [f.message for f in findings if "WrongName" in f.message]


def test_double_parent(mini_repo):
    root = mini_repo(
        {
            "pkg/mod.py": WIDGET_IMPORTS + (
                "class Page(QWidget):\n"
                "    def __init__(self):\n"
                "        super().__init__()\n"
                "        first = QVBoxLayout(self)\n"
                "        second = QHBoxLayout()\n"
                "        child = QWidget(self)\n"
                "        first.addWidget(child)\n"
                "        second.addWidget(child)\n"
            )
        }
    )
    findings = findings_of(root, "ui/double-parent")
    assert len(findings) == 1
    assert "child" in findings[0].message


def test_layout_vs_geometry(mini_repo):
    root = mini_repo(
        {
            "pkg/mod.py": WIDGET_IMPORTS + (
                "class Page(QWidget):\n"
                "    def __init__(self):\n"
                "        super().__init__()\n"
                "        layout = QVBoxLayout(self)\n"
                "        self.card = QWidget(self)\n"
                "        layout.addWidget(self.card)\n"
                "        self.card.setGeometry(0, 0, 100, 100)\n"
            )
        }
    )
    findings = findings_of(root, "ui/layout-vs-geometry")
    assert len(findings) == 1
    assert "self.card" in findings[0].message


def test_layout_vs_geometry_with_chained_creation(mini_repo):
    """``HackerLabel("X", self).setGeometry(...)`` 这种链式写法也要被跟踪。"""
    root = mini_repo(
        {
            "pkg/mod.py": WIDGET_IMPORTS + (
                "class Page(QWidget):\n"
                "    def __init__(self):\n"
                "        super().__init__()\n"
                "        layout = QVBoxLayout(self)\n"
                "        layout.addWidget(QWidget(self))\n"
                "        QWidget(self).setGeometry(0, 0, 10, 10)\n"
            )
        }
    )
    findings = findings_of(root, "ui/layout-vs-geometry")
    assert len(findings) == 1
    assert "QWidget(self)" in findings[0].message


def test_chained_receivers_do_not_collide_across_different_text(mini_repo):
    """文本不同的两个匿名控件不能被当成同一个。"""
    root = mini_repo(
        {
            "pkg/mod.py": WIDGET_IMPORTS + (
                "class Page(QWidget):\n"
                "    def __init__(self):\n"
                "        super().__init__()\n"
                "        layout = QVBoxLayout(self)\n"
                "        layout.addWidget(QWidget(self, objectName='a'))\n"
                "        QWidget(self, objectName='b').setGeometry(0, 0, 10, 10)\n"
            )
        }
    )
    assert findings_of(root, "ui/layout-vs-geometry") == []


def test_geometry_without_layout_is_fine(mini_repo):
    root = mini_repo(
        {
            "pkg/mod.py": WIDGET_IMPORTS + (
                "class Page(QWidget):\n"
                "    def __init__(self):\n"
                "        super().__init__()\n"
                "        self.title = QWidget(self)\n"
                "        self.title.setGeometry(0, 0, 100, 30)\n"
                "        layout = QVBoxLayout(self)\n"
                "        self.other = QWidget(self)\n"
                "        layout.addWidget(self.other)\n"
            )
        }
    )
    assert findings_of(root, "ui/layout-vs-geometry") == []


def test_duplicate_setlayout(mini_repo):
    root = mini_repo(
        {
            "pkg/mod.py": WIDGET_IMPORTS + (
                "class Page(QWidget):\n"
                "    def __init__(self):\n"
                "        super().__init__()\n"
                "        self.setLayout(QVBoxLayout())\n"
                "        self.setLayout(QHBoxLayout())\n"
            )
        }
    )
    findings = findings_of(root, "ui/duplicate-setlayout")
    assert len(findings) == 1


def test_size_constraint_conflict(mini_repo):
    root = mini_repo(
        {
            "pkg/mod.py": WIDGET_IMPORTS + (
                "class Page(QWidget):\n"
                "    def __init__(self):\n"
                "        super().__init__()\n"
                "        self.setFixedHeight(30)\n"
                "        self.setMinimumHeight(60)\n"
            )
        }
    )
    findings = findings_of(root, "ui/size-constraint")
    assert len(findings) == 1


def test_window_flag_conflict(mini_repo):
    root = mini_repo(
        {
            "pkg/mod.py": (
                "from PySide6.QtCore import Qt\n"
                "from PySide6.QtWidgets import QWidget\n"
                "\n"
                "\n"
                "class Page(QWidget):\n"
                "    def __init__(self):\n"
                "        super().__init__()\n"
                "        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.WindowStaysOnBottomHint)\n"
            )
        }
    )
    findings = findings_of(root, "ui/window-flags")
    assert len(findings) == 1


def test_signal_clash(mini_repo):
    root = mini_repo(
        {
            "pkg/mod.py": WIDGET_IMPORTS + (
                "class Switch(QWidget):\n"
                "    stateChanged = Signal(bool)\n"
                "\n"
                "    def stateChanged(self):\n"
                "        return None\n"
            )
        }
    )
    findings = findings_of(root, "ui/signal-clash")
    assert len(findings) == 1


def test_signal_slot_arity_is_checked_for_project_signals(mini_repo):
    root = mini_repo(
        {
            "pkg/mod.py": WIDGET_IMPORTS + (
                "class Switch(QWidget):\n"
                "    stateChanged = Signal(bool)\n"
                "\n"
                "    def __init__(self):\n"
                "        super().__init__()\n"
                "        self.stateChanged.connect(self.needs_two)\n"
                "\n"
                "    def needs_two(self, a, b):\n"
                "        return a, b\n"
            )
        }
    )
    findings = findings_of(root, "ui/signal-slot")
    assert len(findings) == 1
    assert "needs_two" in findings[0].message


def test_signal_slot_ignores_qt_signals_with_same_name(mini_repo):
    """QToolButton.clicked(bool) 不能被项目里的 clicked = Signal() 带偏。"""
    root = mini_repo(
        {
            "pkg/mod.py": WIDGET_IMPORTS + (
                "class Nav(QWidget):\n"
                "    clicked = Signal()\n"
                "\n"
                "\n"
                "class Header(QWidget):\n"
                "    def __init__(self, header):\n"
                "        super().__init__()\n"
                "        header.clicked.connect(self._toggle)\n"
                "\n"
                "    def _toggle(self, checked):\n"
                "        return checked\n"
            )
        }
    )
    assert findings_of(root, "ui/signal-slot") == []


def test_signal_slot_accepts_fewer_arguments(mini_repo):
    """PySide6 允许槽函数少收参数，这不算错。"""
    root = mini_repo(
        {
            "pkg/mod.py": WIDGET_IMPORTS + (
                "class Switch(QWidget):\n"
                "    stateChanged = Signal(bool)\n"
                "\n"
                "    def __init__(self):\n"
                "        super().__init__()\n"
                "        self.stateChanged.connect(self.ignore_args)\n"
                "\n"
                "    def ignore_args(self):\n"
                "        return None\n"
            )
        }
    )
    assert findings_of(root, "ui/signal-slot") == []


def test_dead_control_detected(mini_repo):
    root = mini_repo(
        {
            "pkg/mod.py": (
                "from PySide6.QtWidgets import QComboBox, QWidget\n"
                "\n"
                "\n"
                "class Page(QWidget):\n"
                "    def __init__(self):\n"
                "        super().__init__()\n"
                "        combo = QComboBox(self)\n"
                "        combo.addItems(['a', 'b'])\n"
            )
        }
    )
    findings = findings_of(root, "ui/dead-control")
    assert len(findings) == 1
    assert "combo" in findings[0].message


def test_dead_control_connected_in_other_method_is_fine(mini_repo):
    root = mini_repo(
        {
            "pkg/mod.py": (
                "from PySide6.QtWidgets import QComboBox, QWidget\n"
                "\n"
                "\n"
                "class Page(QWidget):\n"
                "    def __init__(self):\n"
                "        super().__init__()\n"
                "        self.combo = QComboBox(self)\n"
                "        self.combo.currentTextChanged.connect(self.on_change)\n"
                "\n"
                "    def fill(self):\n"
                "        self.combo.addItems(['a', 'b'])\n"
                "\n"
                "    def on_change(self, text):\n"
                "        return text\n"
            )
        }
    )
    assert findings_of(root, "ui/dead-control") == []


def test_style_overwrite_only_within_same_branch(mini_repo):
    root = mini_repo(
        {
            "pkg/mod.py": WIDGET_IMPORTS + (
                "class Button(QWidget):\n"
                "    def setActive(self, active):\n"
                "        if active:\n"
                "            self.setStyleSheet('A { color: red; }')\n"
                "        else:\n"
                "            self.setStyleSheet('A { color: blue; }')\n"
                "\n"
                "    def twice(self):\n"
                "        self.setStyleSheet('A { color: red; }')\n"
                "        self.setStyleSheet('A { color: blue; }')\n"
            )
        }
    )
    findings = findings_of(root, "ui/style-overwrite")
    assert len(findings) == 1
    assert findings[0].location.symbol == "twice"


def test_missing_super_init(mini_repo):
    root = mini_repo(
        {
            "pkg/mod.py": WIDGET_IMPORTS + (
                "class Card(QWidget):\n"
                "    def __init__(self, parent=None):\n"
                "        self.parent = parent\n"
                "\n"
                "\n"
                "class Good(QWidget):\n"
                "    def __init__(self, parent=None):\n"
                "        super().__init__(parent)\n"
                "\n"
                "\n"
                "class AlsoGood(QWidget):\n"
                "    def __init__(self, placeholder=None, parent=None):\n"
                "        super().__init__(parent if isinstance(placeholder, str) else placeholder)\n"
            )
        }
    )
    findings = findings_of(root, "ui/missing-super-init")
    assert len(findings) == 1
    assert "Card" in findings[0].message


def test_ui_checks_do_not_crash_on_real_repo(repo_root):
    report = run_checks(repo_root, ["ui/*"])
    assert report.crashes == [], [r.crash for r in report.crashes]
    assert report.findings == []
