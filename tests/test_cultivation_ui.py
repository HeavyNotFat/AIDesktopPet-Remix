
import os
import sys
from pathlib import Path

import pytest

PLUGIN_DIR = Path(__file__).resolve().parents[1] / "plugins" / "cultivation_system"
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

pytestmark = pytest.mark.ui

QtWidgets = pytest.importorskip("PySide6.QtWidgets", reason="面板测试需要 PySide6")

from cultivation_model import PetState  # noqa: E402

FOODS = {
    "汉堡": {"price": 80, "hungry": 8, "favor": 10, "level": 0},
    "可乐": {"price": 50, "hungry": 5, "favor": 9, "level": 0},
    "剩骨头": {"price": 1, "hungry": 2, "favor": -5, "level": 0},
}

SAVED = {
    "coin": 320,
    "foods": ["可乐", "可乐", "汉堡"],
    "level": {"level": 4, "current": 62, "next": 780},
    "favorability": {"favorability": 3, "current": 40, "next": 640},
    "hungry": {"hungry": 74, "current": 200, "next": 250},
}


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


class FakeAPI:
    name = "养成系统"
    id = "cultivation_system"


@pytest.fixture
def actions():
    return []


@pytest.fixture
def panel(qapp, actions):
    from cultivation_window import CultivationWindow

    state = PetState(storage={"state": dict(SAVED)}, foods=dict(FOODS))
    window = CultivationWindow(FakeAPI(), state, on_action=lambda action, payload=None: actions.append((action, payload)))
    window.resize(700, 600)
    window.show()
    window.refresh()
    for _ in range(3):
        qapp.processEvents()
    yield window
    window.hide()


def bag_widgets(panel):
    grid = panel.bag_holder.grid
    return [grid.itemAt(index).widget() for index in range(grid.count())]


def shop_widgets(panel):
    grid = panel.shop_holder.grid
    return [grid.itemAt(index).widget() for index in range(grid.count())]


def test_header_shows_coin_and_status(panel):
    assert panel.coin_label.text() == "金币 320"
    status = panel.status_label.text()
    assert "Lv.4" in status
    assert "好感 3" in status
    assert "饥饿 74/200" in status
    assert "背包 3 件" in status
    assert "金币" not in status, "金币只在右上角显示一次"


def test_progress_bars_match_state(panel):
    assert panel.level_bar.value() == 62
    assert panel.level_bar.maximum() == 780
    assert panel.level_bar.format().startswith("Lv.4")
    assert "62/780" in panel.level_bar.format()

    assert panel.favor_bar.value() == 40
    assert "好感 3" in panel.favor_bar.format()

    assert panel.hungry_bar.value() == 74
    assert panel.hungry_bar.maximum() == 200


def test_status_on_top_shop_left_bag_right(panel):
    """版面要求：状态在最上面，商店在左、背包在右。"""
    status_y = panel.status_label.mapTo(panel, panel.status_label.rect().topLeft()).y()
    shop_x = panel.shop_panel.mapTo(panel, panel.shop_panel.rect().topLeft()).x()
    bag_x = panel.bag_panel.mapTo(panel, panel.bag_panel.rect().topLeft()).x()

    assert status_y < panel.shop_panel.mapTo(panel, panel.shop_panel.rect().topLeft()).y(), "状态要在上面"
    assert shop_x < bag_x, "商店在左、背包在右"
    assert panel.shop_panel.width() > panel.bag_panel.width(), "商店要更宽（格子更大）"


def test_bag_shows_counts_and_shop_shows_prices(panel):
    bag = [(item.name_label.text(), item.detail_label.text()) for item in bag_widgets(panel)]
    assert ("可乐", "×2") in bag
    assert ("汉堡", "×1") in bag
    assert not any(name == "剩骨头" for name, _detail in bag)

    shop = [(item.name_label.text(), item.detail_label.text()) for item in shop_widgets(panel)]
    assert len(shop) == len(FOODS)
    assert ("汉堡", "80 金币") in shop


def test_shop_tiles_are_image_over_name(panel):
    """商店格子：中间是图，下面才是名字与价格（要的上下布局）。"""
    tile = shop_widgets(panel)[0]
    image = tile.image_label

    assert image.pixmap() is not None and not image.pixmap().isNull()
    assert image.height() >= 60, "图片要给够大小"

    image_bottom = image.mapTo(tile, image.rect().bottomLeft()).y()
    name_top = tile.name_label.mapTo(tile, tile.name_label.rect().topLeft()).y()
    detail_top = tile.detail_label.mapTo(tile, tile.detail_label.rect().topLeft()).y()
    assert image_bottom <= name_top <= detail_top, "顺序必须是 图 → 名字 → 价格"


def test_bag_items_flow_horizontally(panel):
    """背包是横布局：同一行的两个格子 y 相同、x 递增。"""
    grid = panel.bag_holder.grid
    positions = [grid.getItemPosition(index)[:2] for index in range(grid.count())]

    assert positions[0] == (0, 0)
    assert positions[1] == (0, 1), "背包第二格应该在同一行的右侧"


def test_every_tile_has_food_image(panel):
    for item in [*bag_widgets(panel), *shop_widgets(panel)]:
        pixmap = item.image_label.pixmap()
        assert pixmap is not None and not pixmap.isNull(), f"{item.name!r} 应该有食物图"


def test_bag_tile_forwards_eat(panel, actions):
    for item in bag_widgets(panel):
        if item.name == "汉堡":
            item.click()
            break

    assert ("eat", "汉堡") in actions


def test_shop_tile_forwards_buy(panel, actions):
    for item in shop_widgets(panel):
        if item.name == "剩骨头":
            item.click()
            break

    assert ("buy", "剩骨头") in actions


def test_action_buttons_forward(panel, actions):
    buttons = [
        child for child in panel.children()
        if isinstance(child, QtWidgets.QPushButton) and child.parent() is panel
    ]
    assert [item.text() for item in buttons] == ["点一下赚金币", "刷新", "关闭"]

    for button in buttons:
        button.click()

    assert ("click", None) in actions
    assert ("refresh", None) in actions
    assert ("close", None) in actions


def test_empty_bag_shows_hint(qapp):
    from cultivation_window import CultivationWindow

    state = PetState(storage={"state": {"coin": 0, "foods": []}}, foods=dict(FOODS))
    window = CultivationWindow(FakeAPI(), state)
    window.show()
    window.refresh()
    for _ in range(3):
        qapp.processEvents()

    labels = [window.bag_holder.grid.itemAt(i).widget().text() for i in range(window.bag_holder.grid.count())]
    assert any("背包是空的" in item for item in labels)
    window.hide()


def test_refresh_follows_state_changes(panel):
    panel.state.state["coin"] = 999
    panel.state.level["current"] = 100

    panel.refresh()

    assert panel.coin_label.text() == "金币 999"
    assert panel.level_bar.value() == 100


def test_show_panel_refreshes_and_shows(panel):
    panel.state.state["coin"] = 5
    panel.hide()

    panel.show_panel()

    assert panel.isVisible()
    assert panel.coin_label.text() == "金币 5"
    panel.hide()


# -- 跟着主题走 -------------------------------------------------------------
def _panel_with_theme(qapp, theme_name):
    """在当前主题下建一个面板（配色应该取自这个主题）。"""
    import stlibs
    from cultivation_window import CultivationWindow

    previous = stlibs.SharingData.theme
    stlibs.SharingData.theme = stlibs.load_theme(theme_name)
    try:
        state = PetState(storage={"state": dict(SAVED)}, foods=dict(FOODS))
        window = CultivationWindow(FakeAPI(), state)
        window.show()
        window.refresh()
        for _ in range(3):
            qapp.processEvents()
        return window
    finally:
        stlibs.SharingData.theme = previous


def test_panel_follows_the_current_theme(qapp):
    """同一个面板在深色/浅色主题下的配色必须不一样（以前是写死的绿色）。"""
    dark = _panel_with_theme(qapp, "hacker")
    light = _panel_with_theme(qapp, "breeze")

    dark_style = dark.styleSheet() + dark.shop_panel.styleSheet() + dark.level_bar.styleSheet()
    light_style = light.styleSheet() + light.shop_panel.styleSheet() + light.level_bar.styleSheet()

    assert dark_style != light_style
    assert "#16181c" not in light_style, "浅色主题下不该还留着深色底"
    assert "#F7FAFC" not in dark_style, "深色主题下不该出现浅色底"

    for window in (dark, light):
        window.hide()


def test_panel_uses_theme_widgets(qapp):
    """控件本身也要是当前主题的（字体/内边距跟着变，不是自绘 QLabel）。"""
    window = _panel_with_theme(qapp, "breeze")
    try:
        assert type(window.title).__module__.startswith("stlibs.themes.breeze"), \
            f"标题应该是当前主题的 Label，实际 {type(window.title)}"
    finally:
        window.hide()


def test_theme_palette_declares_what_plugins_need():
    """插件只用语义名取色：PALETTE 得给全，不然面板会掉回默认深色。"""
    import stlibs
    from stlibs.graphics.palette import palette
    from stlibs.themes.base import ThemePalette

    for name in ("hacker", "breeze"):
        stlibs.SharingData.theme = stlibs.load_theme(name)
        colors = palette()
        assert isinstance(colors, ThemePalette)
        for key in ("bg", "surface", "surface_soft", "primary", "text", "border"):
            assert getattr(colors, key), f"{name} 的 PALETTE 少了 {key}"
        bright, soft = colors.tint("level")
        assert bright and soft
