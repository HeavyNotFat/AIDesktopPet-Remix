import os
import json

import ollama

from .. import Config
from . import mcp as mcp_server

from PySide6.QtCore import Signal, QObject

mcp: mcp_server.MCP | None = None
if Config.mcp["enable"]:
    mcp = mcp_server.MCP()
for server in Config.mcp["mcp"]:
    if not Config.mcp["enable"]:
        break
    runnable_args = [arg.replace("$PATH$", os.getcwd()) for arg in server["args"]]
    mcp.connect_stdio(server_id=server["server"], command=server["command"], args=runnable_args, )
with open("./resources/prompts.json", "r", encoding="utf-8") as f:
    prompts = json.load(f)


class LLM(QObject):
    memory_signal = Signal(list)

    def __init__(self, model: str = "glm4", system_prompt: str = ""):
        super().__init__()
        from . import Memory, fc, rag

        self.memory = Memory()
        self.function_call = fc.FunctionCall(model)
        self.model = model
        self._closed = False
        self.rag = None

        if Config.mcp["enable"]:
            mcp.inject_to_funcall(self.function_call)
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

    def chat(self, user_input: str):
        if not Config.memory["shortterm"]:
            self.memory.clear()
        self.memory.add_user_msg(user_input)
        messages = self.memory.messages
        if self.rag and self._need_rag(user_input):
            messages = self._inject_rag(user_input, messages)
        print("[RAG MSG]", messages)

        reply_parts = []
        for event in self.function_call.run(messages):
            if isinstance(event, str):
                reply_parts.append(event)
                yield event
                continue

            self._handle_event(event)
            yield event

        reply = "".join(reply_parts)
        if reply:
            self.memory.add_assistant_msg(reply)
        self.memory_signal.emit([self.model, self.memory.messages])

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
