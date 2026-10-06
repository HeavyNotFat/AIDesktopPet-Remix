# AI Desktop Pet · Remix

AI 桌宠：Live2D / 静态形象 + 本地（Ollama）或云端（OpenAI 兼容）大模型，
带 RAG 知识库、MCP 工具调用、桌面聊天窗与**网页聊天**（`resources/web/onlinechat`）。

* 入口：`main.py`（启动闪屏）→ `core.py`（主循环 + 网页聊天服务线程）
* UI 主题：`stlibs/themes/<name>/`，可插拔，契约见 `stlibs/__init__.py::_ThemeTypingProtocol`
* AI：`stlibs/ai/`（`local.py` / `cloud.py` / `rag/` / `fc/` / `mcp/`）
* 网页聊天：`stlibs/mproc/onlinechat/`（FastAPI + 独立 LLM 实例池）

## 运行

```bash
pip install -r requirements.txt
python main.py
```

网页聊天地址：<http://127.0.0.1:52493>（端口可用 `ONLINECHAT_PORT` 覆盖）。

## 网页聊天的实例隔离

网页聊天**不复用**桌面端聊天窗缓存的 LLM 实例
（`stlibs.themes.hacker.cache_llm_class`）。它有自己的实例池：

* 每个网页会话 id（前端把本地对话 id 当 `session_id` 传上来）一个独立实例与独立记忆；
* 换模型一定重建实例；LRU + 空闲超时回收（`WEBCHAT_MAX_SESSIONS` / `WEBCHAT_SESSION_TTL`）；
* 调用时对 `local.LLM` 显式 `should_emit=False`；`cloud.LLM` 没有这个开关，
  它的 `memory_signal` 从不连接，所以也不会碰到桌面端 Qt 界面；
* 会话被回收后重发不会报 502，而是 409（`SessionClosedError`）；
* 观测接口：`POST /api/status` 能看到池内实例数、创建总数、淘汰数。

浏览器的对话记录存在 localStorage，刷新页面会带着同一个 `session_id` 继续；
只有删除对话（前端调 `POST /api/reset`）或服务端回收才会重置记忆。
细节与回归防线见 `tests/test_onlinechat.py`。

## 质量门禁

```bash
python -m tools.ci        # UI 冲突 / 抽象契约 / 主题映射 / 配置资源 / 前后端契约，共 54 项
python -m pytest tests -q # 门禁自身 + 网页聊天实例 + 平台行为金丝雀
```

完整说明见 [`docs/CI.md`](CI.md)（含「怎么测」：门禁、接口联调、端到端三步）。

## 单独调网页聊天

```bash
python -m stlibs.mproc.onlinechat                    # 只起聊天服务，不需要 Qt
python tools/manual/probe_onlinechat.py glm4:latest  # 另一个终端：验证实例隔离
```

## 已知平台行为

PySide6 下 Qt 子类的 `@abstractmethod` **在运行期不生效**
（`Shiboken.ObjectType.__new__` 排在 `ABCMeta.__new__` 前面，
`__abstractmethods__` 不会生成）。因此主题/UI 的抽象契约由
`tools/ci` 的 `abs/*` 检查在提交阶段静态保证，
并有金丝雀测试记录该行为（`tests/test_platform_behaviour.py`）。

## 许可

见 [LICENSE](LICENSE)。
