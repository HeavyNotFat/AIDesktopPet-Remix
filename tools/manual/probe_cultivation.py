import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import stlibs

PLUGIN_ID = "cultivation_system"


def main():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])

    manager = stlibs.plugin_manager()
    stlibs.Config.plugins["disabled"] = [plugin_id for plugin_id in stlibs.Config.plugins.get("disabled", [])
                                         if plugin_id != PLUGIN_ID]

    print("== 1) 加载插件 ==")
    manager.load_all()
    info = manager.infos.get(PLUGIN_ID)
    assert info is not None, "没发现养成系统插件"
    assert info.loaded, f"加载失败：{info.error}"
    print(f"   {info.id}  {info.runtime}  {info.manifest.name} v{info.manifest.version}")

    print("\n== 2) 它接进了哪些地方 ==")
    print("   菜单项：", [item.label for item in manager.menu_items() if item.action.startswith(PLUGIN_ID)])
    print("   命令：", [name for name in manager.commands() if name in ("养成", "状态", "喂食", "买")])
    print("   系统提示词：", manager.system_prompts() or "（当前心情不需要提示）")

    print("\n== 3) 模拟宿主行为 ==")
    manager.emit_event("pet_click", {"source": "probe"})
    app.processEvents()
    print("   /状态 ->", manager.run_command("/状态")[1].replace("\n", " | "))

    state = sys.modules["adp_plugin_cultivation_system"]._state
    state.state["coin"] = 300
    print("   /买 汉堡 ->", manager.run_command("/买 汉堡")[1])
    print("   /喂食 汉堡 ->", manager.run_command("/喂食 汉堡")[1].replace("\n", " | "))
    print("   AI 回复奖励 ->", manager.chat_text("这是一段回答。" * 20, "assistant") is not None and "已记账")

    print("\n== 4) 面板窗口（离屏）==")
    opened = manager.run_command("/养成")[1]
    print("   /养成 ->", opened)
    window = sys.modules["adp_plugin_cultivation_system"]._window
    assert window is not None, "面板没建出来"
    window.refresh()
    print(f"   标题：{window.windowTitle()}")
    print(f"   金币：{window.coin_label.text()}")
    print(f"   状态：{window.status_label.text()}")
    print(f"   等级条：{window.level_bar.format()} 值={window.level_bar.value()}/{window.level_bar.maximum()}")
    print(f"   好感条：{window.favor_bar.format()}")
    print(f"   饥饿条：{window.hungry_bar.format()}")
    print(f"   背包格子：{window.bag_grid.count()}  商店格子：{window.shop_grid.count()}")
    assert window.shop_grid.count() >= 8, "商店应该列出 foods.json 里的八种食物"

    print("\n== 5) 存盘与卸载 ==")
    saved = manager.infos[PLUGIN_ID]
    storage = manager._apis[PLUGIN_ID].storage_get("state")
    print("   存档：", {key: storage[key] for key in ("coin", "foods", "replies")})
    manager.unload(PLUGIN_ID)
    print("   卸载后 loaded =", saved.loaded)

    print("\n养成系统移植验证通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
