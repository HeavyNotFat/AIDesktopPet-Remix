from typing import Dict, Any, List, Optional
import threading
import asyncio
import json

from mcp.types import TextContent


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
