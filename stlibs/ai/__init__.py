from typing import Any, Callable, Dict, Generator, List, Optional, Union
from datetime import datetime
import asyncio
import threading
import base64
import json
import os

import chromadb
import ollama

from .. import Config

from mcp.types import TextContent
from rank_bm25 import BM25Okapi

with open("./resources/prompts.json", "r", encoding="utf-8") as f:
    prompts = json.load(f)


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

            self._thread = threading.Thread(target=self._start_loop, name="MCP-Loop", daemon=True, )
            self._thread.start()

            # 确保事件循环已经真正启动
            asyncio.run_coroutine_threadsafe(self._noop(), self._loop).result()

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

        future = asyncio.run_coroutine_threadsafe(coro, self._loop)

        return future.result()

    def connect_stdio(self, server_id: str, command: str, args: List[str] = None, env: Dict = None, ):
        self._run_sync(self._connect_stdio_async(server_id, command, args or [], env, ))

    async def _connect_stdio_async(self, server_id: str, command: str, args: List[str], env: Dict, ):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        if server_id in self._sessions:
            print(f"[MCP] Server {server_id} 已经连接")
            return

        server_params = StdioServerParameters(command=command, args=args, env=env, )

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

        self._run_sync(self._disconnect_async(server_id))

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
                        asyncio.run_coroutine_threadsafe(self._disconnect_async(sid), self._loop, )
                    except Exception:
                        pass

                import time
                time.sleep(0.5)

                self._loop.call_soon_threadsafe(self._loop.stop)

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
                self._loop.call_soon_threadsafe(self._loop.stop)

            if self._thread.is_alive():
                self._thread.join(timeout=5.0)

            self._closed = True

            print("[MCP] MCP 管理器已关闭")

    def list_tools(self, server_id: Optional[str] = None, ) -> List[Dict[str, Any]]:
        return self._run_sync(self._list_tools_async(server_id))

    async def _list_tools_async(self, server_id: Optional[str], ) -> List[Dict[str, Any]]:

        if server_id is not None:
            if server_id not in self._sessions:
                raise ValueError(f"Server {server_id} 未连接")

            targets = {server_id: self._sessions[server_id]}

        else:
            targets = dict(self._sessions)

        all_tools = []

        for sid, session in targets.items():
            result = await session.list_tools()

            for tool in result.tools:
                parameters = getattr(tool, "input_schema", None, )

                if parameters is None:
                    parameters = getattr(tool, "inputSchema", {}, )

                all_tools.append({"server_id": sid, "name": tool.name, "description": tool.description or "",
                                  "parameters": parameters, })

        return all_tools

    def call_tool(self, server_id: str, tool_name: str, arguments: dict, ) -> str:

        return self._run_sync(self._call_tool_async(server_id, tool_name, arguments, ))

    async def _call_tool_async(self, server_id: str, tool_name: str, arguments: dict, ) -> str:

        if server_id not in self._sessions:
            raise ValueError(f"Server {server_id} 未连接")

        session = self._sessions[server_id]

        result = await session.call_tool(tool_name, arguments, )

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
        print(json.dumps(mcp_tools, indent=3, ensure_ascii=False, ))

        for tool in mcp_tools:

            def make_proxy(sid, tname):
                def proxy_func(**kwargs):
                    raw_result = self.call_tool(sid, tname, kwargs, )

                    try:
                        return json.loads(raw_result)
                    except json.JSONDecodeError:
                        return {"text": raw_result}

                return proxy_func

            proxy = make_proxy(tool["server_id"], tool["name"], )

            proxy.__name__ = tool["name"]
            proxy.__doc__ = tool["description"]

            funcall_engine.register(func=proxy, description=tool["description"], parameters=tool["parameters"], )

        print(f"[MCP] 已将 {len(mcp_tools)} 个外部工具注入 "
              f"FunctionCall 引擎")

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
        self._tools_schema.append({"type": "function",
                                   "function": {"name": name, "description": description or func.__doc__ or "",
                                                "parameters": parameters or {"type": "object", "properties": {},
                                                                             "required": []}}})

    def run(self, messages: List[Dict]) -> Generator[Union[str, Dict], None, None]:
        """
        执行带工具调用的流式对话循环
        :yields:
            str: 模型生成的文本片段（实时流式）
            dict: 工具调用事件 {"type": "tool_call", "name": ..., "args": ...}
            dict: 工具执行结果 {"type": "tool_result", "name": ..., "result": ...}
        """
        for _ in range(self.max_rounds):
            kwargs: Dict[str, Any] = {"model": self.model, "messages": messages, "stream": True}

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
                            tool_calls_map[idx] = {"name": fn.get("name", ""), "arguments": ""}
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

                    full_tc = {"function": {"name": tc_data["name"], "arguments": args}}
                    full_tool_calls.append(full_tc)

                    # yield 工具调用事件，方便外部感知
                    yield {"type": "tool_call", "name": tc_data["name"], "args": args}

                # 将完整的 assistant 消息加入上下文
                messages.append({"role": "assistant", "content": "".join(content_parts), "tool_calls": full_tool_calls})

                # 依次执行工具并追加结果
                for tc in full_tool_calls:
                    fn_name = tc["function"]["name"]
                    fn_args = tc["function"]["arguments"]
                    try:
                        result = self._registry[fn_name](**fn_args)
                    except Exception as e:
                        result = {"error": str(e)}

                    yield {"type": "tool_result", "name": fn_name, "result": result}
                    messages.append({"role": "tool", "content": json.dumps(result, ensure_ascii=False)})

                continue

            return

        yield "达到最大工具调用轮次限制"


class RAG:
    RAG_ROOT = "./resources/rag"

    def __init__(self, chat_model=None, embed_model=None, top_k=None, chunk_size=None, overlap=None):
        self.chat_model = chat_model
        self.embed_model = embed_model
        self.collection_name = Config.rag["collection"]
        self.knowledge_path = os.path.join(self.RAG_ROOT, self.collection_name)
        self.chroma_path = os.path.join(self.RAG_ROOT, "chroma_db")

        self.top_k = top_k
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.client = None
        self.collection = None
        self.bm25 = None
        self.bm25_chunks = []

    @staticmethod
    def log(message, level="INFO"):
        now = datetime.now().strftime("%H:%M:%S")
        print(f"[{now}] [{level}] {message}")

    def init_chroma(self):
        os.makedirs(self.chroma_path, exist_ok=True)
        self.client = chromadb.PersistentClient(path=self.chroma_path)
        self.collection = self.client.get_or_create_collection(name=self.collection_name)
        self.log(f"Chroma 初始化完成：{self.chroma_path}")

    def read_documents(self):
        if not os.path.exists(self.knowledge_path):
            self.log(f"知识库不存在：{self.knowledge_path}", "WARN")
            return []

        if os.path.isfile(self.knowledge_path):
            if os.path.splitext(self.knowledge_path)[1].lower() not in [".txt", ".md"]:
                self.log(f"不支持的知识库文件类型：{self.knowledge_path}", "WARN")
                return []

            paths = [self.knowledge_path]

        else:
            paths = []

            for root, _, files in os.walk(self.knowledge_path):
                for filename in files:
                    ext = os.path.splitext(filename)[1].lower()

                    if ext in [".txt", ".md"]:
                        paths.append(os.path.join(root, filename))

        documents = []
        for path in paths:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    text = f.read()
                if text.strip():
                    documents.append({"source": path, "text": text})
            except Exception as e:
                self.log(f"读取文件失败：{path} ({e})", "ERROR")

        return documents

    def split_text(self, text):
        text = (text.replace("\r\n", "\n").replace("\r", "\n").strip())

        if not text:
            return []

        chunks = []
        start = 0
        text_length = len(text)

        while start < text_length:
            end = min(start + self.chunk_size, text_length)
            chunk = text[start:end].strip()

            if chunk:
                chunks.append(chunk)
            if end >= text_length:
                break

            start = max(0, end - self.overlap)

        return chunks

    def create_chunks(self):
        documents = self.read_documents()
        chunks = []

        for document in documents:
            text_chunks = self.split_text(document["text"])
            for index, chunk in enumerate(text_chunks):
                chunks.append(
                    {"id": str(len(chunks)), "source": document["source"], "chunk_index": index, "text": chunk})

        return chunks

    @staticmethod
    def tokenize(text):
        return list(text)

    def get_embedding(self, text):
        response = ollama.embeddings(model=self.embed_model, prompt=text)
        return response["embedding"]

    def build_bm25(self, chunks):
        self.bm25_chunks = chunks
        corpus = []
        for chunk in chunks:
            corpus.append(self.tokenize(chunk["text"]))
        self.bm25 = BM25Okapi(corpus)

    def build(self):
        if self.collection is None:
            self.init_chroma()

        chunks = self.create_chunks()
        self.build_bm25(chunks)

        if not chunks:
            self.log("知识库中没有可用内容", "WARN")
            return False

        if self.collection.count() > 0:
            all_ids = self.collection.get()["ids"]
            if all_ids: self.collection.delete(ids=all_ids)

        for index, chunk in enumerate(chunks):
            try:
                vector = self.get_embedding(chunk["text"])

                self.collection.add(ids=[chunk["id"]], embeddings=[vector], documents=[chunk["text"]],
                                    metadatas=[{"source": chunk["source"], "chunk_index": chunk["chunk_index"]}])

            except Exception as e:
                self.log(f"Embedding失败：Chunk {index} ({e})", "ERROR")
                return False

        self.log(f"索引建立完成，共 {len(chunks)} 个chunk")

        return True

    def load(self):
        if self.collection is None:
            self.init_chroma()

        count = self.collection.count()
        if count <= 0:
            self.log("Chroma索引为空", "WARN")
            return False

        return True

    def load_or_build(self):
        if self.load():
            return True

        self.log("没有现有索引，开始建立", "WARN")

        return self.build()

    def bm25_search(self, query, top_k=None):
        if self.bm25 is None:
            return []

        top_k = top_k or self.top_k
        scores = self.bm25.get_scores(self.tokenize(query))
        indexes = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        results = []

        for i in indexes:
            chunk = self.bm25_chunks[i]
            results.append({"score": scores[i], "source": chunk["source"], "chunk_index": chunk["chunk_index"],
                            "text": chunk["text"], "type": "bm25"})

        return results

    def search(self, query, top_k=None):
        top_k = top_k or self.top_k
        # BM25
        bm25_results = self.bm25_search(query, top_k)
        # 向量
        vector_results = []

        if self.collection.count() > 0:
            query_vector = self.get_embedding(query)
            result = self.collection.query(query_embeddings=[query_vector], n_results=top_k)
            for text, meta, distance in zip(result["documents"][0], result["metadatas"][0], result["distances"][0]):
                vector_results.append(
                    {"score": 1 - distance, "source": meta["source"], "chunk_index": meta["chunk_index"], "text": text,
                     "type": "vector"})

        return self.merge_results(bm25_results, vector_results, top_k)

    def compress_context(self, query, search_results):
        if not search_results:
            return "没有检索到相关知识。"

        compressed = []
        for index, result in enumerate(search_results):
            try:
                response = ollama.chat(model=self.chat_model, messages=[{"role": "user",
                                                                         "content": prompts['rag_compressed'].replace(
                                                                             "{query}", query).replace('text', result[
                                                                             'text'])}], )
                text = (response["message"]["content"].strip())

                if text:
                    compressed.append(f"[知识片段 {index + 1}]\n来源：\n{result["source"]}\n\n{text}")
            except Exception as e:
                self.log(f"压缩失败 {index}: {e}", "ERROR")

        if not compressed:
            return "没有检索到相关知识。"

        return "\n".join(compressed)

    @staticmethod
    def merge_results(bm25_results, vector_results, top_k):
        result_map = {}
        # BM25权重
        for r in bm25_results:
            key = r["text"]
            result_map[key] = {**r, "final_score": r["score"] * 2}

        # vector权重
        for r in vector_results:
            key = r["text"]
            if key in result_map:
                result_map[key]["final_score"] += (r["score"])
            else:
                result_map[key] = {**r, "final_score": r["score"]}

        results = list(result_map.values())
        results.sort(key=lambda x: x["final_score"], reverse=True)
        return results[:top_k]

    @staticmethod
    def build_context(search_results):
        if not search_results:
            return "没有检索到相关知识。"

        parts = []
        for index, result in enumerate(search_results):
            parts.append(f"[知识片段 {index + 1}]\n来源：\n{result["source"]}\n\n{result['text']}")
        return "\n".join(parts)

    def clear(self):
        if self.collection is None:
            self.init_chroma()

        if self.collection.count() > 0:
            all_ids = self.collection.get()["ids"]
            if all_ids: self.collection.delete(ids=all_ids)


class LTMemory:
    """长期记忆：将历史对话压缩摘要后存入 RAG 或本地内存"""
    # TODO: LT
    pass


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
