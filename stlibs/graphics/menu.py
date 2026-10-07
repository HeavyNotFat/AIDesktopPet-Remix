"""把插件注册的菜单项挂到桌宠右键菜单上（两个 shader 共用）。

规则：
* 一个插件一组，组标题 = 插件清单的 ``menu``（没写就是插件名），组标题左边是插件图标；
* 只有一组、且组里只有一条时直接平铺，少一层没必要的子菜单；
* 插件系统坏了（读不到菜单项）就当没有插件菜单，绝不能连右键菜单一起挂掉。

宿主侧只跟 ``PluginManager.menu_groups()`` 打交道，这里不碰任何插件代码。
"""

from __future__ import annotations

from .. import SharingData
from ..plugins import MenuGroup


def plugin_menu_groups(manager=None) -> list:
    """当前该挂的插件菜单分组（读不到就返回空列表）。"""
    try:
        if manager is None:
            from .. import plugin_manager

            manager = plugin_manager()
        return [group for group in manager.menu_groups() if len(group)]
    except Exception as exc:  # noqa: BLE001 - 插件坏了不能挡住菜单
        print(f"[plugin] 菜单项读取失败：{exc}")
        return []


def add_plugin_menu(context_menu, manager=None, action_factory=None) -> list:
    """把插件菜单挂到 ``context_menu`` 上，返回挂上去的分组（没有就返回空列表）。

    ``action_factory(text, icon)`` 由主题提供（各主题 Action 的构造签名不一样，
    桌宠这边的 shader 传的是 ``stlibs.SharingData.theme.Action``）。
    """
    groups = plugin_menu_groups(manager)
    if not groups:
        return []

    context_menu.addSeparator()

    if len(groups) == 1 and len(groups[0]) == 1:
        # 只有一个插件的一条菜单：平铺，别为了分组硬套一层子菜单
        group = groups[0]
        item = group.items[0]
        _add_item(context_menu, item.label, group, item.action, action_factory)
        return groups

    for group in groups:
        submenu = context_menu.addMenu(group.title, getattr(group, "icon", None))
        for item in group.items:
            _add_item(submenu, item.label, group, item.action, action_factory)

    return groups


def _add_item(menu, label, group: MenuGroup, action: str, action_factory=None):
    """挂一条会回调插件 on_command 的菜单项（带这一组插件的图标）。"""
    if action_factory is None:
        def action_factory(text, icon):
            return SharingData.theme.Action(text, None, icon)

    entry = action_factory(label, getattr(group, "icon", None))
    entry.setToolTip(f"{group.title} · {action}")
    entry.triggered.connect(lambda _checked=False, name=action: trigger_plugin_action(name))
    menu.addAction(entry)
    return entry


def trigger_plugin_action(action: str):
    """菜单项被点：交给插件系统；插件回了文本就弹一条提示。"""
    from .. import notify, plugin_manager

    try:
        manager = plugin_manager()
        result = manager.trigger_menu(action) or manager.trigger_menu(action.split(":")[-1])
    except Exception as exc:  # noqa: BLE001
        notify(f"插件菜单执行失败：{exc}", "error", 4000)
        return None

    if result:
        notify(str(result)[:120], "info", 3000)
    return result


__all__ = ["add_plugin_menu", "plugin_menu_groups", "trigger_plugin_action"]
