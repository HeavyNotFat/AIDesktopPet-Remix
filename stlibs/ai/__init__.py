import base64
import json
import os
import threading
import time
import uuid


def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        data = base64.b64encode(image_file.read()).decode("utf-8")
        image_file.close()
    return data


def _one_line(text, limit):
    if not text:
        return ""
    collapsed = " ".join(str(text).split())
    return collapsed if len(collapsed) <= limit else collapsed[: limit - 1] + "…"


def _bigrams(text):
    compact = "".join(text.split())
    if len(compact) < 2:
        return {compact} if compact else set()
    return {compact[i : i + 2] for i in range(len(compact) - 1)}


def summarize_turns(turns, max_chars=800):
    """把若干轮对话压成一段摘要（默认抽取式，不依赖模型）。

    需要更"像人写"的摘要时，给 LTMemory 传一个 summarizer 覆盖即可。
    """
    lines = []
    for turn in turns:
        user = _one_line(turn.get("user"), 120)
        answer = _one_line(turn.get("assistant"), 200)
        if user:
            lines.append(f"用户问：{user}")
        if answer:
            lines.append(f"回答：{answer}")

    text = "；".join(lines)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1] + "…"


class LTMemory:
    """长期记忆：把对话按轮次攒起来压缩成摘要落盘，下次按相关性召回。"""

    STORE_PATH = "./resources/memory/lt_memory.json"
    _path_locks = {}
    _locks_guard = threading.Lock()

    def __init__(
        self,
        scope="default",
        path=None,
        window=4,
        max_chars=800,
        max_entries=500,
        top_k=3,
        summarizer=None,
    ):
        self.scope = scope or "default"
        self.path = os.path.abspath(path or self.STORE_PATH)
        self.window = max(1, int(window))
        self.max_chars = max(80, int(max_chars))
        self.max_entries = max(1, int(max_entries))
        self.top_k = max(1, int(top_k))
        self.summarizer = summarizer or summarize_turns

        self._pending = []
        self._lock = self._shared_lock(self.path)

    @classmethod
    def _shared_lock(cls, path):
        """同一个记忆文件可能被多个 LLM 实例（多个网页会话）同时写，锁必须按路径共享。"""
        with cls._locks_guard:
            lock = cls._path_locks.get(path)
            if lock is None:
                lock = threading.RLock()
                cls._path_locks[path] = lock
            return lock

    def _read(self):
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return []

        entries = data.get("entries") if isinstance(data, dict) else None
        return entries if isinstance(entries, list) else []

    def _write(self, entries):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        kept = entries[-self.max_entries :]
        temp_path = f"{self.path}.tmp"
        with open(temp_path, "w", encoding="utf-8") as handle:
            json.dump({"version": 1, "entries": kept}, handle, ensure_ascii=False, indent=2)
        os.replace(temp_path, self.path)
        return kept

    def _entries(self):
        # 每次读盘：记忆文件被多个实例（多个网页会话）共享，
        # 用 mtime 做缓存判据会在两次写入落在同一时间戳刻度时读到旧快照
        with self._lock:
            return self._read()

    def remember_turn(self, user, assistant):
        """累积一轮对话；攒够 window 轮就压缩入库并返回新条目。"""
        user = _one_line(user, 400)
        assistant = _one_line(assistant, 800)
        if not user and not assistant:
            return None

        self._pending.append({"user": user, "assistant": assistant, "at": time.time()})
        if len(self._pending) < self.window:
            return None

        return self.flush()

    def flush(self):
        """把待压缩的对话立刻入库。"""
        if not self._pending:
            return None

        with self._lock:
            turns = self._pending
            self._pending = []

            summary = self.summarizer(turns, self.max_chars)
            entry = {
                "id": uuid.uuid4().hex[:12],
                "scope": self.scope,
                "created_at": time.time(),
                "turns": len(turns),
                "summary": summary,
                "topics": [_one_line(turn.get("user"), 60) for turn in turns if turn.get("user")],
            }

            entries = self._read()
            entries.append(entry)
            self._write(entries)

        return entry

    def recall(self, query, top_k=None, scope=None):
        """按相关性召回摘要；scope=None 表示跨全部记忆检索。"""
        query = (query or "").strip()
        if not query:
            return []

        limit = max(1, int(top_k or self.top_k))
        query_grams = _bigrams(query)
        scored = []

        for entry in self._entries():
            if scope and entry.get("scope") != scope:
                continue
            text = " ".join([entry.get("summary", ""), *entry.get("topics", [])])
            score = self._score(query, query_grams, text)
            if score <= 0:
                continue
            scored.append((score, entry))

        scored.sort(key=lambda item: (item[0], item[1].get("created_at", 0)), reverse=True)
        return [{**entry, "score": round(score, 4)} for score, entry in scored[:limit]]

    @staticmethod
    def _score(query, query_grams, text):
        """字符二元组 Dice 相似度 + 完整命中加权。

        刻意不引第三方检索库：长期记忆量级小（几百条），
        这样它在没装 rank_bm25 / 向量库的环境下也能工作。
        """
        grams = _bigrams(text)
        if not grams or not query_grams:
            return 0.0

        overlap = len(query_grams & grams)
        dice = 2 * overlap / (len(query_grams) + len(grams))
        return dice * 4 + (1.0 if query in text else 0.0)

    def build_context(self, query, top_k=None, scope=None, max_chars=1200):
        recalled = self.recall(query, top_k=top_k, scope=scope)
        if not recalled:
            return ""

        lines = [
            "以下是从长期记忆中召回的历史对话摘要，仅在与当前问题相关时参考，"
            "不要向用户复述这段说明：",
        ]
        for index, entry in enumerate(recalled, 1):
            lines.append(f"[{index}]（{entry.get('turns', 0)} 轮）{entry.get('summary', '')}")

        text = "\n".join(lines)
        return text if len(text) <= max_chars else text[: max_chars - 1] + "…"

    def entries(self):
        return list(self._entries())

    def clear(self, scope=None):
        with self._lock:
            entries = self._read()
            if scope is None:
                kept = []
            else:
                kept = [entry for entry in entries if entry.get("scope") != scope]

            removed = len(entries) - len(kept)
            self._write(kept)
            self._pending = []

        return removed

    def stats(self):
        entries = self._entries()
        scopes = {}
        for entry in entries:
            key = entry.get("scope", "default")
            scopes[key] = scopes.get(key, 0) + 1

        return {
            "entries": len(entries),
            "pending": len(self._pending),
            "scopes": scopes,
            "path": self.path,
        }


def inject_memory_context(messages, context):
    """把长期记忆插在 system 消息之后，别让它变成"最新一轮用户输入"。"""
    if not context:
        return messages

    index = 0
    while index < len(messages) and isinstance(messages[index], dict) and messages[index].get("role") == "system":
        index += 1

    return [*messages[:index], {"role": "system", "content": context}, *messages[index:]]


class Memory:
    """
    实时对话记忆
    """
    def __init__(self):
        self.messages = []

    def add_user_msg(self, msg: str):
        self.messages.append({"role": "user", "content": msg})

    def add_user_image(self, path: str):
        self.messages.append({"role": "user", "content": {"type": "image_url", "image_url": {
            "url": f"data:image/png;base64,{encode_image(path)}"}}})

    def add_assistant_msg(self, msg: str):
        self.messages.append({"role": "assistant", "content": msg})

    def add_system_msg(self, msg: str):
        self.messages.append({"role": "system", "content": msg})

    def clear(self):
        self.messages.clear()


class MultiAgentCoop:
    """
    多Agent合作
    """
    # TODO: MultiAgentCoop
    pass


class TTSEmotion:
    """
    语音情感
    """
    # TODO: TTSEmotion
    pass
