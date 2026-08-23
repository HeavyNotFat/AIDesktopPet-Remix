from typing import Generator, Union, Dict, List, Optional
import os
import json
import re

from .. import Config
from . import MCP

from PySide6.QtCore import Signal, QObject

mcp = None
if Config.mcp['enable']: mcp = MCP()
for server in Config.mcp["mcp"]:
    if not Config.mcp['enable']: break
    runnable_args = [
        arg.replace("$PATH$", os.getcwd())
        for arg in server["args"]
    ]
    mcp.connect_stdio(
        server_id=server["server"],
        command=server["command"],
        args=runnable_args,
    )
with open("./resources/prompts.json", "r", encoding="utf-8") as f:
    prompts = json.load(f)


class LLM(QObject):
    memory_signal = Signal(list)

    def __init__(self, model: str = "glm4", system_prompt: str = ""):
        super().__init__()
        from . import LTMemory, Memory, rag, FunctionCall

        self.memory = Memory()
        self.function_call = FunctionCall(model)
        self.model = model
        self._closed = False
        self.rag = None

        if Config.rag['enable']: self.rag = rag.HybridRAG(
            Config.rag['model'],
            Config.rag["embedding"],
            Config.rag["resort"],
            Config.rag["chunks"],
            Config.rag["overlap"],
        )
        if Config.mcp['enable']: mcp.inject_to_funcall(self.function_call)

        self.lt_memory = LTMemory(self.rag)
        if system_prompt.strip():
            self.memory.add_system_msg(system_prompt)

    def chat(self, user_input: str) -> Generator[Union[str, Dict], None, None]:
        if not Config.memory["shortterm"]:
            self.memory.clear()

        self.memory.add_user_msg(user_input)
        if Config.memory["longterm"]:
            try:
                self.lt_memory.consolidate(self.memory.messages)
            except Exception as e:
                print(f"[Memory] 长期记忆压缩失败: {e}")

        working_messages = self._build_rag_messages(
            messages=self.memory.messages,
            user_input=user_input,
        )

        reply_parts = []
        for event in self.function_call.run(working_messages):
            if isinstance(event, str):
                reply_parts.append(event)
                yield event

            elif isinstance(event, dict):
                event_type = event.get("type")

                if event_type == "tool_call":
                    print(
                        f"调用工具: {event.get('name')}"
                        f"({event.get('args')})"
                    )
                    yield event

                elif event_type == "tool_result":
                    print(f"工具结果: {event.get('result')}")
                    yield event

                else:
                    yield event

        reply = "".join(reply_parts)

        if reply:
            self.memory.add_assistant_msg(reply)

        self.memory_signal.emit([
            self.model,
            self.memory.messages,
        ])
    
    def _need_rag(self, user_input: str, messages: Optional[List[Dict]] = None) -> bool:
        """判断当前问题是否需要查询长期记忆。"""
        import ollama

        recent_context = ""

        if isinstance(messages, list):
            recent_messages = messages[-6:]
            context_parts = []

            for message in recent_messages:
                if not isinstance(message, dict):
                    continue

                content = message.get("content", "")
                if not isinstance(content, str) or not content.strip():
                    continue

                context_parts.append(
                    f"{message.get('role', '')}: {content}"
                )

            recent_context = "\n".join(context_parts)

        try:
            prompt = prompts["rag"].replace("{recent_context}", recent_context).replace("{user_input}", user_input)

            resp = ollama.chat(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
            )

            result = resp["message"]["content"].strip()
            result = result.replace("\\", "")
            print(f"[RAG Judge] {result}")

        except Exception as e:
            print(f"[RAG Judge] 判断失败: {e}")
            return False

        try:
            data = json.loads(result)
            if isinstance(data, dict):
                need_rag = data.get("need_rag", False)

                if isinstance(need_rag, bool):
                    print(f"[RAG Judge] need_rag={need_rag}")
                    return need_rag

                if isinstance(need_rag, str):
                    return need_rag.strip().lower() == "true"

        except (json.JSONDecodeError, TypeError) as e:
            print(type(e).__name__, str(e))

        match = re.search(r'"need_rag"\s*:\s*(true|false)', result, re.IGNORECASE)
        if match:
            need_rag = match.group(1).lower() == "true"
            print(f"[RAG Judge] need_rag={need_rag}")
            return need_rag

        print("[RAG Judge] 无法解析判断结果，默认不使用 RAG")
        return False
    
    def _build_rag_messages(self, messages: List[Dict], user_input: str) -> List[Dict]:
        if not isinstance(messages, list):
            print(f"[RAG] messages 类型错误: {type(messages)}")
            return []

        need_rag = self._need_rag(user_input=user_input, messages=messages) if Config.rag['enable'] else False

        print(f"[RAG] need_rag={need_rag}")
        if not need_rag:
            return messages
        print("[RAG] 当前问题需要RAG检索")

        try:
            docs = self.rag.retrieve(user_input, collection=Config.rag['type'])
        except Exception as e:
            print(f"[RAG] 检索失败: {e}")
            return messages

        if not docs:
            print("[RAG] 未找到相关RAG")
            return messages

        print("[RAG] 找到相关RAG")
        context = "\n\n".join(
            f"- {doc.content}"
            for doc in docs
            if getattr(doc, "content", None)
        )

        if not context:
            return messages

        rag_message = {
            "role": "system",
            "content": prompts["ltmemory"].replace("{context}", context),
        }

        result = list(messages)
        insert_index = 0

        while (
            insert_index < len(result)
            and isinstance(result[insert_index], dict)
            and result[insert_index].get("role") == "system"
        ):
            insert_index += 1

        result.insert(insert_index, rag_message)
        return result
