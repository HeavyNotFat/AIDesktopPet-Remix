import base64
import io
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import stlibs
from stlibs.ai import attachment, local

WEB_BASE = "http://127.0.0.1:52493"
SECRET = "7391-ABCD"
DOC_QUESTION = "附件里写的暗号是什么？只回答暗号本身，不要解释。"


def make_image(size=512) -> bytes:
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (size, size), (250, 250, 250))
    draw = ImageDraw.Draw(image)
    margin = size * 0.15
    draw.ellipse([margin, margin, size - margin, size - margin], fill=(20, 20, 200))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def ask(llm, question, items):
    return "".join(
        chunk for chunk in llm.chat(question, should_emit=False, attachments=items)
        if isinstance(chunk, str)
    ).strip()


def post(path, payload, timeout=180):
    request = urllib.request.Request(
        f"{WEB_BASE}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return {"status": exc.code, "detail": exc.read().decode("utf-8", "replace")[:120]}


def send_through_chat_widget(model: str, document: dict, timeout: float = 240.0) -> str:
    """离屏跑一遍真实聊天页：挂附件 -> _send_message -> 等线程结束 -> 读气泡。"""
    import time

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])

    from stlibs.themes import hacker

    stlibs.SharingData.theme = hacker
    hacker.cache_llm_class.clear()

    page = hacker.ModelChat("联调", model, True)
    page.chat.add_attachment(document)
    page.chat.input_edit.setPlainText(DOC_QUESTION)
    page.chat._send_message()

    deadline = time.time() + timeout
    while not page.chat.send_button.isEnabled() and time.time() < deadline:
        app.processEvents()
        time.sleep(0.05)

    app.processEvents()
    return page.chat.bubbles[-1].text()


def main():
    argv = [item for item in sys.argv[1:] if not item.startswith("--")]
    model = argv[0] if argv else "glm4:latest"
    with_web = "--web" in sys.argv

    stlibs.Config.mcp["enable"] = False
    stlibs.Config.rag["enable"] = False
    stlibs.Config.memory["longterm"] = False

    raw = make_image()
    image = attachment.from_bytes(raw, "蓝色圆.png", "image/png")
    document = attachment.from_bytes(f"本文件记录一个暗号：{SECRET}\n".encode("utf-8"), "暗号.txt")
    print(f"测试图：{image['name']} {attachment.human_size(image['size'])} kind={image['kind']}")
    print(f"测试文档：{document['name']} 正文={document['text']!r}")

    print(f"\n== 1) 图片的消息形状（{model}）==")
    message = attachment.ollama_message("看图", [image])
    print("  字段：", sorted(message))
    assert message.get("images"), "ollama 消息里没有 images 字段"
    assert base64.b64decode(message["images"][0]) == raw, "图片 base64 与原文件不一致"
    print("  images 条数：1，base64 与原文件一致 ✓")

    print("\n== 2) 文档正文进了上下文（桌面链路）==")
    answer = ask(local.LLM(model, coop=False), DOC_QUESTION, [document])
    print("  回答：", answer[:80])
    assert SECRET in answer, f"模型没读到附件正文：{answer[:80]}"

    print("\n== 2b) 桌面真实发送链路（附件 → 发送 → 气泡）==")
    widget_answer = send_through_chat_widget(model, document)
    print("  气泡里的回答：", widget_answer[:80])
    assert SECRET in widget_answer, f"附件没走通发送链路：{widget_answer[:80]}"

    if with_web:
        print(f"\n== 3) 网页链路（{WEB_BASE}）==")
        payload = {
            "model": model,
            "question": DOC_QUESTION,
            "session_id": "manual-attach",
            "attachments": [{
                "name": document["name"],
                "mime": "text/plain",
                "data": base64.b64encode(f"暗号：{SECRET}".encode("utf-8")).decode("ascii"),
            }],
        }
        web_answer = str(post("/api/chat", payload).get("answer", ""))
        print("  回答：", web_answer[:80])
        assert SECRET in web_answer, f"网页链路没把附件正文交给模型：{web_answer[:80]}"

        empty = post("/api/chat", {"model": model, "question": "   ", "attachments": []})
        print("  空问题（应被拒）：", empty.get("status"), empty.get("detail", "")[:60])
        assert empty.get("status") == 400, "空问题+无附件应该被拒"

    print("\n附件链路验证通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
