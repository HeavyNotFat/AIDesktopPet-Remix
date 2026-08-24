import os

from .utils import log

SUPPORTED_EXTENSIONS = (".txt", ".md")


def read_documents(knowledge_path):
    if not os.path.exists(knowledge_path):
        log(f"知识库不存在：{knowledge_path}", "WARN")
        return []

    if os.path.isfile(knowledge_path):
        if os.path.splitext(knowledge_path)[1].lower() not in SUPPORTED_EXTENSIONS:
            log(f"不支持的知识库文件类型：{knowledge_path}", "WARN")
            return []

        paths = [knowledge_path]

    else:
        paths = []

        for root, _, files in os.walk(knowledge_path):
            for filename in files:
                ext = os.path.splitext(filename)[1].lower()

                if ext in SUPPORTED_EXTENSIONS:
                    paths.append(os.path.join(root, filename))

    documents = []
    for path in paths:
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
            if text.strip():
                documents.append({"source": path, "text": text})
        except Exception as e:
            log(f"读取文件失败：{path} ({e})", "ERROR")

    return documents


def split_text(text, chunk_size, overlap):
    text = (text.replace("\r\n", "\n").replace("\r", "\n").strip())

    if not text:
        return []

    chunks = []
    start = 0
    text_length = len(text)

    while start < text_length:
        end = min(start + chunk_size, text_length)
        chunk = text[start:end].strip()

        if chunk:
            chunks.append(chunk)
        if end >= text_length:
            break

        start = max(0, end - overlap)

    return chunks


def create_chunks(knowledge_path, chunk_size, overlap):
    documents = read_documents(knowledge_path)
    chunks = []

    for document in documents:
        text_chunks = split_text(document["text"], chunk_size, overlap)
        for index, chunk in enumerate(text_chunks):
            chunks.append(
                {"id": str(len(chunks)), "source": document["source"], "chunk_index": index, "text": chunk})

    return chunks
