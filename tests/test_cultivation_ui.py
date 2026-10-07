"""养成面板（离屏 Qt）：状态、商店、背包、按钮回调与版面顺序。

数值逻辑在 test_cultivation.py、hook 接线在 test_cultivation_hooks.py，
这里只确认"数据有没有画到控件上、点按钮有没有转发出去、版面是不是按要求排的"。
"""

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
    window.resize(620, 560)
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
    assert abs(panel.shop_panel.width() - panel.bag_panel.width()) <= 4, "左右两栏宽度应该差不多"


def test_bag_shows_counts_and_shop_shows_prices(panel):
    bag = [item.text() for item in bag_widgets(panel)]
    assert "可乐 ×2" in bag
    assert "汉堡 ×1" in bag
    assert not any("剩骨头" in item for item in bag)

    shop = [item.text() for item in shop_widgets(panel)]
    assert len(shop) == len(FOODS)
    assert any(item.startswith("汉堡") and "80 金币" in item for item in shop)


def test_bag_items_flow_horizontally(panel):
    """背包是横布局：同一行的两个格子 y 相同、x 递增。"""
    grid = panel.bag_holder.grid
    positions = [grid.getItemPosition(index)[:2] for index in range(grid.count())]

    assert positions[0] == (0, 0)
    assert positions[1] == (0, 1), "背包第二格应该在同一行的右侧"


def test_food_buttons_have_icons(panel):
    for item in [*bag_widgets(panel), *shop_widgets(panel)]:
        if isinstance(item, QtWidgets.QPushButton):
            assert not item.icon().isNull(), f"{item.text()!r} 应该有食物图标"


def test_bag_button_forwards_eat(panel, actions):
    for item in bag_widgets(panel):
        if item.text().startswith("汉堡"):
            item.click()
            break

    assert ("eat", "汉堡") in actions


def test_shop_button_forwards_buy(panel, actions):
    for item in shop_widgets(panel):
        if item.text().startswith("剩骨头"):
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
