import os
import json

import ollama

from .. import Config, SharingData
from . import mcp as mcp_server

from PySide6.QtCore import Signal, QObject

mcp: mcp_server.MCP | None = None
if Config.mcp["enable"]:
    try:
        mcp = mcp_server.MCP()
    except Exception as exc:  # noqa: BLE001 - MCP 起不来不该拖垮聊天
        print(f"[MCP] 管理器初始化失败，本次将不加载任何 MCP 工具：{type(exc).__name__}: {exc}")
        mcp = None

for server in Config.mcp["mcp"]:
    if not Config.mcp["enable"] or mcp is None:
        break
    runnable_args = [arg.replace("$PATH$", os.getcwd()) for arg in server["args"]]
    try:
        mcp.connect_stdio(server_id=server["server"], command=server["command"], args=runnable_args, )
    except Exception as exc:  # noqa: BLE001 - 单个 MCP server 失败不影响对话
        print(f"[MCP] 启动 {server.get('server')!r} 失败，跳过该工具：{type(exc).__name__}: {exc}")
with open("./resources/prompts.json", "r", encoding="utf-8") as f:
    prompts = json.load(f)


class LLM(QObject):
    memory_signal = Signal(list)
    coop_signal = Signal(dict)

    def __init__(self, model: str = "glm4", system_prompt: str = "", coop: bool | None = None):
        super().__init__()
        from . import LTMemory, Memory, MultiAgentCoop, fc, rag

        self.memory = Memory()
        self.function_call = fc.FunctionCall(model)
        self.model = model
        self._closed = False
        self.rag = None
        self.lt_memory = LTMemory(scope=f"local:{model}") if Config.memory["longterm"] else None
        self.coop_disabled = coop is False
        self.coop = None if self.coop_disabled else (MultiAgentCoop() if (coop or Config.coop.get("enable")) else None)
        SharingData.llm_instances[f"local:{model}"] = self

        if Config.mcp["enable"] and mcp is not None:
            try:
                mcp.inject_to_funcall(self.function_call)
            except Exception as exc:  # noqa: BLE001 - 注不进工具也要能正常聊天
                print(f"[MCP] 注入工具失败，将只做纯对话：{type(exc).__name__}: {exc}")
        if Config.rag["enable"]:
            self.rag = rag.RAG(
                chat_model=Config.rag['model'],
                embed_model=Config.rag['embedding'],
                top_k=Config.rag['top_k'],
                chunk_size=Config.rag['chunks'],
                overlap=Config.rag['overlap'],)
            self.rag.load_or_build()
        if system_prompt.strip():
            self.memory.add_system_msg(system_prompt)
        # else:
        #     self.memory.add_system_msg(prompts['general'])

    def chat(self, user_input: str, should_emit: bool = True, skill=None, attachments=None):
        if not Config.memory["shortterm"]:
            self.memory.clear()
        self.memory.add_user_msg(user_input, attachments, target="ollama")

        if self.coop is not None and self.coop.enable:
            stream = self.coop.run(user_input, self, base_messages=self.memory.messages)
        else:
            messages = self.memory.messages
            if skill:
                from . import inject_skill

                messages = inject_skill(messages, skill)
            if self.rag and self._need_rag(user_input):
                messages = self._inject_rag(user_input, messages)
            if self.lt_memory is not None:
                messages = self._inject_memory(user_input, messages)
            print("[RAG MSG]", messages)
            stream = self.function_call.run(messages)

        reply_parts = []
        for event in stream:
            if isinstance(event, str):
                reply_parts.append(event)
                yield event
                continue

            if isinstance(event, dict) and event.get("type") == "coop":
                self.coop_signal.emit(event)
            else:
                self._handle_event(event)
            yield event

        reply = "".join(reply_parts)
        if reply:
            self.memory.add_assistant_msg(reply)
            if self.lt_memory is not None:
                self.lt_memory.remember_turn(user_input, reply)
        if should_emit: self.memory_signal.emit([self.model, self.memory.messages])

    def complete(self, messages: list):
        """按给定消息跑一轮，不读写短期记忆（协作成员与初稿走这里）。"""
        for event in self._call_chat(messages, should_emit=False):
            if isinstance(event, str):
                yield event
                continue

            self._handle_event(event)
            yield event

    def _inject_memory(self, user_input: str, messages: list):
        from . import inject_memory_context

        return inject_memory_context(messages, self.lt_memory.build_context(user_input))

    @staticmethod
    def _need_rag(user_input: str):
        try:
            response = ollama.chat(
                model=Config.rag['model'],
                messages=[{"role": "system", "content": prompts['rag']},
                          {'role': 'user', 'content': user_input}],
            )
            result = response["message"]["content"].strip().upper()
            print("[RAG]", result)
            need_rag = "yes" in result.lower()

            print(f"[RAG] {'需要' if need_rag else '不需要'}："
                  f"{user_input}")
            return need_rag

        except Exception as e:
            print(f"[RAG] 判断失败：{e}")
            return False

    def _inject_rag(self, user_input: str, messages: list):
        results = self.rag.search(user_input, top_k=Config.rag['top_k'])
        if not results:
            return messages
        if Config.rag['compressed_enable']:
            context = self.rag.compress_context(user_input, results)
        else:
            context = self.rag.build_context(results)
        rag_message = {"role": "user",
                       "content": ("以下是与当前问题相关的知识库内容。\n"
                                   "请优先依据这些内容回答。\n"
                                   "如果知识库没有足够信息，不要编造。\n\n"
                                   "===== 知识库 =====\n\n"
                                   f"{context}\n"
                                   f"===== 用户问题 =====\n\n"
                                   f"{user_input}")}

        if not messages:
            return [rag_message]

        return [*messages, rag_message]

    @staticmethod
    def _handle_event(event):
        event_type = event.get("type")

        if event_type == "tool_call":
            print(f"调用工具: {event.get('name')}"
                  f"({event.get('args')})")

        elif event_type == "tool_result":
            print(f"工具结果: {event.get('result')}")
