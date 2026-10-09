import base64
import inspect
import json
import os
import threading
import time
import uuid

from .attachment import (  # noqa: F401
    MAX_ATTACHMENTS,
    compact_for_display,
    data_url,
    encode_image,
    from_base64,
    from_bytes,
    from_path,
    human_size,
    images,
    normalize,
    ollama_message,
    openai_message,
    summarize,
    with_document_context,
)


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
    """长期记忆：攒够若干轮对话就压缩成摘要落盘，之后按相关性召回。"""
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
        """同一个记忆文件会被多个实例同时写，锁按路径共享。"""
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
        # 记忆文件被多个实例共享，每次读盘才能拿到最新内容
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
    """把长期记忆插在 system 消息之后，别让它变成最新一轮用户输入。"""
    if not context:
        return messages

    index = 0
    while index < len(messages) and isinstance(messages[index], dict) and messages[index].get("role") == "system":
        index += 1

    return [*messages[:index], {"role": "system", "content": context}, *messages[index:]]


def _skill_list(skills=None) -> list:
    if skills is not None:
        return [skill for skill in skills if isinstance(skill, dict)]

    from .. import Config

    return [skill for skill in (getattr(Config, "skills", None) or []) if isinstance(skill, dict)]


def find_skill(name, skills=None):
    """按名字找技能，忽略大小写、允许带前导斜杠。"""
    wanted = str(name or "").strip().lstrip("/").strip().casefold()
    if not wanted:
        return None

    for skill in _skill_list(skills):
        if str(skill.get("name") or "").strip().casefold() == wanted:
            return dict(skill)
    return None


def parse_skill(text, skills=None):
    """把 ``/名字 正文`` 拆成 ``(技能, 正文)``，没匹配上就原样返回。"""
    text = text or ""
    if not text.startswith("/"):
        return None, text

    head, _sep, rest = text[1:].partition(" ")
    skill = find_skill(head, skills)
    if skill is None:
        return None, text
    return skill, rest.strip()


def inject_skill(messages, prompt):
    """技能提示词插在 system 段之后。"""
    if not isinstance(prompt, str) or not prompt.strip():
        return messages

    index = 0
    while index < len(messages) and isinstance(messages[index], dict) and messages[index].get("role") == "system":
        index += 1

    return [*messages[:index], {"role": "system", "content": str(prompt)}, *messages[index:]]


def skill_prompt(skill) -> str:
    if not isinstance(skill, dict):
        return ""
    return str(skill.get("prompt") or "").strip()


def _coop_config() -> dict:
    # 运行期才取 Config，模块级导入会成环
    from .. import Config

    return getattr(Config, "coop", None) or {}


def build_llm(model_key, system_prompt="", coop=False):
    from .. import Config
    from . import cloud, local

    parameters = (Config.models or {}).get(model_key)
    if parameters:
        return cloud.LLM(
            parameters.get("name") or model_key,
            parameters.get("apikey"),
            parameters.get("baseurl"),
            system_prompt,
            coop=coop,
        )
    return local.LLM(model_key, system_prompt, coop=coop)


def chat_prompt(llm, question):
    """按签名适配 ``local.LLM.chat(user_input, should_emit)`` 与 ``cloud.LLM.chat(query)``。"""
    parameters = inspect.signature(llm.chat).parameters
    message_params = [name for name in parameters if name not in {"should_emit", "emit"}]
    if not message_params:
        raise TypeError(f"{type(llm).__name__}.chat 没有可识别的消息参数：{list(parameters)}")

    kwargs = {name: False for name in parameters if name in {"should_emit", "emit"}}
    kwargs[message_params[0]] = question
    return llm.chat(**kwargs)


class MultiAgentCoop:
    """多模型协作：主模型出稿，其它模型评审，主模型据此定稿。"""
    MODES = {"review": "评审改稿", "parallel": "并行汇总"}

    REVIEW_PROMPT = (
        "你是评审专家。请针对收到的回答逐条指出事实错误、遗漏和表达不清之处，"
        "只列问题、不要评价好坏、也不要重写答案。"
    )
    FINAL_PROMPT = (
        "下面是你自己的初稿，以及其它模型对它的评审意见。请综合这些意见，"
        "输出一份更准确、更完整的最终回答，只输出答案本身。\n\n"
        "【初稿】\n{draft}\n\n【评审意见】\n{notes}"
    )
    SYNTHESIZE_PROMPT = (
        "下面是多个模型对同一个问题的回答。请综合它们，去重、纠错、补全，"
        "输出一份最完整的最终回答，只输出答案本身。\n\n{answers}"
    )

    def __init__(self, config=None, builder=None):
        self._config = config if config is not None else _coop_config()
        self._builder = builder or build_llm
        self._lock = threading.RLock()
        self._instances = {}

    def reconfigure(self, config=None):
        with self._lock:
            self._config = config if config is not None else _coop_config()
            self._instances.clear()

    @property
    def enable(self):
        return bool(self._config.get("enable"))

    @property
    def mode(self):
        mode = str(self._config.get("mode") or "review")
        return mode if mode in self.MODES else "review"

    @property
    def rounds(self):
        try:
            return max(1, min(3, int(self._config.get("rounds") or 1)))
        except (TypeError, ValueError):
            return 1

    @property
    def agents(self):
        agents = []
        for item in self._config.get("agents") or []:
            if not isinstance(item, dict):
                continue
            model = str(item.get("model") or "").strip()
            if not model:
                continue
            agents.append({
                "model": model,
                "name": str(item.get("name") or model).strip() or model,
                "prompt": str(item.get("prompt") or "").strip(),
            })
        return agents

    def instance(self, model_key, system_prompt=""):
        """协作成员的实例按 (模型, 角色提示词) 缓存。"""
        key = (model_key, system_prompt)
        with self._lock:
            llm = self._instances.get(key)
            if llm is None:
                llm = self._builder(model_key, system_prompt=system_prompt)
                self._instances[key] = llm
            return llm

    def describe(self):
        agents = self.agents
        if not self.enable:
            return "协作已关闭"
        if not agents:
            return "协作已开启，但没有配置可用的模型"
        return f"{self.MODES[self.mode]}：主模型 + {len(agents)} 个协作模型，{self.rounds} 轮"

    def run(self, query, lead_llm, base_messages=None):
        """产出协作过程：先若干 dict 事件，最后把定稿当文本片段吐出来。"""
        base_messages = list(base_messages or [])
        agents = self.agents

        if not agents:
            yield {"type": "coop", "stage": "empty", "detail": "没有可用的协作模型，按普通模式回答"}
            yield from self._reply(lead_llm, query, base_messages)
            return

        if self.mode == "parallel":
            yield from self._run_parallel(query, lead_llm, base_messages, agents)
            return

        yield from self._run_review(query, lead_llm, base_messages, agents)

    def _run_parallel(self, query, lead_llm, base_messages, agents):
        answers = []
        for agent in agents:
            yield {"type": "coop", "stage": "agent_start", "agent": agent["name"], "model": agent["model"]}
            text, error = self._ask(agent, query)
            if error:
                yield {"type": "coop", "stage": "agent_error", "agent": agent["name"], "detail": error}
                continue
            answers.append((agent["name"], text))
            yield {"type": "coop", "stage": "agent_done", "agent": agent["name"], "text": text}

        if not answers:
            yield {"type": "coop", "stage": "empty", "detail": "所有协作模型都失败了，按普通模式回答"}
            yield from self._reply(lead_llm, query, base_messages)
            return

        prompt = self.SYNTHESIZE_PROMPT.format(
            answers="\n\n".join(f"【{name}】\n{text}" for name, text in answers)
        )
        yield {"type": "coop", "stage": "final", "agents": len(answers)}
        yield from self._reply(lead_llm, prompt, base_messages)

    def _run_review(self, query, lead_llm, base_messages, agents):
        yield {"type": "coop", "stage": "draft", "agents": len(agents)}
        draft = self._lead_text(lead_llm, base_messages)
        if not draft:
            yield {"type": "coop", "stage": "empty", "detail": "主模型没有给出初稿"}
            return

        request = f"用户的问题：\n{query}\n\n需要评审的回答：\n{draft}"
        notes = []
        for round_index in range(1, self.rounds + 1):
            for agent in agents:
                yield {
                    "type": "coop",
                    "stage": "review_start",
                    "agent": agent["name"],
                    "round": round_index,
                }
                text, error = self._ask(agent, request)
                if error:
                    yield {"type": "coop", "stage": "agent_error", "agent": agent["name"], "detail": error}
                    continue
                notes.append((agent["name"], text))
                yield {"type": "coop", "stage": "review_done", "agent": agent["name"], "text": text}

        if not notes:
            yield {"type": "coop", "stage": "empty", "detail": "没有拿到任何评审意见，直接输出初稿"}
            yield draft
            return

        prompt = self.FINAL_PROMPT.format(
            draft=draft,
            notes="\n\n".join(f"【{name}】\n{text}" for name, text in notes),
        )
        yield {"type": "coop", "stage": "final", "reviews": len(notes)}
        yield from self._reply(lead_llm, prompt, base_messages)

    @staticmethod
    def _invoke(llm, messages):
        complete = getattr(llm, "complete", None)
        if callable(complete):
            yield from complete(messages)
            return
        prompt = messages[-1].get("content", "") if messages else ""
        yield from chat_prompt(llm, prompt)

    def _lead_text(self, llm, base_messages):
        try:
            return "".join(
                chunk for chunk in self._invoke(llm, base_messages) if isinstance(chunk, str)
            ).strip()
        except Exception:  # noqa: BLE001
            return ""

    def _reply(self, llm, prompt, base_messages):
        yield from self._invoke(llm, [*base_messages, {"role": "user", "content": prompt}])

    def _ask(self, agent, prompt):
        """让一个协作成员回答，失败只报告不中断。"""
        try:
            llm = self.instance(agent["model"], agent["prompt"] or self.REVIEW_PROMPT)
        except Exception as exc:  # noqa: BLE001
            return "", f"{type(exc).__name__}: {exc}"

        try:
            text = "".join(
                chunk for chunk in self._invoke(llm, [{"role": "user", "content": prompt}])
                if isinstance(chunk, str)
            ).strip()
        except Exception as exc:  # noqa: BLE001
            return "", f"{type(exc).__name__}: {exc}"

        return text, "" if text else "模型返回了空内容"


class Memory:
    def __init__(self):
        self.messages = []

    def add_user_msg(self, msg: str, attachments=None, target: str = "ollama"):
        """attachments 是附件列表（见 ``stlibs.ai.attachment``）；target 决定消息形状。"""
        items = normalize(attachments) if attachments else []
        text = with_document_context(msg, items)
        builder = openai_message if target == "openai" else ollama_message
        self.messages.append(builder(text, items))

    def add_user_image(self, path: str):
        self.add_user_msg("", [from_path(path)], target="ollama")

    def add_assistant_msg(self, msg: str):
        self.messages.append({"role": "assistant", "content": msg})

    def add_system_msg(self, msg: str):
        self.messages.append({"role": "system", "content": msg})

    def clear(self):
        self.messages.clear()


class TTSEmotion:
    # TODO: TTSEmotion
    pass
