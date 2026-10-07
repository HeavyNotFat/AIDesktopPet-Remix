"""手动验证：桌宠右键菜单的插件条目（一层平铺）。

自动化用例在 ``tests/test_plugin_menu.py``；这个脚本是真窗口手测用的——
它会真弹一个菜单，方便肉眼确认插件条目是一条一条平铺、左边带各自插件图标、
名字是「插件名 · 菜单名」，以及点下去能真的触发插件。

    .venv\\Scripts\\python.exe tools\\manual\\verify_plugin_menu.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import stlibs  # noqa: E402
from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QFrame  # noqa: E402

app = QApplication([])

from stlibs.graphics import menu as menu_module  # noqa: E402
from stlibs.themes import hacker  # noqa: E402

stlibs.SharingData.theme = hacker
hacker.IconList.init()

FIRED = []
FAILURES = []

pet = QFrame()
pet.setStyleSheet("QFrame { background: #202225; border: 2px solid #00FF00; }")
pet.resize(200, 200)
pet.show()

MENU_X, MENU_Y = 560, 380


class FakeItem:
    def __init__(self, label, action):
        self.label = label
        self.action = action


class FakeGroup:
    def __init__(self, title, items):
        self.title = title
        self.icon = hacker.IconList.SETTING
        self.items = [FakeItem(label, action) for label, action in items]

    def __len__(self):
        return len(self.items)


class FakeManager:
    """假装装了三个插件：菜单应该平铺成 5 条，不再分组。"""

    def __init__(self):
        self.groups = [
            FakeGroup("养成系统", [("打开面板", "cultivation:panel"), ("查看状态", "cultivation:state")]),
            FakeGroup("桌宠扭蛋机", [("扭一次", "gacha:roll")]),
            FakeGroup("唯一插件", [("唯一一条", "solo:one")]),
        ]

    def menu_groups(self):
        return list(self.groups)


def build_menu():
    menu = hacker.HackerMenu(pet)
    menu.addAction(hacker.Action("设置", pet, hacker.IconList.SETTING))
    menu.addSeparator()
    groups = menu_module.add_plugin_menu(menu, manager=FakeManager())
    menu.addSeparator()
    menu.addAction(hacker.Action("关闭", pet, hacker.IconList.SHUTDOWN))
    return menu, groups


def settle(times=5):
    for _ in range(times):
        app.processEvents()


def check(condition, message):
    print(f"  {'OK  ' if condition else 'FAIL'} {message}")
    if not condition:
        FAILURES.append(message)


class _Click:
    def __init__(self, button):
        self._button = button

    def button(self):
        return self._button


def main():
    # 先拦截插件动作，免得真去跑插件
    original = menu_module.trigger_plugin_action
    menu_module.trigger_plugin_action = lambda action: FIRED.append(action)

    try:
        menu, groups = build_menu()
        menu.exec(QPoint(MENU_X, MENU_Y))
        settle()

        labels = [entry["text"] for entry in menu._action_items]
        print("\n[1] 一层平铺：插件条目全部排在同一层，没有子菜单")
        print("    条目：", labels)
        check(len([label for label in labels if " · " in label]) == 4, "4 条插件菜单项都平铺出来了")
        check(not hasattr(menu, "addMenu"), "主题菜单已经没有 addMenu（子菜单那套删掉了）")
        check(menu.width() > 0 and menu.height() > 0, f"菜单有尺寸：{menu.width()}x{menu.height()}")

        print("\n[2] 每条带自己插件的图标")
        plugin_rows = [entry for entry in menu._action_items if " · " in entry["text"]]
        check(all(entry["pixmap"] is not None for entry in plugin_rows), "每条都有图标")

        print("\n[3] 点一条插件条目：触发插件动作并把菜单收起来")
        target = next(entry for entry in plugin_rows if entry["text"] == "桌宠扭蛋机 · 扭一次")
        target["label"].mousePressEvent(_Click(Qt.MouseButton.LeftButton))
        settle(8)
        check(FIRED == ["gacha:roll"], f"触发了正确的动作（{FIRED}）")
        check(not menu.isVisible(), "菜单收起")
    finally:
        menu_module.trigger_plugin_action = original

    print(f"\n结论：{'全部通过' if not FAILURES else '失败 ' + str(FAILURES)}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
