from __future__ import annotations

from .. import SharingData

LABEL_SEPARATOR = " · "


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


def plugin_menu_items(manager=None) -> list:
    """平铺用的 ``(分组, 菜单项)`` 列表。"""
    return [(group, item) for group in plugin_menu_groups(manager) for item in group.items]


def add_plugin_menu(context_menu, manager=None, action_factory=None) -> list:
    """把插件菜单平铺到 ``context_menu`` 上，返回挂上去的分组。"""
    entries = plugin_menu_items(manager)
    if not entries:
        return []

    context_menu.addSeparator()
    for group, item in entries:
        _add_item(context_menu, group, item, action_factory)

    return plugin_menu_groups(manager)


def item_label(group, item) -> str:
    """平铺后的显示名：``插件名 · 菜单名``（菜单名已含插件名就不加前缀）。"""
    title = str(getattr(group, "title", "") or "").strip()
    label = str(getattr(item, "label", "") or "").strip()
    if not title:
        return label
    if not label:
        return title
    if _already_names_plugin(title, label):
        return label
    return f"{title}{LABEL_SEPARATOR}{label}"


def _already_names_plugin(title: str, label: str) -> bool:
    """菜单名里是不是已经能看出是哪个插件了。"""
    if not title or not label:
        return True
    if label.startswith(title) or title in label:
        return True
    if label in title:                                   # 标题是菜单名的超集
        return True
    for prefix in _TITLE_PREFIX_NOISE:
        if title.startswith(prefix) and label.startswith(title[len(prefix):]):
            return True
    return False


# 插件标题里常见、但对不上菜单名的前缀
_TITLE_PREFIX_NOISE = ("桌宠", "宠物", "我的")


def _add_item(menu, group, item, action_factory=None):
    """平铺一条会回调插件 on_command 的菜单项（带这个插件的图标）。"""
    if action_factory is None:
        def action_factory(text, icon):
            return SharingData.theme.Action(text, None, icon)

    entry = action_factory(item_label(group, item), getattr(group, "icon", None))
    entry.setToolTip(f"{getattr(group, 'title', '')} · {item.action}")
    entry.triggered.connect(lambda _checked=False, name=item.action: trigger_plugin_action(name))
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


__all__ = [
    "add_plugin_menu",
    "item_label",
    "plugin_menu_groups",
    "plugin_menu_items",
    "trigger_plugin_action",
]
