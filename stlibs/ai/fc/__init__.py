from typing import List, Dict, Callable, Any, Generator, Union, Optional
import json

from ... import Config


class FunctionCall:
    """支持流式输出的函数调用引擎。"""
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
                "parameters": parameters or {"type": "object", "properties": {}, "required": []},
            },
        })

    def run(self, messages: List[Dict]) -> Generator[Union[str, Dict], None, None]:
        for _ in range(self.max_rounds):
            content_parts: List[str] = []
            tool_calls_map: Dict[int, Dict[str, Any]] = {}

            yield from self._stream_once(messages, content_parts, tool_calls_map)

            if not tool_calls_map:
                return  # 没有工具调用说明模型已给出最终答案

            full_tool_calls = self._build_tool_calls(tool_calls_map)
            yield from self._emit_tool_call_events(full_tool_calls)

            messages.append({
                "role": "assistant",
                "content": "".join(content_parts),
                "tool_calls": full_tool_calls,
            })

            yield from self._execute_tools(full_tool_calls, messages)

        yield "达到最大工具调用轮次限制"

    def _stream_once(
        self,
        messages: List[Dict],
        content_parts: List[str],
        tool_calls_map: Dict[int, Dict[str, Any]],
    ) -> Generator[str, None, None]:
        """发起一次流式请求并实时 yield 文本片段，tool_calls 增量写入 tool_calls_map。"""
        kwargs: Dict[str, Any] = {"model": self.model, "messages": messages, "stream": True}
        if Config.mcp["enable"] and self._tools_schema:
            kwargs["tools"] = self._tools_schema

        for chunk in self.client.chat(**kwargs):
            msg = chunk.get("message", {})

            delta_content = msg.get("content", "")
            if delta_content:
                content_parts.append(delta_content)
                yield delta_content

            for tc in msg.get("tool_calls") or []:
                self._merge_tool_call_delta(tool_calls_map, tc)

    @staticmethod
    def _merge_tool_call_delta(tool_calls_map: Dict[int, Dict[str, Any]], tc: Dict[str, Any]) -> None:
        """把单个增量 tool_call 分片按 index 拼进 tool_calls_map。"""
        idx = tc.get("index", 0)
        fn = tc.get("function", {})
        entry = tool_calls_map.setdefault(idx, {"name": "", "arguments": ""})

        if fn.get("name"):
            entry["name"] = fn["name"]

        new_args = fn.get("arguments")
        if new_args:
            if isinstance(new_args, dict):
                new_args = json.dumps(new_args, ensure_ascii=False)
            if isinstance(entry["arguments"], str):
                entry["arguments"] += new_args
            else:
                entry["arguments"] = new_args

    @staticmethod
    def _build_tool_calls(tool_calls_map: Dict[int, Dict[str, Any]]) -> List[Dict[str, Any]]:
        full_tool_calls = []
        for idx in sorted(tool_calls_map):
            data = tool_calls_map[idx]
            try:
                args = json.loads(data["arguments"]) if data["arguments"] else {}
            except json.JSONDecodeError:
                args = {"_raw": data["arguments"]}
            full_tool_calls.append({"function": {"name": data["name"], "arguments": args}})
        return full_tool_calls

    @staticmethod
    def _emit_tool_call_events(full_tool_calls: List[Dict[str, Any]]) -> Generator[Dict, None, None]:
        for tc in full_tool_calls:
            yield {
                "type": "tool_call",
                "name": tc["function"]["name"],
                "args": tc["function"]["arguments"],
            }

    def _execute_tools(
        self, full_tool_calls: List[Dict[str, Any]], messages: List[Dict]
    ) -> Generator[Dict, None, None]:
        for tc in full_tool_calls:
            name = tc["function"]["name"]
            args = tc["function"]["arguments"]
            result = self._call_tool(name, args)

            yield {"type": "tool_result", "name": name, "result": result}
            messages.append({"role": "tool", "content": json.dumps(result, ensure_ascii=False)})

    def _call_tool(self, name: str, args: Dict[str, Any]) -> Any:
        try:
            return self._registry[name](**args)
        except Exception as e:
            return {"error": str(e)}
