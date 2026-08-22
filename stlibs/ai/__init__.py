from typing import Any, Callable, Dict, Generator, List, Optional, Union
import asyncio
import threading
import base64
import json

from . import rag
from .. import Config

from mcp.types import TextContent


def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        data = base64.b64encode(image_file.read()).decode("utf-8")
        image_file.close()
    return data


class MCP:
    """MCP 客户端管理器（线程安全单例）"""

    _instance = None
    _instance_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        # 双重检查锁，保证多线程下只创建一个实例
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._initialized = False
                    cls._instance = instance

        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        with self._instance_lock:
            if self._initialized:
                return

            self._sessions: Dict[str, Any] = {}
            self._read_streams: Dict[str, Any] = {}
            self._write_streams: Dict[str, Any] = {}

            self._loop = asyncio.new_event_loop()

            self._thread = threading.Thread(
                target=self._start_loop,
                name="MCP-Loop",
                daemon=True,
            )
            self._thread.start()

            # 确保事件循环已经真正启动
            asyncio.run_coroutine_threadsafe(
                self._noop(),
                self._loop
            ).result()

            self._closed = False

            # 最后再标记初始化完成
            self._initialized = True

            print("[MCP] 全局 MCP 管理器初始化完成")

    def _start_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    async def _noop(self):
        pass

    def _run_sync(self, coro):
        if self._closed or not self._loop.is_running():
            coro.close()
            raise RuntimeError("MCP 后台事件循环已经关闭")

        future = asyncio.run_coroutine_threadsafe(
            coro,
            self._loop
        )

        return future.result()

    def connect_stdio(
        self,
        server_id: str,
        command: str,
        args: List[str] = None,
        env: Dict = None,
    ):
        self._run_sync(
            self._connect_stdio_async(
                server_id,
                command,
                args or [],
                env,
            )
        )

    async def _connect_stdio_async(
        self,
        server_id: str,
        command: str,
        args: List[str],
        env: Dict,
    ):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        if server_id in self._sessions:
            print(f"[MCP] Server {server_id} 已经连接")
            return

        server_params = StdioServerParameters(
            command=command,
            args=args,
            env=env,
        )

        ctx = stdio_client(server_params)

        read, write = await ctx.__aenter__()

        session_ctx = ClientSession(read, write)
        session = await session_ctx.__aenter__()

        try:
            await session.initialize()
        except Exception:
            try:
                await session_ctx.__aexit__(None, None, None)
            finally:
                await ctx.__aexit__(None, None, None)
            raise

        self._sessions[server_id] = session
        self._read_streams[server_id] = ctx
        self._write_streams[server_id] = session_ctx

        print(f"[MCP] 成功连接 Server: {server_id}")

    def disconnect(self, server_id: str):
        if server_id not in self._sessions:
            return

        self._run_sync(
            self._disconnect_async(server_id)
        )

    async def _disconnect_async(self, server_id: str):
        session_ctx = self._write_streams.pop(server_id, None)
        stream_ctx = self._read_streams.pop(server_id, None)

        self._sessions.pop(server_id, None)

        if session_ctx is not None:
            try:
                await session_ctx.__aexit__(None, None, None)
            except Exception as e:
                print(f"[MCP] 关闭 Session {server_id} 失败: {e}")

        if stream_ctx is not None:
            try:
                await stream_ctx.__aexit__(None, None, None)
            except Exception as e:
                print(f"[MCP] 关闭 Stream {server_id} 失败: {e}")

        print(f"[MCP] 已断开 Server: {server_id}")

    def shutdown(self):
        if self._closed:
            return

        try:
            if self._loop.is_running():

                for sid in list(self._sessions.keys()):
                    try:
                        asyncio.run_coroutine_threadsafe(
                            self._disconnect_async(sid),
                            self._loop,
                        )
                    except Exception:
                        pass

                import time
                time.sleep(0.5)

                self._loop.call_soon_threadsafe(
                    self._loop.stop
                )

            if self._thread.is_alive():
                self._thread.join(timeout=2.0)

        except Exception:
            pass

        finally:
            self._closed = True

    def close_sync(self):
        if self._closed:
            return

        try:
            for sid in list(self._sessions.keys()):
                try:
                    self.disconnect(sid)
                except Exception as e:
                    print(f"[MCP] 断开 {sid} 失败: {e}")

        finally:
            if self._loop.is_running():
                self._loop.call_soon_threadsafe(
                    self._loop.stop
                )

            if self._thread.is_alive():
                self._thread.join(timeout=5.0)

            self._closed = True

            print("[MCP] MCP 管理器已关闭")

    def list_tools(
        self,
        server_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        return self._run_sync(
            self._list_tools_async(server_id)
        )

    async def _list_tools_async(
        self,
        server_id: Optional[str],
    ) -> List[Dict[str, Any]]:

        if server_id is not None:
            if server_id not in self._sessions:
                raise ValueError(
                    f"Server {server_id} 未连接"
                )

            targets = {
                server_id: self._sessions[server_id]
            }

        else:
            targets = dict(self._sessions)

        all_tools = []

        for sid, session in targets.items():
            result = await session.list_tools()

            for tool in result.tools:
                parameters = getattr(
                    tool,
                    "input_schema",
                    None,
                )

                if parameters is None:
                    parameters = getattr(
                        tool,
                        "inputSchema",
                        {},
                    )

                all_tools.append({
                    "server_id": sid,
                    "name": tool.name,
                    "description": tool.description or "",
                    "parameters": parameters,
                })

        return all_tools

    def call_tool(
        self,
        server_id: str,
        tool_name: str,
        arguments: dict,
    ) -> str:

        return self._run_sync(
            self._call_tool_async(
                server_id,
                tool_name,
                arguments,
            )
        )

    async def _call_tool_async(
        self,
        server_id: str,
        tool_name: str,
        arguments: dict,
    ) -> str:

        if server_id not in self._sessions:
            raise ValueError(
                f"Server {server_id} 未连接"
            )

        session = self._sessions[server_id]

        result = await session.call_tool(
            tool_name,
            arguments,
        )

        texts = []

        for content in result.content:
            if isinstance(content, TextContent):
                texts.append(content.text)
            elif hasattr(content, "text"):
                texts.append(content.text)

        return "\n".join(texts)

    def inject_to_funcall(self, funcall_engine):
        mcp_tools = self.list_tools()

        print("[MCP] 工具列表")
        print(
            json.dumps(
                mcp_tools,
                indent=3,
                ensure_ascii=False,
            )
        )

        for tool in mcp_tools:

            def make_proxy(sid, tname):
                def proxy_func(**kwargs):
                    raw_result = self.call_tool(
                        sid,
                        tname,
                        kwargs,
                    )

                    try:
                        return json.loads(raw_result)
                    except json.JSONDecodeError:
                        return {
                            "text": raw_result
                        }

                return proxy_func

            proxy = make_proxy(
                tool["server_id"],
                tool["name"],
            )

            proxy.__name__ = tool["name"]
            proxy.__doc__ = tool["description"]

            funcall_engine.register(
                func=proxy,
                description=tool["description"],
                parameters=tool["parameters"],
            )

        print(
            f"[MCP] 已将 {len(mcp_tools)} 个外部工具注入 "
            f"FunctionCall 引擎"
        )

    @classmethod
    def reset_instance(cls):
        """彻底关闭并重置单例，主要用于程序退出或测试。"""

        with cls._instance_lock:
            instance = cls._instance

            if instance is None:
                return

            # 先把全局引用拿掉
            cls._instance = None

        try:
            instance.close_sync()
        except Exception:
            pass


class FunctionCall:
    """支持流式输出的函数调用引擎"""

    def __init__(self, model: str = "qwen3.5:4b", max_rounds: int = 10, host: Optional[str] = None):
        import ollama

        self.model = model
        self.max_rounds = max_rounds
        self.client = ollama.Client(host=host) if host else ollama
        self._tools_schema: List[Dict[str, Any]] = []
        self._registry: Dict[str, Callable] = {}

    @property
    def get_tools_schema(self) -> List[Dict[str, Any]]:
        return self._tools_schema

    def register(self, func: Callable, description: str = "", parameters: Optional[Dict] = None):
        name = func.__name__
        self._registry[name] = func
        self._tools_schema.append({
            "type": "function",
            "function": {
                "name": name,
                "description": description or func.__doc__ or "",
                "parameters": parameters or {"type": "object", "properties": {}, "required": []}
            }
        })

    def run(self, messages: List[Dict]) -> Generator[Union[str, Dict], None, None]:
        """
        执行带工具调用的流式对话循环
        :yields:
            str: 模型生成的文本片段（实时流式）
            dict: 工具调用事件 {"type": "tool_call", "name": ..., "args": ...}
            dict: 工具执行结果 {"type": "tool_result", "name": ..., "result": ...}
        """
        for _ in range(self.max_rounds):
            kwargs: Dict[str, Any] = {
                "model": self.model,
                "messages": messages,
                "stream": True
            }

            if Config.mcp['enable'] and self._tools_schema:
                kwargs["tools"] = self._tools_schema

            content_parts: List[str] = []
            # 用 index 作为 key 来拼接分块到达的 tool_calls
            tool_calls_map: Dict[int, Dict[str, Any]] = {}

            stream = self.client.chat(**kwargs)
            for chunk in stream:
                msg = chunk.get("message", {})

                # 流式输出文本内容
                delta_content = msg.get("content", "")
                if delta_content:
                    content_parts.append(delta_content)
                    yield delta_content

                # 流式拼接 tool_calls（关键！）
                delta_tool_calls = msg.get("tool_calls")
                if delta_tool_calls:
                    for tc in delta_tool_calls:
                        idx = tc.get("index", 0)
                        fn = tc.get("function", {})

                        if idx not in tool_calls_map:
                            tool_calls_map[idx] = {
                                "name": fn.get("name", ""),
                                "arguments": ""
                            }
                        # 增量拼接 name 和 arguments
                        if fn.get("name"):
                            tool_calls_map[idx]["name"] = fn["name"]
                        if fn.get("arguments"):
                            new_args = fn.get("arguments", "")
                            if isinstance(new_args, dict):
                                # 如果模型直接返回了完整字典，转为 JSON 字符串再拼接（或直接覆盖）
                                new_args = json.dumps(new_args, ensure_ascii=False)

                            if isinstance(tool_calls_map[idx]["arguments"], str):
                                tool_calls_map[idx]["arguments"] += new_args
                            else:
                                # 防御性编程（？）
                                tool_calls_map[idx]["arguments"] = new_args

            if tool_calls_map:
                # 构造完整的 assistant message 追加到历史
                full_tool_calls = []
                for idx in sorted(tool_calls_map.keys()):
                    tc_data = tool_calls_map[idx]
                    try:
                        args = json.loads(tc_data["arguments"]) if tc_data["arguments"] else {}
                    except json.JSONDecodeError:
                        args = {"_raw": tc_data["arguments"]}

                    full_tc = {
                        "function": {
                            "name": tc_data["name"],
                            "arguments": args
                        }
                    }
                    full_tool_calls.append(full_tc)

                    # yield 工具调用事件，方便外部感知
                    yield {"type": "tool_call", "name": tc_data["name"], "args": args}

                # 将完整的 assistant 消息加入上下文
                messages.append({
                    "role": "assistant",
                    "content": "".join(content_parts),
                    "tool_calls": full_tool_calls
                })

                # 依次执行工具并追加结果
                for tc in full_tool_calls:
                    fn_name = tc["function"]["name"]
                    fn_args = tc["function"]["arguments"]
                    try:
                        result = self._registry[fn_name](**fn_args)
                    except Exception as e:
                        result = {"error": str(e)}

                    yield {"type": "tool_result", "name": fn_name, "result": result}
                    messages.append({
                        "role": "tool",
                        "content": json.dumps(result, ensure_ascii=False)
                    })

                continue

            return

        yield "达到最大工具调用轮次限制"


class LTMemory:
    """长期记忆：将历史对话压缩摘要后存入 RAG 或本地内存"""

    def __init__(
        self,
        rag_instance: Optional[object] = None,
        summary_model: Optional[str] = None,
        default_model: str = "glm4:latest"
    ):
        self.rag = rag_instance
        self.summary_model = (
            summary_model
            or getattr(rag_instance, "chat_model", None)
            or default_model
        )
        # 当 RAG 不可用时的本地存储
        self.memory_store: List[Dict] = []

    def consolidate(
        self,
        messages: List[Dict],
        trigger_len: int = 20
    ) -> Optional[str]:
        """当短期记忆过长时，提取关键信息写入长期知识库或本地存储"""
        import ollama

        if len(messages) < trigger_len:
            return None

        to_summarize = messages[: len(messages) // 2]
        content = "\n".join(
            f"{m['role']}: {m.get('content', '')}"
            for m in to_summarize
            if isinstance(m.get("content"), str)
        )
        if not content.strip():
            return None

        prompt = (
            "请将以下对话历史浓缩为一段客观的事实性知识摘要，"
            "用于未来的长期记忆检索。\n\n"
            f"{content}"
        )

        resp = ollama.chat(
            model=self.summary_model,
            messages=[{"role": "user", "content": prompt}]
        )

        summary = resp["message"]["content"].strip()
        if not summary:
            return None

        metadata = {
            "source": "long_term_memory",
            "type": "conversation_summary",
        }

        if self.rag is not None:
            self.rag.add_documents(
                [summary],
                metadatas=[metadata],
                collection=self.rag.memory_collection,
            )
        else:
            # 无 RAG 时存入本地内存列表
            self.memory_store.append({
                "content": summary,
                "metadata": metadata,
            })

        return summary

    def get_memories(self) -> List[Dict]:
        """统一获取长期记忆（兼容 RAG 和本地存储）"""
        if self.rag is not None:
            # 根据你的 RAG 实现调整检索方法
            return self.rag.search(
                query="long term memory",
                collection=self.rag.memory_collection,
            )
        return self.memory_store


class Memory:
    """
    实时对话记忆
    """
    def __init__(self):
        self.messages = []

    def add_user_msg(self, msg: str):
        self.messages.append({"role": "user", "content": msg})

    def add_user_image(self, path: str):
        self.messages.append({"role": "user", "content": {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encode_image(path)}"}}})

    def add_assistant_msg(self, msg: str):
        self.messages.append({"role": "assistant", "content": msg})

    def add_system_msg(self, msg: str):
        self.messages.append({"role": "system", "content": msg})

    def clear(self):
        self.messages.clear()


class MultiAgentCoop:
    """
    多人合作
    """
    # TODO: MultiAgentCoop
    pass


class TTSEmotion:
    """
    语音情感
    """
    # TODO: TTSEmotion
    pass
