import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import stlibs

MARK = "【插件生效】"


def make_temp_plugins(root: str) -> str:
    """一个 Python 插件，要求模型在回答里带暗号。"""
    directory = os.path.join(root, "probe_prompt")
    os.makedirs(directory, exist_ok=True)
    with open(os.path.join(directory, "plugin.json"), "w", encoding="utf-8") as handle:
        json.dump({
            "id": "probe_prompt",
            "name": "联调用提示词插件",
            "language": "python",
            "entry": "main.py",
            "hooks": ["on_system_prompt"],
        }, handle, ensure_ascii=False)
    with open(os.path.join(directory, "main.py"), "w", encoding="utf-8") as handle:
        handle.write(
            "def on_system_prompt(api):\n"
            f"    return '无论用户问什么，回答开头都必须原样写上 {MARK} 这四个字符。'\n"
        )
    return root


def send_through_chat(model: str, question: str, timeout: float = 240.0) -> str:
    """离屏跑一遍真实聊天页，返回最后一个气泡的文本。"""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])

    from stlibs.themes import hacker

    stlibs.SharingData.theme = hacker
    hacker.cache_llm_class.clear()

    page = hacker.ModelChat("联调", model, True)
    page.chat.input_edit.setPlainText(question)
    page.chat._send_message()

    deadline = time.time() + timeout
    while not page.chat.send_button.isEnabled() and time.time() < deadline:
        app.processEvents()
        time.sleep(0.05)

    app.processEvents()
    return page.chat.bubbles[-1].text()


def main():
    model = sys.argv[1] if len(sys.argv) > 1 else "glm4:latest"

    stlibs.Config.mcp["enable"] = False
    stlibs.Config.rag["enable"] = False
    stlibs.Config.memory["longterm"] = False

    manager = stlibs.plugin_manager()
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])

    print(f"== 1) 发现与加载（目录 {manager.directory}）==")
    loaded = manager.load_all()
    for info in loaded:
        state = "已加载" if info.loaded else f"失败：{info.error[:60]}"
        print(f"   {info.id:20} {info.manifest.language:10} {state} ({info.runtime})")
    for problem in manager.problems:
        print(f"   [问题] {problem['name']}: {problem['error']}")

    print("   菜单项：", [(item.label, item.action) for item in manager.menu_items()])
    print("   命令：", list(manager.commands()))
    print("   系统提示词：", manager.system_prompts())

    print("\n== 2) 回复被插件加工（真实聊天页）==")
    answer = send_through_chat(model, "用一句话说明什么是插件")
    print("   气泡内容：", answer[:120].replace("\n", " / "))
    if any(info.id == "hello_python" and info.loaded for info in loaded):
        assert "（来自 Python 插件）" in answer, "Python 插件的 on_chat_reply 没生效"
    else:
        print("   （没装示例插件 hello_python，跳过这一条断言）")

    print("\n== 3) 命令与菜单动作 ==")
    commands = manager.commands()
    if "统计" in commands:
        handled, text = manager.run_command("/统计")
        print("   /统计 ->", handled, text[:80])
        assert handled and text, "/统计 没被 Python 插件处理"
    else:
        print("   （示例插件不在，跳过 /统计）")

    if any(item.action == "hello_javascript:count" for item in manager.menu_items()):
        result = manager.trigger_menu("hello_javascript:count")
        print("   JS 菜单 ->", result[:80])
        assert result, "JS 菜单动作没返回内容"
    else:
        print("   （示例插件不在，跳过 JS 菜单）")

    print("\n== 4) 系统提示词真的进了模型 ==")
    with tempfile.TemporaryDirectory(dir=os.path.abspath(".tmp")) as workspace:
        directory = make_temp_plugins(os.path.join(workspace, "plugins"))
        stlibs.Config.plugins["directory"] = directory
        probe_manager = stlibs.plugin_manager()
        probe_manager.load_all()
        print("   临时插件提示词：", probe_manager.system_prompts())
        assert probe_manager.system_prompts(), "临时插件没提供提示词"

        with_mark = send_through_chat(model, "用一句话介绍你自己")
        print("   回答：", with_mark[:100].replace("\n", " "))
        assert MARK in with_mark, f"系统提示词没进模型（回答里没有 {MARK}）"

        # 换回仓库目录，并把插件重新装回来
        stlibs.Config.plugins["directory"] = manager.directory
        stlibs.plugin_manager().reload()

    print("\n插件系统验证通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
