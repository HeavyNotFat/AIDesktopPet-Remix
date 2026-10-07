import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

OUT_DIR = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".tmp/ui-shots")
os.makedirs(OUT_DIR, exist_ok=True)

import stlibs

# 别碰仓库里的 configure.json
SAMPLE = {
    "models": {
        "DeepseekV4.1Flash": {"name": "deepseek-flash", "apikey": "sk-sample",
                              "baseurl": "https://api.deepseek.com"},
        "本地网关": {"name": "qwen", "apikey": "not-needed", "baseurl": "http://127.0.0.1:8000/v1"},
    },
    "memory": {"shortterm": True, "longterm": True},
    "rag": {"enable": False},
    "mcp": {"enable": False, "mcp": []},
    "coop": {"enable": True, "mode": "review", "rounds": 2,
             "agents": [{"model": "glm4:latest", "name": "评审员", "prompt": ""}]},
    "name": "探针", "model_live2d": "", "static_model": "",
    "opacity": 1, "size": 100, "rotate": 0, "theme": "hacker",
}
stlibs.CONFIG_PATH = os.path.join(OUT_DIR, "configure.json")
with open(stlibs.CONFIG_PATH, "w", encoding="utf-8") as handle:
    json.dump(SAMPLE, handle, ensure_ascii=False, indent=3)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QFrame

app = QApplication([])

from stlibs.themes import hacker

stlibs.SharingData.theme = hacker
stlibs.Config.models = {alias: dict(values) for alias, values in SAMPLE["models"].items()}
stlibs.Config.coop = dict(SAMPLE["coop"])

settings_module = sys.modules["stlibs.themes.hacker.llm"]
hacker.HackerNotify._stack.clear()


def shot(name, widget):
    # 先把挂起的布局/样式跑完，否则刚 addWidget 的控件还没尺寸，截出来是空的
    for _ in range(3):
        app.processEvents()
    widget.grab().save(os.path.join(OUT_DIR, name))
    print(f"  {name}  {widget.width()}x{widget.height()}")


def shoot_cultivation():
    """养成系统插件的面板：给它一点存档，好让进度条/背包有内容。"""
    plugin_dir = os.path.abspath("plugins/cultivation_system")
    if plugin_dir not in sys.path:
        sys.path.insert(0, plugin_dir)

    from cultivation_model import PetState
    from cultivation_window import CultivationWindow

    state = PetState(storage={"state": {
        "coin": 320,
        "foods": ["可乐", "汉堡", "可乐", "剩骨头"],
        "level": {"level": 4, "current": 62, "next": 780},
        "favorability": {"favorability": 3, "current": 40, "next": 640},
        "hungry": {"hungry": 74, "current": 200, "next": 250},
    }})

    class Api:
        name = "养成系统"
        id = "cultivation_system"

    panel = CultivationWindow(Api(), state)
    panel.resize(720, 660)
    panel.show()
    panel.refresh()
    shot("cultivation-panel.png", panel)
    return panel


def shoot_menu():
    """右键菜单：条目必须一行铺满（宽度参差不齐 + 高亮只亮一半是回归信号）。"""
    menu = hacker.HackerMenu(None)
    for text, tip in (("打开养成面板", "看看桌宠的状态"),
                      ("示例：打个招呼", "很长的菜单项文字用来撑宽度"),
                      ("设置", "打开设置窗口"),
                      ("关闭", "退出程序")):
        action = hacker.Action(text, menu, hacker.IconList.SETTING)
        action.setToolTip(tip)
        menu.addAction(action)
        print(f"   菜单项 {text!r} -> 宽 {menu._action_items[-1]['label'].width()}")

    menu.addSeparator()
    menu.exec(QPoint(20, 20))
    shot("menu.png", menu)
    widths = {item['label'].width() for item in menu._action_items}
    assert len(widths) == 1, f"菜单项宽度不一致：{widths}"
    menu.close()
    return menu


def shoot_plugin_menu():
    """插件右键菜单：每个插件一层子菜单（标题带图标），悬浮才展开。

    截图是"父菜单 + 已展开的子菜单"拼在一起的预览——悬浮展开后的真实样子，
    单独 grab 父菜单是看不到子菜单的（子菜单是独立窗口）。
    """
    from stlibs.graphics import menu as menu_module
    from stlibs.plugins.manager import core as plugin_core

    plugin_core.manager.directory = os.path.abspath("plugins")
    plugin_core.manager.load_all()

    menu = hacker.HackerMenu(None)
    for text in ("设置", "聊天"):
        menu.addAction(hacker.Action(text, menu, hacker.IconList.SETTING))
    groups = menu_module.add_plugin_menu(menu)
    menu.addAction(hacker.Action("关闭", menu, hacker.IconList.SHUTDOWN))
    menu.exec(QPoint(20, 20))

    print("   插件菜单分组：", [(group.title, len(group), "有图" if group.icon is not None else "无图")
                                for group in groups])
    assert groups, "装了插件却没挂上插件菜单"
    assert len(menu.sub_menus()) == len(groups), "每个插件应该各有一层子菜单"

    # 悬浮第一组：展开它的子菜单
    entry = next(item for item in menu._action_items if item['submenu'] is not None)
    entry['label'].enterEvent(None)
    for _ in range(3):
        app.processEvents()
    submenu = entry['submenu']
    assert submenu.isVisible(), "悬浮后子菜单要展开"
    print(f"   悬浮 {entry['text']!r} -> 子菜单 {submenu.title_text!r} "
          f"{submenu.width()}x{submenu.height()}，条目 {[i['text'] for i in submenu._action_items]}")

    # 把两个窗口拼成一张预览图（子菜单贴在父菜单右边，和真实位置一致）
    preview = QPixmap(menu.width() + submenu.width() + 16, max(menu.height(), submenu.height()) + 16)
    preview.fill(QColor(30, 31, 34))
    painter = QPainter(preview)
    painter.drawPixmap(0, 8, menu.grab())
    painter.drawPixmap(menu.width() + 16, max(0, (menu.height() - submenu.height()) // 2 + 8), submenu.grab())
    painter.end()

    path = os.path.join(OUT_DIR, "menu-plugin-submenu.png")
    preview.save(path)
    print(f"   menu-plugin-submenu.png  {preview.width()}x{preview.height()}")

    menu.close()
    return menu


# 假窗口：模拟主题窗口的深色底，让提示条有地方贴
window = QFrame()
window.setStyleSheet("QFrame { background: #1e1f22; border: 1px solid #00FF00; }")
window.resize(760, 520)
window.show()
stlibs.SharingData.setting_window = window

print("提示条：")
hacker.HackerNotify("已添加 API 模型「DeepseekV4.1Flash」，聊天列表已刷新", "success")
shot("notify-single.png", window)
hacker.HackerNotify("别名「DeepseekV4.1Flash」已经存在，换个名字或先删除旧配置", "error")
hacker.HackerNotify("协作配置已保存，但还没有配置任何模型", "warning")
shot("notify-stack.png", window)
for note in list(hacker.HackerNotify._stack):
    note.hide()
hacker.HackerNotify._stack.clear()

print("设置页：")
page = settings_module.BasicWidgetScroll(None)
page.resize(660, 500)
page.show()
shot("basic-page.png", page)
print(f"  删除行 -> 下拉 {page.existing.width()}x{page.existing.height()}"
      f" 按钮 {page.remove_button.width()}x{page.remove_button.height()}")

coop = settings_module.Cooperation(None)
coop.resize(660, 470)
coop.show()
shot("coop-page.png", coop)
print(f"  协作表 -> {coop.agent_table.rowCount()} 行 {coop.agent_table.columnCount()} 列")

skills = settings_module.Skills(None)
skills.resize(660, 420)
skills.show()
shot("skills-page.png", skills)
print(f"  技能表 -> {skills.skill_table.rowCount()} 行")

# 记忆页：故意塞 30 个模型，确认不会堆出 30 个页签
settings_module.get_model_lists = lambda: [f"model-{index:02d}:latest" for index in range(30)]
memory = settings_module.Memory(None)
memory.resize(660, 460)
memory.show()
shot("memory-page.png", memory)
print(f"  记忆页 -> 下拉 {memory.model_selector.count()} 个模型，"
      f"当前 {memory.model_selector.currentText()!r}")

plugins = hacker.plugins.PluginsPage(None)
plugins.resize(660, 500)
plugins.show()
plugins.refresh()
shot("plugins-page.png", plugins)
print(f"  插件表 -> {plugins.card.table.rowCount()} 行")

print("右键菜单：")
shoot_menu()
print("插件右键菜单：")
shoot_plugin_menu()

cultivation = shoot_cultivation()
print(f"  养成面板 -> 商店 {cultivation.shop_holder.grid.count()} 格 / 背包 {cultivation.bag_holder.grid.count()} 格")

print("聊天窗：")
chat = hacker.HackerChatWidget()
chat.resize(620, 620)
chat.show()
chat.add_user_msg("帮我把这句话翻译一下", skill={"name": "翻译"})
reply = chat.add_assistant_msg("好的，请把要翻译的内容发给我。")
reply.attach_audio("ZmFrZQ==")

from stlibs.ai import attachment as attachment_api

# 附件：一张真图片 + 一个文本文档
from PIL import Image as PILImage

picture = PILImage.new("RGB", (200, 120), (40, 40, 200))
buffer = io.BytesIO()
picture.save(buffer, format="PNG")
chat.add_user_msg("这两张一起看", attachments=[
    attachment_api.from_bytes(buffer.getvalue(), "示意图.png", "image/png"),
    attachment_api.from_bytes("这是文档正文".encode("utf-8"), "说明.md"),
])
chat.add_user_msg("第二句也一起")
chat.set_skill({"name": "翻译", "description": "翻译成中文", "prompt": "只输出译文"})
shot("chat-window.png", chat)
print(f"  复制按钮 {reply.copy_button.width()}x{reply.copy_button.height()}"
      f" 播放按钮 {reply.play_button.width()}x{reply.play_button.height()}"
      f" 气泡高 {reply.height()}")
print(f"  技能按钮 {chat.skill_button.width()}x{chat.skill_button.height()}"
      f" 附件按钮 {chat.attach_button.width()}x{chat.attach_button.height()}")
print(f"  带附件气泡的图片数 {len(chat.bubbles[-2].image_labels)}")

chat.attach_paths([os.path.join(OUT_DIR, "configure.json")])
shot("chat-attach-chips.png", chat)
print(f"  待发送附件 {[item['name'] for item in chat.attachments]}")

print(f"\n出图目录：{OUT_DIR}")
