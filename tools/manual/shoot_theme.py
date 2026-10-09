
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

THEME = (sys.argv[1] if len(sys.argv) > 1 else "breeze").strip() or "breeze"
OUT_DIR = os.path.abspath(sys.argv[2] if len(sys.argv) > 2 else f".tmp/theme-{THEME}")
os.makedirs(OUT_DIR, exist_ok=True)

import stlibs  # noqa: E402

# 别碰仓库里的 configure.json
SAMPLE = {
    "models": {
        "DeepseekV4.1Flash": {"name": "deepseek-flash", "apikey": "sk-sample",
                              "baseurl": "https://api.deepseek.com"},
    },
    "memory": {"shortterm": True, "longterm": True},
    "rag": {"enable": False},
    "mcp": {"enable": False, "mcp": []},
    "coop": {"enable": True, "mode": "review", "rounds": 2,
             "agents": [{"model": "qwen", "name": "评审员", "prompt": ""}]},
    "skills": [{"name": "翻译", "description": "翻译成中文", "prompt": "只输出译文"},
               {"name": "总结", "description": "提炼要点", "prompt": "三条要点"}],
    "name": "小轻", "model_live2d": "", "static_model": "",
    "opacity": 1, "size": 100, "rotate": 0, "theme": THEME,
}
stlibs.CONFIG_PATH = os.path.join(OUT_DIR, "configure.json")
with open(stlibs.CONFIG_PATH, "w", encoding="utf-8") as handle:
    json.dump(SAMPLE, handle, ensure_ascii=False, indent=3)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication([])

stlibs.SharingData.theme = stlibs.load_theme(THEME)

# 先装上自带中文字体，否则离屏出的图里控件会画成方框
from stlibs.themes.breeze.theme import install_ui_font  # noqa: E402

print("字体族：", install_ui_font() or "（装不上，用系统默认）")

stlibs.Config.models = {alias: dict(values) for alias, values in SAMPLE["models"].items()}
stlibs.Config.coop = dict(SAMPLE["coop"])
stlibs.Config.skills = [dict(item) for item in SAMPLE["skills"]]
stlibs.Config.name = SAMPLE["name"]

theme = stlibs.SharingData.theme
theme.IconList.init()
print(f"主题：{getattr(theme, 'THEME_LABEL', '?')}({THEME})")


def shot(name, widget):
    # 先跑完挂起的布局/样式，否则刚 addWidget 的控件还没尺寸
    for _ in range(4):
        app.processEvents()
    widget.grab().save(os.path.join(OUT_DIR, name))
    print(f"  {name}  {widget.width()}x{widget.height()}")


def shoot_window():
    """主窗口：侧栏导航 + 一个真实设置页。"""
    window = theme.Window()
    try:
        page = theme.settings.SettingsPage(window)
    except Exception as exc:  # noqa: BLE001 - 出图脚本不该因为某个页面炸掉
        print(f"  [警告] 设置页建不出来：{type(exc).__name__}: {exc}")
        page = theme.Label("（设置页建不出来）")
    window.create_category("设置")
    window.addNavigation("设置", page, category="设置")
    window.addNavigation("常规", theme.Label("常规页占位"))
    window.addNavigation("聊天", theme.Label("聊天页占位"))
    window.setTitle(f"AI 桌宠 · 轻风 | 设置 | {getattr(theme, 'THEME_LABEL', THEME)}")
    window.resize(940, 640)
    window.show()
    shot("window-settings.png", window)

    # 每个设置页各出一张图，看卡片布局有没有问题
    for name, factory, file_name in (
        ("LLM 设置", lambda: theme.llm.LLMPage(window), "window-llm.png"),
        ("动画设置", lambda: theme.animation.AnimationPage(window), "window-animation.png"),
        ("常规设置", lambda: theme.general.GeneralPage(window), "window-general.png"),
        ("插件", lambda: theme.plugins.PluginsPage(window), "window-plugins.png"),
    ):
        try:
            built = factory()
        except Exception as exc:  # noqa: BLE001
            print(f"  [警告] {name} 页建不出来：{type(exc).__name__}: {exc}")
            continue
        window.addNavigation(name, built, category="设置")
        window._set_active(built)
        shot(file_name, window)
        window.removeNavigation(built)
        built.deleteLater()

    window.close()
    return window


def shoot_cultivation():
    """养成系统插件面板，配色应该跟着当前主题走。"""
    plugin_dir = os.path.abspath("plugins/cultivation_system")
    if plugin_dir not in sys.path:
        sys.path.insert(0, plugin_dir)

    try:
        from cultivation_model import PetState
        from cultivation_window import CultivationWindow
    except Exception as exc:  # noqa: BLE001
        print(f"  [警告] 养成面板建不出来：{type(exc).__name__}: {exc}")
        return None

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
    panel.close()
    return panel


def shoot_chat():
    chat = theme.ChatWidget()
    chat.resize(640, 620)
    chat.show()
    chat.add_user_msg("帮我把这句话翻成日语", skill={"name": "翻译"})
    reply = chat.add_assistant_msg("好的，把要翻译的内容发给我就行。")
    reply.attach_audio("ZmFrZQ==")

    from stlibs.ai import attachment as attachment_api
    from PIL import Image as PILImage

    picture = PILImage.new("RGB", (220, 130), (120, 180, 230))
    buffer = io.BytesIO()
    picture.save(buffer, format="PNG")
    chat.add_user_msg("这张图也看一下", attachments=[
        attachment_api.from_bytes(buffer.getvalue(), "示意图.png", "image/png"),
        attachment_api.from_bytes("这是文档正文".encode("utf-8"), "说明.md"),
    ])
    chat.set_skill({"name": "翻译", "description": "翻译成中文", "prompt": "只输出译文"})
    shot("chat.png", chat)
    return chat


def shoot_menu():
    from stlibs.graphics import menu as menu_module

    menu = theme.Menu(None)
    menu.addAction(theme.Action("设置", menu, theme.IconList.SETTING))
    menu.addSeparator()
    menu.addAction(theme.Action("聊天", menu, theme.IconList.CHAT))
    menu.addSeparator()
    groups = menu_module.add_plugin_menu(menu)
    menu.addSeparator()
    menu.addAction(theme.Action("关闭", menu, theme.IconList.SHUTDOWN))
    menu.exec(QPoint(20, 20))

    print(f"  插件菜单：{[group.title for group in groups]}")
    print(f"  菜单条目：{[entry['text'] for entry in menu._action_items]}")
    shot("menu.png", menu)
    menu.close()


def shoot_notify():
    from PySide6.QtWidgets import QFrame

    host = QFrame()
    host.setStyleSheet(f"QFrame {{ background: {getattr(theme, 'BG', '#F7FAFC')}; }}")
    host.resize(760, 460)
    host.show()
    stlibs.SharingData.setting_window = host
    for note in list(theme.Notify._stack):
        note.hide()
    theme.Notify._stack.clear()
    for _ in range(3):
        app.processEvents()

    notes = [
        theme.Notify("已保存这条配置，重启后依然是这个样子", "success", 60000),
        theme.Notify("这个模型没有配置 API Key，先去「LLM 设置」补上", "warning", 60000),
        theme.Notify("插件加载失败：清单里的 entry 找不到", "error", 60000),
    ]
    print(f"  提示条：{[(n.geometry().x(), n.geometry().y()) for n in notes]}")
    shot("notify.png", host)
    for note in notes:
        note.hide()
    theme.Notify._stack.clear()
    host.close()


print("主窗口：")
shoot_window()
print("聊天窗：")
chat = shoot_chat()
print("右键菜单：")
shoot_menu()
print("提示条：")
shoot_notify()
print("养成面板（插件跟主题）：")
shoot_cultivation()

print(f"\n出图目录：{OUT_DIR}")
