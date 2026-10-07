"""插件图标：清单里的自定义图 + 没有图时的字母徽章回退。"""

import os

import pytest

from stlibs.plugins.icons import (
    BADGE_COLORS,
    badge_color,
    badge_pixmap,
    initials,
    plugin_icon,
    plugin_pixmap,
)
from stlibs.plugins.manifest import ICON_SUFFIXES, PluginManifest, parse_manifest

pytestmark = pytest.mark.ui

QtGui = pytest.importorskip("PySide6.QtGui", reason="图标测试需要 PySide6")


@pytest.fixture(scope="module", autouse=True)
def qapp():
    """整个模块都要有 QApplication：没有它时构造 QPixmap 会直接终止进程。"""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    yield QApplication.instance() or QApplication([])


def make_manifest(directory, **raw):
    (directory / "main.py").write_text("def on_load(api):\n    pass\n", encoding="utf-8")
    payload = {"id": "demo", "name": "演示插件", "language": "python", "entry": "main.py"}
    payload.update(raw)
    return parse_manifest(directory, payload)


def write_png(directory, name, color=(255, 0, 0)):
    """真写一张 PNG（用 Qt 存，省得给测试引 Pillow 依赖）。"""
    from PySide6.QtGui import QColor, QPixmap

    pixmap = QPixmap(32, 32)
    pixmap.fill(QColor(*color))
    path = directory / name
    assert pixmap.save(str(path), "PNG")
    return path


# 清单字段
def test_manifest_reads_icon_and_menu(tmp_path):
    manifest = make_manifest(tmp_path, icon="icon.png", menu="演示组")

    assert manifest.icon == "icon.png"
    assert manifest.menu_title == "演示组"
    assert manifest.public()["icon"] == "icon.png"
    assert manifest.public()["menu"] == "演示组"


def test_menu_title_falls_back_to_name(tmp_path):
    manifest = make_manifest(tmp_path, name="没有组名的插件")

    assert manifest.icon == ""
    assert manifest.menu_title == "没有组名的插件"


@pytest.mark.parametrize("bad", [
    "../icon.png",           # 想爬出插件目录
    "/etc/passwd",           # 绝对路径
    "C:/windows/icon.png",   # 盘符路径
    "icon.gif",              # 不是支持的图片后缀
    "   ",                   # 空白
])
def test_manifest_rejects_bad_icon(tmp_path, bad):
    """图标写错不该让插件加载不了：静默当没写，回退徽章。"""
    manifest = make_manifest(tmp_path, icon=bad)

    assert manifest.icon == ""
    assert manifest.icon_path is None


def test_icon_suffix_list_covers_svg_and_png():
    assert ".png" in ICON_SUFFIXES and ".svg" in ICON_SUFFIXES


def test_icon_path_is_inside_plugin_dir(tmp_path):
    manifest = make_manifest(tmp_path, icon="assets/icon.png")
    (tmp_path / "assets").mkdir()
    write_png(tmp_path / "assets", "icon.png")

    assert manifest.icon_path == tmp_path / "assets" / "icon.png"


def test_missing_icon_file_reports_none(tmp_path):
    manifest = make_manifest(tmp_path, icon="icon.png")

    assert manifest.icon == "icon.png"
    assert manifest.icon_path is None, "写是写了，但文件不在就得当没有"


# 图标本体
def test_custom_icon_is_used_when_present(qapp, tmp_path):
    write_png(tmp_path, "icon.png", color=(0, 0, 255))
    manifest = make_manifest(tmp_path, icon="icon.png")

    pixmap = plugin_pixmap(manifest, 24)

    assert not pixmap.isNull()
    center = pixmap.toImage().pixelColor(pixmap.width() // 2, pixmap.height() // 2)
    assert (center.red(), center.green(), center.blue()) == (0, 0, 255), "用的应该是自定义图"


def test_icon_falls_back_to_badge_when_file_missing(qapp, tmp_path):
    manifest = make_manifest(tmp_path, icon="icon.png")

    pixmap = plugin_pixmap(manifest, 24)

    assert not pixmap.isNull(), "文件不在也要给一枚徽章，不能是空图标"
    assert not plugin_icon(manifest, 24).isNull()


def test_badge_is_painted_not_blank(qapp):
    pixmap = badge_pixmap("养成系统", "cultivation_system", 32)

    assert pixmap is not None and pixmap.size().width() == 32
    image = pixmap.toImage()
    painted = sum(
        1
        for x in range(0, image.width(), 4)
        for y in range(0, image.height(), 4)
        if image.pixelColor(x, y).alpha() > 0
    )
    assert painted > 8, "徽章上要有实际画出来的像素"


def test_badge_color_is_stable_and_varied():
    assert badge_color("alpha") == badge_color("alpha"), "同一个插件每次都要同一个色"
    assert badge_color("alpha") != badge_color("beta") or len(BADGE_COLORS) == 1
    assert badge_color("").isValid()


@pytest.mark.parametrize("name,plugin_id,expected", [
    ("养成系统", "cultivation_system", "养"),
    ("桌宠扭蛋机", "lucky_pet", "桌"),
    ("Hello Plugin", "hello", "H"),
    ("2fast", "two", "2"),
    ("", "plain_id", "P"),
])
def test_initials_picks_a_visible_glyph(name, plugin_id, expected):
    assert initials(name, plugin_id) == expected


def test_badge_pixmap_cache_reuses_same_object(qapp):
    first = badge_pixmap("演示插件", "demo", 32)
    second = badge_pixmap("演示插件", "demo", 32)

    assert first is second, "徽章要缓存，右键菜单每次弹出都重画太浪费"


def test_custom_icon_cache_notices_a_replaced_file(qapp, tmp_path):
    """插件作者换了图，不重启也该看到新图（缓存键带修改时间）。"""
    write_png(tmp_path, "icon.png", color=(255, 0, 0))
    manifest = make_manifest(tmp_path, icon="icon.png")

    def center_color():
        pixmap = plugin_pixmap(manifest, 16)
        return pixmap.toImage().pixelColor(8, 8).getRgb()[:3]

    assert center_color() == (255, 0, 0)

    import time

    time.sleep(0.01)
    write_png(tmp_path, "icon.png", color=(0, 255, 0))

    assert center_color() == (0, 255, 0), "换了图就该用新图"


def test_plugin_icon_accepts_a_bare_manifest_like_object(qapp):
    """SDK/主题拿到的是 dataclass，不一定是完整清单；缺属性也不能炸。"""
    manifest = PluginManifest(id="bare", name="极简", path=None)

    assert not plugin_icon(manifest, 24).isNull()


def test_icon_without_gui_returns_empty_instead_of_crashing(tmp_path, monkeypatch):
    """没有 QGuiApplication 时 Qt 构造 QPixmap 会直接终止进程——必须提前返回。"""
    from stlibs.plugins import icons

    monkeypatch.setattr(icons, "has_gui", lambda: False)
    manifest = make_manifest(tmp_path, icon="icon.png")

    assert icons.plugin_pixmap(manifest, 24) is None
    assert icons.plugin_icon(manifest, 24).isNull()
    assert icons.badge_pixmap("演示插件", "demo", 24) is None
