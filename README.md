# AI Desktop Pet · Remix

AI 桌宠：Live2D / 静态形象 + 本地（Ollama）或云端（OpenAI 兼容）大模型，
带 RAG 知识库、MCP 工具调用、桌面聊天窗与**网页聊天**（`resources/web/onlinechat`）。

* 入口：`main.py`（启动闪屏）→ `core.py`（主循环 + 网页聊天服务线程）
* UI 主题：`stlibs/themes/<name>/`，可插拔，契约见 `stlibs/__init__.py::_ThemeTypingProtocol`
* AI：`stlibs/ai/`（`local.py` / `cloud.py` / `rag/` / `fc/` / `mcp/`，长期记忆 `LTMemory`）
* 网页聊天：`stlibs/mproc/onlinechat/`（FastAPI + 独立 LLM 实例池 + SSE 流式）

## 运行

```bash
pip install -r requirements.txt
python main.py
```

网页聊天地址：<http://127.0.0.1:52493>（端口可用 `ONLINECHAT_PORT` 覆盖）。

## 网页聊天

地址 <http://127.0.0.1:52493>（端口可用 `ONLINECHAT_PORT` 覆盖）。

| 接口 | 说明 |
| --- | --- |
| `POST /api/chat` | 一次性返回完整回答 |
| `POST /api/chat/stream` | SSE 流式：`start` → 若干 `delta` → `done`，出错发 `error` |
| `POST /api/chat/recall` | 把命中本地缓存的一轮问答补记进会话记忆（不调模型） |
| `POST /api/reset` | 丢弃某个会话的实例与记忆 |
| `POST /api/status` | 实例池观测：会话数、实例创建数、淘汰数 |
| `POST /api/getmodellist` | 可选模型（本地 Ollama + 云端别名） |

前端行为：

* 逐字渲染（实测首字延迟约 0.13s），停止按钮会中断流并把已收到的部分留在对话里；
* 回答按「模型 + 问题」缓存在浏览器本地（默认 7 天 / 200 条，`CACHE_TTL`、`CACHE_MAX` 可调），
  命中时直接展示并标注「本地缓存」，侧边栏的数据库图标可一键清空；
* 对话记录存 localStorage，刷新页面继续用同一个 `session_id`。

### 实例隔离

网页聊天**不复用**桌面端聊天窗缓存的 LLM 实例
（`stlibs.themes.hacker.cache_llm_class`）。它有自己的实例池：

* 每个网页会话 id（前端把本地对话 id 当 `session_id` 传上来）一个独立实例与独立记忆；
* 换模型一定重建实例；LRU + 空闲超时回收（`WEBCHAT_MAX_SESSIONS` / `WEBCHAT_SESSION_TTL`）；
* 调用时对 `local.LLM` 显式 `should_emit=False`；`cloud.LLM` 没有这个开关，
  它的 `memory_signal` 从不连接，所以也不会碰到桌面端 Qt 界面；
* 流式生成期间会话锁由一个专用线程持有，客户端断开时自动收手并交还锁；
* 会话被回收后重发不会报 502，而是 409（`SessionClosedError`）。

细节与回归防线见 `tests/test_onlinechat.py`。

## 长期记忆

`stlibs/ai/__init__.py::LTMemory`：把对话按 `window` 轮攒起来压缩成摘要，
落盘到 `resources/memory/lt_memory.json`（运行时数据，已 gitignore），
之后按字符二元组相似度召回并注入到 system 位置。

* 开关就是设置页里的「长期存储记忆」（`Config.memory['longterm']`）——之前是个空开关；
* 默认抽取式摘要，不额外调模型；想换成模型摘要就传 `summarizer=`；
* 多个实例（多个网页会话）共享同一个文件，写入走文件锁 + 原子替换；
* 召回刻意不依赖向量库，没装 chromadb / rank_bm25 也能工作。

## 质量门禁

```bash
python -m tools.ci        # UI 冲突 / 抽象契约 / 主题映射 / 配置资源 / 前后端契约，共 54 项
python -m pytest tests -q # 门禁自身 + 网页聊天实例 + 平台行为金丝雀
```

完整说明见 [`CI.md`](CI.md)（含「怎么测」：门禁、接口联调、端到端三步）。

## 单独调网页聊天

```bash
python -m stlibs.mproc.onlinechat                    # 只起聊天服务，不需要 Qt
python tools/manual/probe_onlinechat.py glm4:latest  # 另一个终端：验证实例隔离 + 流式
```

## 已知平台行为

PySide6 下 Qt 子类的 `@abstractmethod` **在运行期不生效**
（`Shiboken.ObjectType.__new__` 排在 `ABCMeta.__new__` 前面，
`__abstractmethods__` 不会生成）。因此主题/UI 的抽象契约由
`tools/ci` 的 `abs/*` 检查在提交阶段静态保证，
并有金丝雀测试记录该行为（`tests/test_platform_behaviour.py`）。

## 许可

见 [LICENSE](LICENSE)。
