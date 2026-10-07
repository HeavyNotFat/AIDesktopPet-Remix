from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.platform

QtWidgets = pytest.importorskip("PySide6.QtWidgets", reason="需要 PySide6 才能验证 Qt 元类行为")


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


def test_plain_abcmeta_is_enforced():
    """对照组：纯 Python 的 ABCMeta 是生效的。"""
    from abc import ABCMeta, abstractmethod

    class Base(metaclass=ABCMeta):
        @abstractmethod
        def need_me(self): ...

    class Child(Base):
        pass

    assert Child.__abstractmethods__ == frozenset({"need_me"})
    with pytest.raises(TypeError):
        Child()


def test_qt_combined_metaclass_does_not_enforce(qapp):
    """结论：Qt 子类上的 @abstractmethod 只是文档。"""
    from abc import ABCMeta, abstractmethod

    from PySide6.QtWidgets import QWidget

    combined = type("CombinedMeta", (type(QWidget), ABCMeta), {})

    class Iface(metaclass=ABCMeta):
        @abstractmethod
        def need_me(self): ...

    class Incomplete(QWidget, Iface, metaclass=combined):
        pass

    assert not hasattr(Incomplete, "__abstractmethods__"), (
        "PySide6 开始生成 __abstractmethods__ 了：请重新评估 abs/* 静态检查的必要性"
    )
    Incomplete()  # 不抛异常，正是需要静态检查的原因


def test_theme_abs_classes_are_statically_complete(repo_root):
    """既然运行期不管，就由 CI 静态保证主题实现完整。"""
    from tools.ci import run

    report = run(root=repo_root, only=["abs/contract", "abs/instantiate"])
    assert report.findings == []


def test_shader_canvas_abstract_contract_is_static_only(repo_root):
    from tools.ci.checks.abstract_api import Hierarchy, is_abstract
    from tools.ci.settings import Settings
    from tools.ci.source import SourceIndex

    sources = SourceIndex(repo_root, Settings.load(repo_root))
    canvas = sources.class_in_module("shader", "ADPOpenGLCanvas")
    assert canvas is not None
    declared = {name for name, node in canvas.methods.items() if is_abstract(node)}
    assert declared == {"on_init", "on_draw", "on_resize"}

    hierarchy = Hierarchy(sources)
    child = sources.class_in_module("shader.live2d", "PublicShader")
    assert child is not None
    assert hierarchy.is_abc_derived(child)
    # 关键断言：子类没有留下任何未实现的抽象成员
    assert hierarchy.abstract_members(child) == {}, (
        "live2d.PublicShader 还缺画布钩子：PySide6 运行期不会拦，只会在 paintGL 里炸"
    )


def test_shader_static_branch_has_its_own_base(repo_root):
    """静态形象模式走 QWidget 另一条分支，不共享画布契约。"""
    from tools.ci.settings import Settings
    from tools.ci.source import SourceIndex

    sources = SourceIndex(repo_root, Settings.load(repo_root))
    static_shader = sources.class_in_module("shader.static", "PublicShader")
    assert static_shader is not None
    assert not any(base.rpartition(".")[2] == "ADPOpenGLCanvas" for base in static_shader.bases)


@pytest.fixture(scope="module")
def themes_module():
    import stlibs

    stlibs.Config.mcp["enable"] = False
    return pytest.importorskip("stlibs.themes", reason="主题包需要 PySide6")


def test_load_theme_resolves_and_falls_back(themes_module):
    """``stlibs.load_theme``：按配置取主题，名字写错时回退而不是崩在启动阶段。"""
    import stlibs

    assert stlibs.load_theme("hacker") is themes_module.hacker
    assert stlibs.load_theme() is themes_module.hacker
    assert stlibs.load_theme("") is themes_module.hacker
    assert stlibs.load_theme("   ") is themes_module.hacker
    assert stlibs.load_theme("does-not-exist") is themes_module.hacker, "未知主题必须回退到 hacker"


def test_every_discovered_theme_is_importable(themes_module):
    from stlibs.themes.hacker.settings import available_themes

    discovered = available_themes()
    assert discovered, "至少要有一个主题"
    for name in discovered:
        assert hasattr(themes_module, name), f"{name} 被 available_themes 列出来但没被导入"
