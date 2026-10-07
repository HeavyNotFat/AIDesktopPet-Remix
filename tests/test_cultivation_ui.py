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
    window.resize(560, 580)
    window.show()
    window.refresh()
    for _ in range(3):
        qapp.processEvents()
    yield window
    window.hide()


def test_header_shows_coin_and_status(panel):
    assert panel.coin_label.text() == "金币：320"
    assert "Lv.4" in panel.status_label.text()
    assert "饥饿 74/200" in panel.status_label.text()


def test_progress_bars_match_state(panel):
    assert panel.level_bar.value() == 62
    assert panel.level_bar.maximum() == 780
    assert panel.level_bar.format() == "Lv.4  62/780"

    assert panel.favor_bar.value() == 40
    assert "好感 3" in panel.favor_bar.format()

    assert panel.hungry_bar.value() == 74
    assert panel.hungry_bar.maximum() == 200


def test_bag_shows_counts_and_shop_shows_prices(panel):
    labels = [panel.bag_grid.itemAt(i).widget().text() for i in range(panel.bag_grid.count())]
    assert "可乐 x2" in labels
    assert "汉堡 x1" in labels

    shop = [panel.shop_grid.itemAt(i).widget().text() for i in range(panel.shop_grid.count())]
    assert len(shop) == len(FOODS)
    assert any("汉堡（80 金币）" == item for item in shop)


def test_bag_button_forwards_eat(panel, actions):
    for index in range(panel.bag_grid.count()):
        button = panel.bag_grid.itemAt(index).widget()
        if button.text().startswith("汉堡"):
            button.click()
            break

    assert ("eat", "汉堡") in actions


def test_shop_button_forwards_buy(panel, actions):
    for index in range(panel.shop_grid.count()):
        button = panel.shop_grid.itemAt(index).widget()
        if button.text().startswith("剩骨头"):
            button.click()
            break

    assert ("buy", "剩骨头") in actions


def test_action_buttons_forward(panel, actions):
    # 三个动作按钮直接挂在窗口上（背包/商店的按钮挂在各自的容器里）
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

    labels = [window.bag_grid.itemAt(i).widget().text() for i in range(window.bag_grid.count())]
    assert any("背包是空的" in item for item in labels)
    window.hide()


def test_refresh_follows_state_changes(panel):
    panel.state.state["coin"] = 999
    panel.state.level["current"] = 100

    panel.refresh()

    assert panel.coin_label.text() == "金币：999"
    assert panel.level_bar.value() == 100


def test_show_panel_refreshes_and_shows(panel):
    panel.state.state["coin"] = 5
    panel.hide()

    panel.show_panel()

    assert panel.isVisible()
    assert panel.coin_label.text() == "金币：5"
    panel.hide()
