from typing import List, Dict, Callable, Any, Generator, Union, Optional
import json

from ... import Config


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
