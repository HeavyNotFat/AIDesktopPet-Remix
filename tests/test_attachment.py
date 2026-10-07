import base64
import json

import pytest

from stlibs.ai import attachment

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


# 分类与限额
def test_image_is_detected_by_mime_and_suffix():
    assert attachment.kind_of("a.png") == "image"
    assert attachment.kind_of("a.JPG") == "image"
    assert attachment.kind_of("没后缀", "image/webp") == "image"
    assert attachment.kind_of("a.md") == "file"
    assert attachment.kind_of("") == "file"


def test_image_keeps_base64_and_marks_note():
    item = attachment.from_bytes(PNG, "cat.png")

    assert item["kind"] == "image"
    assert item["name"] == "cat.png"
    assert base64.b64decode(item["data"]) == PNG
    assert item["size"] == len(PNG)
    assert item["note"] == "图片"


def test_document_text_is_extracted():
    item = attachment.from_bytes("第一行\n第二行".encode("utf-8"), "说明.md")

    assert item["kind"] == "file"
    assert item["text"] == "第一行\n第二行"
    assert item["note"] == "已读入正文"
    assert item["truncated"] is False


def test_gbk_document_is_readable():
    item = attachment.from_bytes("中文内容".encode("gb18030"), "notes.txt")

    assert "中文内容" in item["text"]


def test_long_document_is_truncated():
    item = attachment.from_bytes(("行\n" * 6000).encode("utf-8"), "big.txt")

    assert len(item["text"]) == attachment.MAX_DOC_CHARS
    assert item["truncated"] is True


def test_binary_document_degrades_to_name_only():
    item = attachment.from_bytes(b"\x00\x01\x02\xff\xfe", "blob.bin")

    assert item["text"] == ""
    assert "无法读取正文" in item["note"]


def test_oversized_attachment_is_refused_with_note():
    big = b"x" * (attachment.MAX_FILE_BYTES + 1)
    item = attachment.from_bytes(big, "big.txt")

    assert item["text"] == ""
    assert "超过" in item["note"]


def test_empty_file_is_marked():
    item = attachment.from_bytes(b"", "empty.txt")

    assert item["note"] == "空文件"


def test_docx_text_is_extracted_when_library_present(tmp_path):
    docx = pytest.importorskip("docx", reason="需要 python-docx")

    document = docx.Document()
    document.add_paragraph("段落一")
    document.add_paragraph("段落二")
    table = document.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "A"
    table.rows[0].cells[1].text = "B"
    path = tmp_path / "报告.docx"
    document.save(str(path))

    item = attachment.from_path(str(path))

    assert "段落一" in item["text"]
    assert "段落二" in item["text"]
    assert "A | B" in item["text"]


def test_from_path_reads_real_file(tmp_path):
    path = tmp_path / "note.txt"
    path.write_text("你好", encoding="utf-8")

    item = attachment.from_path(str(path))

    assert item["name"] == "note.txt"
    assert item["text"] == "你好"


def test_from_base64_accepts_data_url():
    payload = "data:image/png;base64," + _b64(PNG)
    item = attachment.from_base64(payload, "paste.png", "image/png")

    assert item["kind"] == "image"
    assert base64.b64decode(item["data"]) == PNG


def test_from_base64_with_broken_payload():
    item = attachment.from_base64("!!!不是 base64!!!", "bad.png", "image/png")

    assert item["size"] == 0
    assert item["note"] == "空文件"


# 归一化
def test_normalize_accepts_paths_dicts_and_web_payloads(tmp_path):
    path = tmp_path / "a.txt"
    path.write_text("来自路径", encoding="utf-8")

    items = attachment.normalize([
        str(path),
        {"name": "b.txt", "data": _b64("来自网页".encode("utf-8"))},
        {"kind": "image", "name": "c.png", "size": 10, "text": ""},
        "不存在的文件.txt",
        None,
    ])

    assert [item["name"] for item in items] == ["a.txt", "b.txt", "c.png"]
    assert items[0]["text"] == "来自路径"
    assert items[1]["text"] == "来自网页"


def test_normalize_deduplicates_same_name_and_size():
    payload = {"name": "same.txt", "data": _b64("内容".encode("utf-8"))}

    assert len(attachment.normalize([payload, dict(payload)])) == 1


def test_normalize_caps_count():
    items = [{"name": f"{index}.txt", "data": _b64(str(index).encode())} for index in range(12)]

    assert len(attachment.normalize(items)) == attachment.MAX_ATTACHMENTS


# 给模型的消息形状
def test_document_context_is_prepended():
    doc = attachment.from_bytes("正文在此".encode("utf-8"), "说明.md")

    text = attachment.with_document_context("看看这个", [doc])

    assert text.startswith("【附件：说明.md")
    assert "正文在此" in text
    assert text.endswith("看看这个")


def test_document_context_skipped_for_images_only():
    image = attachment.from_bytes(PNG, "cat.png")

    assert attachment.with_document_context("图里是什么", [image]) == "图里是什么"


def test_ollama_message_uses_images_field():
    message = attachment.ollama_message("看图", [attachment.from_bytes(PNG, "cat.png")])

    assert message["role"] == "user"
    assert message["content"] == "看图"
    assert len(message["images"]) == 1
    assert base64.b64decode(message["images"][0]) == PNG


def test_ollama_message_without_image_has_no_images_key():
    message = attachment.ollama_message("纯文字", [])

    assert "images" not in message
    assert message["content"] == "纯文字"


def test_openai_message_uses_content_array():
    message = attachment.openai_message("看图", [attachment.from_bytes(PNG, "cat.png")])

    kinds = [part["type"] for part in message["content"]]
    assert kinds == ["text", "image_url"]
    assert message["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_openai_message_stays_plain_without_image():
    message = attachment.openai_message("只有文字", [attachment.from_bytes(b"hi", "a.txt")])

    assert message["content"] == "只有文字"


def test_images_helper_filters_files():
    items = [
        attachment.from_bytes(PNG, "a.png"),
        attachment.from_bytes(b"text", "b.txt"),
    ]

    assert [item["name"] for item in attachment.images(items)] == ["a.png"]


def test_summarize_lists_attachments():
    items = [
        attachment.from_bytes(PNG, "a.png"),
        attachment.from_bytes(b"text", "b.txt"),
    ]

    text = attachment.summarize(items)

    assert "图片 a.png" in text
    assert "文件 b.txt" in text


# 展示辅助
def test_human_size():
    assert attachment.human_size(0) == "0 B"
    assert attachment.human_size(999) == "999 B"
    assert attachment.human_size(2048) == "2.0 KB"
    assert attachment.human_size(5 * 1024 * 1024) == "5.0 MB"
    assert attachment.human_size("坏值") == "?"


def test_compact_for_display_shortens_base64():
    messages = [{"role": "user", "content": [{"image_url": {"url": "A" * 5000}}]}]

    compacted = attachment.compact_for_display(messages)
    url = compacted[0]["content"][0]["image_url"]["url"]

    assert len(url) < 200
    assert "base64" in url
    # 原数据不能被就地改掉
    assert len(messages[0]["content"][0]["image_url"]["url"]) == 5000


def test_compact_for_display_keeps_short_values():
    assert attachment.compact_for_display("短文本") == "短文本"
    assert attachment.compact_for_display(123) == 123


# 记忆与 LLM 接线
def test_memory_uses_ollama_shape_by_default():
    from stlibs.ai import Memory

    memory = Memory()
    memory.add_user_msg("看图", [attachment.from_bytes(PNG, "cat.png")])

    assert memory.messages[0]["images"]
    assert memory.messages[0]["content"] == "看图"


def test_memory_can_build_openai_shape():
    from stlibs.ai import Memory

    memory = Memory()
    memory.add_user_msg("看图", [attachment.from_bytes(PNG, "cat.png")], target="openai")

    assert isinstance(memory.messages[0]["content"], list)
    assert memory.messages[0]["content"][1]["type"] == "image_url"


def test_memory_add_user_image_still_works(tmp_path):
    from stlibs.ai import Memory

    path = tmp_path / "old.png"
    path.write_bytes(PNG)
    memory = Memory()
    memory.add_user_image(str(path))

    assert memory.messages[0]["images"]


def test_local_llm_receives_attachments(monkeypatch):
    pytest.importorskip("PySide6.QtCore")
    import stlibs

    monkeypatch.setattr(stlibs.Config, "mcp", {"enable": False, "mcp": []}, raising=False)
    monkeypatch.setattr(stlibs.Config, "rag", {"enable": False}, raising=False)
    monkeypatch.setattr(stlibs.Config, "memory", {"shortterm": True, "longterm": False}, raising=False)

    from stlibs.ai import local

    llm = local.LLM("attach-probe")
    captured = {}

    class FakeCall:
        def run(self, messages):
            captured["messages"] = [dict(item) for item in messages]
            yield "看到了"

    llm.function_call = FakeCall()
    llm.rag = None

    list(llm.chat("这是什么", attachments=[attachment.from_bytes(PNG, "cat.png")]))

    message = captured["messages"][-1]
    assert message["content"] == "这是什么"
    assert len(message["images"]) == 1


def test_page_payload_round_trip():
    """网页端上传 -> 后端解析：字段名必须对得上。"""
    payload = json.loads(json.dumps([{"name": "a.txt", "mime": "text/plain", "data": _b64(b"hello")}]))

    items = attachment.normalize(payload)

    assert items[0]["name"] == "a.txt"
    assert items[0]["text"] == "hello"


# 视觉能力（纯文本模型会静默忽略图片，得提前告诉用户）
@pytest.fixture(autouse=True)
def _clear_vision_cache():
    attachment._VISION_CACHE.clear()
    yield
    attachment._VISION_CACHE.clear()


def _fake_show(monkeypatch, capabilities):
    import ollama

    def fake(model, **kwargs):
        if capabilities is None:
            raise RuntimeError("模型不存在")
        return {"capabilities": capabilities, "model": model}

    monkeypatch.setattr(ollama, "show", fake, raising=False)


def test_vision_capability_true(monkeypatch):
    _fake_show(monkeypatch, ["completion", "vision"])

    assert attachment.vision_capability("gemma") is True
    assert attachment.can_see_images("gemma") is True


def test_vision_capability_false(monkeypatch):
    _fake_show(monkeypatch, ["completion", "tools"])

    assert attachment.vision_capability("glm4") is False
    assert attachment.can_see_images("glm4") is False


def test_vision_capability_unknown_on_error(monkeypatch):
    _fake_show(monkeypatch, None)

    assert attachment.vision_capability("云端模型") is None
    assert attachment.can_see_images("云端模型") is True, "查不到就别乱警告"


def test_vision_capability_missing_field(monkeypatch):
    import ollama

    monkeypatch.setattr(ollama, "show", lambda model, **kwargs: {"model": model}, raising=False)

    assert attachment.vision_capability("老版本 ollama") is None


def test_vision_capability_is_cached(monkeypatch):
    calls = []

    import ollama

    def fake(model, **kwargs):
        calls.append(model)
        return {"capabilities": ["vision"]}

    monkeypatch.setattr(ollama, "show", fake, raising=False)

    attachment.vision_capability("m")
    attachment.vision_capability("m")

    assert calls == ["m"], "重复查询要打缓存"
