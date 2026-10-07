# ADPRemix 代码结构与职责地图

> 这份文档回答三个问题：**代码放在哪、每个文件干什么、改动时要动哪些地方**。
> 全部结论来自实际读代码与运行验证；标注「待验证」的是静态分析提出、尚未逐一复现的疑点。

## 0. 一句话总览

AI 桌宠：Live2D / 静态序列帧形象 + 本地（Ollama）或云端（OpenAI 兼容）大模型，
对外提供 **桌面聊天窗**、**网页聊天**（FastAPI + SSE）、**插件系统**（Python / JavaScript）、
**UDP SDK**（外部程序控制桌宠）四条入口，另有 RAG 知识库、MCP 工具调用、长期记忆、
多模型协作与一套 54 项的自研 CI 门禁。

## 1. 代码规模

| 区域                      | 文件数 |    行数 |    占比 | 说明                                 |
|:------------------------|----:|------:|------:|:-----------------------------------|
| `resources/`（配置/模型/知识库） |  93 | 74378 | 71.4% | 绝大部分是 Live2D 模型 JSON 与知识库语料，不是手写代码 |
| `stlibs/`（核心库）          |  58 | 10742 | 10.3% | AI、主题、插件、SDK、网页聊天服务                |
| `tests/`（测试）            |  27 |  8082 |  7.8% | 536 个用例                            |
| `tools/`（CI 门禁与手工脚本）    |  25 |  4907 |  4.7% | 54 项检查 + 联调/出图脚本                   |
| 根目录（入口/文档/配置）           |  19 |  1825 |  1.8% | `main.py`、`core.py`、README、CI.md   |
| `resources/web/`（前端）    |  12 |  1524 |  1.5% | 网页聊天单页（原生 JS）                      |
| `plugins/`（示例与养成插件）     |  19 |  1162 |  1.1% | 插件作者参考实现                           |
| `shader/`（渲染）           |   3 |  1110 |  1.1% | OpenGL 画布 + 两种形象                   |
| `.github/`（工作流）         |   2 |   368 |  0.4% | 门禁/测试/打包发布                         |

手写 Python 约 **1.4 万行**（`stlibs` + `shader` + `plugins` + `tools` + 测试），前端约 1500 行。

## 2. 目录树与职责

```
ADPRemix/
├── main.py                    进程入口：清 RAG 缓存 → QApplication → 启动闪屏 → 延时 1s 导入 core
├── core.py                    总装线（导入即执行）：起 SDK/网页服务、选形象、建窗口、加载插件
├── requirements.txt           运行依赖（PySide6 / live2d-py / ollama / fastapi / chromadb …）
├── pyproject.toml             打包元数据 + ruff + pytest + 自研门禁 [tool.adpci] 配置
├── .github/workflows/         ci.yml（门禁/ruff/编译/测试矩阵）、release.yml（发布前门禁 + Windows 打包）
├── README.md / CI.md          功能总览与部署 / 质量门禁与「怎么测」
├── PROMPT.md                  猫娘人设提示词草稿（与 resources/prompts.json 的 general 同源）
│
├── shader/                    桌宠本体（窗口 + 渲染）
│   ├── __init__.py            OpenGL 画布基类：GLSL 3.30 程序、VAO、离屏 FBO、透明度/旋转 uniform
│   ├── live2d.py              Live2D 形象：QOpenGLWidget + live2d-py，alpha 命中检测、鼠标穿透、右键菜单
│   └── static.py              静态序列帧形象：QWidget + QPainter 逐帧绘制、帧缓存、播放器
│
├── stlibs/                    核心库（主题无关的业务与能力）
│   ├── __init__.py            配置/全局/工具：Config、ConfigLoader、SharingData、主题契约与加载、
│   │                          通知、模型刷新、插件门面、Physics 物理、Animation 动画配置、翻译
│   ├── ai/                    模型能力层
│   │   ├── __init__.py        LTMemory 长期记忆、技能解析、build_llm、chat_prompt、MultiAgentCoop、Memory
│   │   ├── local.py           本地 Ollama 后端（记忆/RAG/函数调用/协作）
│   │   ├── cloud.py           云端 OpenAI 兼容后端（流式 + 音频事件）
│   │   ├── attachment.py      附件统一表示：图片 base64、docx/文本抽正文、限额、vision 探测、两种后端消息形状
│   │   ├── fc/__init__.py     函数调用引擎：工具注册 + 多轮 tool_call 循环（流式）
│   │   ├── mcp/__init__.py    MCP 客户端管理器：单例 + 后台 asyncio 循环 + stdio 连接 + 工具注入
│   │   └── rag/               RAG 知识库
│   │       ├── __init__.py    RAG 门面：建/载索引、BM25+向量混合检索、上下文注入
│   │       ├── bm25.py        字符级 BM25 索引
│   │       ├── context.py     结果融合、上下文拼装、LLM 压缩
│   │       ├── document.py    语料读取与定长切块
│   │       ├── embeddings.py  Ollama 向量化
│   │       ├── prompts.py     导入即读 resources/prompts.json
│   │       ├── utils.py       最简日志
│   │       ├── vector.py      早期 Chroma 实现（**已无人引用，死代码**）
│   │       └── engine/        向量库抽象 + chroma / lance 两种实现 + 工厂
│   ├── themes/                主题（可插拔外观）
│   │   ├── __init__.py        主题自动发现（目录含 __init__.py 即算主题）
│   │   ├── base.py            契约抽象基类 + CombinedMeta（Qt 元类与 ABCMeta 合并）
│   │   └── hacker/            默认主题（代码雨 + 绿色终端风），见 §4.5
│   ├── graphics/              窗口装配层
│   │   ├── chat.py            聊天窗：主题 Window + 按「本地/API」分类的模型页导航
│   │   ├── settings.py        设置窗：6 个设置页（Ctrl+1..5、Ctrl+0）
│   │   └── menu.py            插件右键菜单装配：按插件分组、标题带图标、悬浮子菜单
│   ├── derfer/__init__.py     线程边界与音频：LLMAICallback(QThread) + 音频解码/播放
│   ├── mproc/onlinechat/      网页聊天服务端（FastAPI）
│   │   ├── __init__.py        路由：/api/chat、/chat/stream(SSE)、/chat/recall、/reset、/status、/getmodellist、/getmodelname、/health + 静态托管
│   │   ├── llm.py             实例池：每会话一个 LLM+记忆，LRU+TTL 回收、并发锁、流式泵
│   │   ├── registry.py        模型注册表：本地 Ollama 扫描 + 云端别名，TTL 快照 + invalidate
│   │   ├── config.py          端口/上限/附件限制/前端目录
│   │   └── __main__.py        单独起服务（不需要 Qt）
│   ├── plugins/               插件系统（宿主侧）
│   │   ├── __init__.py        对外导出
│   │   ├── api.py             插件 API 门面（日志/提示/设置/存储/菜单/命令/提示词/动作表情/主线程回调）+ hook 常量
│   │   ├── icons.py           插件图标：自定义图解码 + 字母徽章兜底（带缓存与无 GUI 守卫）
│   │   ├── manifest.py        plugin.json 解析与校验（含 icon / menu）
│   │   └── manager/           管理子包
│   │       ├── core.py        PluginManager：发现/加载/派发/卸载/事件/能力聚合/菜单分组
│   │       ├── python_plugin.py Python 入口导入 + hook 表（签名自适应）
│   │       ├── js_plugin.py   node 子进程桥（一行一个 JSON 的同步协议）
│   │       ├── runtime.js     跑在 node 里的那一半
│   │       └── panel.py       设置页「插件」的逻辑层（不依赖 Qt，可单测）
│   └── sdk/                   外部控制 SDK（UDP JSON-RPC）
│       ├── base.py            UDP 底座 + 异常 + 报文约定
│       ├── methods.py         24 个宿主能力实现（界面/聊天/配置/插件/记忆/状态）
│       ├── server.py          服务端：校验、派发、事件推送、白名单/鉴权
│       ├── client.py          Python 客户端（方法封装 + 事件订阅）
│       └── README.md          接口说明（接口地址/参数表/返回值解析）
│
├── plugins/                   插件目录（用户插件放这里）
│   ├── README.md              插件开发文档：清单字段、hook 表、API 参数表、模板、调试、安全边界
│   ├── hello_python/          示例：Python 插件（菜单/命令/回复加工/系统提示词/持久化）
│   ├── hello_javascript/      示例：JavaScript 插件（同上，跑在 node 子进程）
│   └── cultivation_system/    养成系统（从 .PluginDevOld 移植）：数值模型 + 面板 + 资源
│
├── mcp_servers/               暴露给 LLM 的 MCP 工具服务
│   ├── live2d_motion.py       stdio MCP server：列出/播放 Live2D 动作与表情（内部走 UDP SDK）
│   └── sdk/                   精简版 SDK 客户端（**与 stlibs/sdk 是两份独立实现**）
│
├── resources/                 运行时资源
│   ├── configure.json         主配置（models/memory/rag/mcp/coop/skills/plugins/形象/主题）
│   ├── prompts.json           各场景提示词（RAG 分类器、压缩、人设）
│   ├── static.json            静态形象清单：模型 → 动作 → 帧前缀
│   ├── animation/*.json       点击/抚摸部位 → 动作表情映射与开关
│   ├── character/model/<名>/  Live2D 模型（.moc3/.model3.json/physics3/pose3 + motions/ + expressions/）
│   ├── character/static/fox/  静态序列帧图片
│   ├── fonts/ icons/ locale/  等宽字体、图标、gettext 翻译
│   ├── memory/lt_memory.json  长期记忆持久化
│   ├── rag/                   知识库语料 + 向量库缓存（chroma_db/lancedb_db）
│   └── web/onlinechat/        网页聊天前端（index.html + css + 10 个 js 模块）
│
├── tools/
│   ├── ci/                    自研门禁（零第三方依赖，AST 静态分析）54 项检查
│   └── manual/                手工联调与出图：probe_*（附件/协作/养成/插件/技能/网页）、shoot_ui、
│                              make_plugin_icons（画插件图标）、strip_doc_headers
│
└── tests/                     602 个用例：单元 + 离屏 Qt + node 跑前端 js + 门禁自测
```

## 3. 启动链路

```
python main.py
├─ 读 Config.rag['clear_cache'] → 是则删 resources/rag/{chroma_db,lancedb_db} 并回写
└─ Application() → QApplication + SplashWindow(QSplashScreen 700x413)
   └─ QTimer.singleShot(1000, import core)   # 先让 Qt 跑起来再总装
      └─ core.py（模块级顺序执行，无 main()）
         1  SDKServer().start()                → UDP 127.0.0.1:9000（接收线程 + 16 线程池）
         2  SharingData.theme = load_theme(Config.theme)
         3  SharingData.sdk_server = server    # 界面/插件可推 SDK 事件
         4  按 Config.model_live2d 选 shader.live2d 或 shader.static
         5  定义 DesktopPetRemix（物理 gravity/friction + 拖动）
         6  threading.Thread(onlinechat.main)  → FastAPI http://127.0.0.1:52493
         7  theme.IconList.init()
         8  desktop.show()                     # 首次绘制时才真正初始化 GL/Live2D
         9  plugin_manager().load_all()        # 界面就绪后再加载插件
```

**线程/服务清单**：Qt 主线程（窗口 + GL + 主循环）；onlinechat 线程（uvicorn，非守护）；
SDK UDP 接收线程 + 16 工作线程；Live2D 满帧 `startTimer(0)` / 静态形象按 fps 的定时器。
桌宠与模型生成之间的唯一正规通道是 `derfer.LLMAICallback(QThread)` + Qt 信号。

## 4. 分层详解

### 4.1 入口层

| 文件                   | 职责                    | 关键点                                                                            |
|:---------------------|:----------------------|:-------------------------------------------------------------------------------|
| `main.py`            | 清 RAG 缓存、闪屏、延时导入 core | 闪屏进度条里有 5 秒阻塞 sleep（观感需要，非真实加载）                                                |
| `core.py`            | 总装线 + 桌宠窗口与物理         | **导入即执行**，没有 `main()`；启动顺序 = 语句顺序                                              |
| `stlibs/__init__.py` | 配置/全局/工具门面            | 主题必须在 `stlibs.graphics`、`shader` 之前绑定：那些模块导入期就拿 `SharingData.theme.Window` 当基类 |

`stlibs/__init__.py` 里的关键对象：

* `Config` / `ConfigLoader`：`resources/configure.json` ↔ dataclass 双向读写（CI 有 `config/schema` 检查一致性）。
* `SharingData`：全局窗口/主题/LLM 实例弱引用表/插件回调/坐标录入等运行时状态。
* `_ThemeTypingProtocol`：**主题契约的单一事实来源**（映射名 + 六个必需子模块）。
* `load_theme()`：取 `stlibs.themes.<name>`，未知或空则回退 `hacker`。
* `notify()` / `refresh_models()` / `refresh_coop()` / `emit_sdk_event()` / `plugin_*()`：给界面与插件用的横切工具。
* `Physics`：重力/摩擦/边界碰撞（core 里定时 16ms 驱动）。
* `analyze_signature()`：按目标函数签名过滤关键字参数，让界面层吸收不同主题的参数差异。

### 4.2 AI 层（`stlibs/ai/`）

**门面 `__init__.py`**

* `Memory`：短期记忆（消息列表；附件按后端形态拼 `images` 或 content 数组）。
* `LTMemory`：长期记忆。攒够 `window` 轮 → 摘要入库；召回用字符二元组 Dice 相似度 ×4 + 子串加分；
  按绝对路径共享锁、`tmp + os.replace` 原子写盘；`scope` 形如 `local:<model>` / `cloud:<model>`。
* 技能：`find_skill` / `parse_skill` / `inject_skill`（插在 system 段之后）/ `skill_prompt`。
* `build_llm()` / `chat_prompt()`：按模型名造后端并把一段问题跑成文本（SDK 的 `ask` 走这条）。
* `MultiAgentCoop`：`review`（主模型出稿 → 成员评审 → 定稿）与 `parallel`（成员并行作答 → 汇总）；
  成员实例按 `(model, prompt)` 缓存；全程串行 yield，失败降级成 `agent_error` 事件而不中断。

**后端**

| 文件         | 职责                                               | 关键点                                                                              |
|:-----------|:-------------------------------------------------|:---------------------------------------------------------------------------------|
| `local.py` | 本地 Ollama：记忆 → 技能注入 → RAG 判断/注入 → 长期记忆注入 → 函数调用流 | 模块级副作用：import 就连 MCP、读 `prompts.json`；`chat()` 产 str（文本）与 dict（工具/音频/协作事件）       |
| `cloud.py` | 云端 OpenAI 兼容：流式文本 + tool_call/audio 事件           | 无 MCP/RAG/fc；`extra_body.enable_thinking=False` 与 `modalities=[text,audio]` 是硬编码 |

**能力**

* `attachment.py`：桌面与网页共用的附件真相源 —— 限额（图 8MB / 其它 4MB / 6 个 / 正文 8000 字）、
  分类、docx 抽取、`ollama_message` 与 `openai_message` 两种形状、`can_see_images` 视觉能力探测（带缓存）。
* `fc/`：工具 schema 下发 + 多轮 tool_call 循环；`register()` 以函数名为键；`max_rounds=10`。
* `mcp/`：MCP 单例 + 后台事件循环；`connect_stdio` 连 stdio server，`inject_to_funcall` 把工具塞进函数调用。
* `rag/`：`document` 读语料切块 → `embeddings` 向量化 → `engine/{chroma,lance}` 落库 →
  `bm25` 关键词检索 → `context.merge_results` 融合 → `build_context` 或 `compress_context` 拼上下文。

### 4.3 渲染层（`shader/`）

| 维度   | Live2D（`live2d.py`）                          | 静态序列帧（`static.py`）                            |
|:-----|:---------------------------------------------|:----------------------------------------------|
| 窗口   | `QOpenGLWidget`（`ADPOpenGLCanvas`）           | 普通透明 `QWidget`（`\|Qt.Tool`）                   |
| 绘制   | 模型画进离屏 FBO → shader 贴屏（uniform 控透明度、顶点矩阵控旋转） | `QPainter.drawPixmap` 居中绘制当前帧                 |
| 驱动   | `startTimer(0)` 满帧 update+draw               | `QTimer(1000/fps)` 推帧 + `startTimer(5)` 做穿透检测 |
| 命中   | `glReadPixels` 单点 alpha                      | 等比缩放换算回图片坐标取 alpha                            |
| 鼠标穿透 | Win32 `WS_EX_TRANSPARENT` 切换                 | 同一套 ctypes 逻辑                                 |
| 右键菜单 | 设置 / 聊天 / 在线聊天 / 插件分组 / 关闭                    | 同类菜单（无「在线聊天」项）                                |

两者都会在鼠标释放（未拖动）时发 `pet_click`：插件总线 `plugin_manager().emit_event("pet_click")`
与 SDK 事件 `stlibs.emit_sdk_event(...)`。

插件菜单的装配（按插件分组、子菜单悬浮展开）抽在 `stlibs/graphics/menu.py`，两个 shader 都调它。

### 4.4 线程边界（`stlibs/derfer/`）

* `decode_audio` / `play_audio`：base64 → soundfile 波形 → sounddevice 播放。
* `LLMAICallback(QThread)`：在子线程迭代 `llm.chat(...)`，文本走 `text_chunk`、
  工具/音频/协作事件走 `tool_event`、整段回复走 `finished`；UI 只接信号。音频**不自动播**，由气泡按钮触发。

### 4.5 界面层

`stlibs/graphics/`（装配，与主题无关）：

* `chat.py`：聊天窗 = 主题 Window + 左侧「本地 / API」两分类下的模型页导航；提供 `add_model/find_model/reload_models`。
* `settings.py`：设置窗 = 6 页（常规 / LLM / 语音 / 动画 / 插件 / 设置），把子页信号中转成窗口级信号。
* `menu.py`：插件右键菜单的装配（按插件分组 → 子菜单，标题带图标；单插件单条目时平铺）+ 点击回调转发。

`stlibs/themes/hacker/`（默认主题实现，`__init__.py` 约 2900 行）：

| 文件                          | 内容                                                                                                                                                                                                                                                                                                                                                                                    |
|:----------------------------|:--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `__init__.py`               | 全部控件与契约映射：`HackerWindow`（标题栏/导航/堆叠页/快捷键）、`HackerMenu`（Qt.Popup 自绘菜单，`addMenu` 子菜单悬浮展开 + ▸ 指示）/`HackerSubMenu`（子菜单，独立工具窗不抢弹出状态）、`HackerNotify`（窗口内提示条，多级配色 + 堆叠）、`HackerSwitch`/`HackerSlider`/`HackerComboBox`/`HackerTable`/`HackerCard`/`HackerTabWidget`、`_CodeRain` 背景、`HackerChatBubble`（复制/播放/技能标签/附件）、`HackerChatWidget`（消息区 + 技能栏 + 附件栏 + 输入行）、`_ChatInputEdit`（回车发送、Ctrl+V 图片转附件）、`ModelChat`（单模型聊天页：LLM 缓存、函数线程、插件改写、技能与插件提示词合并、协作提示） |
| `llm.py`                    | LLM 设置页六 Tab：新增 LLM / 记忆（模型下拉 + JSON 视图）/ RAG / MCP / 协作 / 技能                                                                                                                                                                                                                                                                                                                         |
| `general.py`                | 常规设置：名字、形象、透明度、大小、旋转                                                                                                                                                                                                                                                                                                                                                                  |
| `animation.py`              | 动画页：Live2D 动作/表情面板、坐标录入、智能与 AI 控制开关                                                                                                                                                                                                                                                                                                                                                   |
| `settings.py`               | 设置页外壳：主题下拉（`available_themes()`）                                                                                                                                                                                                                                                                                                                                                      |
| `plugins.py`                | 插件管理页（展示层，逻辑在 `plugins/manager/panel.py`）；表格首列是插件图标                                                                                                                                                                                                                                                                                                                                   |
| `tts.py` / `recognition.py` | 语音页占位 / 空文件（未实现）                                                                                                                                                                                                                                                                                                                                                                      |

**主题契约三处必须同步**：`stlibs/__init__.py::_ThemeTypingProtocol`（类型）、
`stlibs/themes/base.py`（ABC）、`tools/ci/contract.py`（CI 侧），外加主题包尾部的映射别名。

### 4.6 网页聊天（`stlibs/mproc/onlinechat/` + `resources/web/onlinechat/`）

服务端：`APIRouter(prefix='/api')`，8 个接口（详见 `README.md` 的接口说明）。
`llm.py` 的 `WebChatPool` 给**每个网页会话**一个独立 LLM 实例与独立记忆，
换模型必重建，LRU + 空闲 TTL 回收，会话锁由专用线程持有；会话被回收后重发得到 409 而不是 502。
`registry.py` 提供模型快照（本地扫描 + 云端别名 + vision 标记），桌面端改配置后 `refresh_models()` 会让它失效重扫。

前端（原生 JS，全部挂在 `window.QW`）：

| 文件                                                                    | 职责                                                                                                               |
|:----------------------------------------------------------------------|:-----------------------------------------------------------------------------------------------------------------|
| `index.html` / `css/style.css`                                        | 单页骨架与全部样式（侧栏、气泡、附件 chip、模型下拉、移动端折叠）                                                                              |
| `js/config.js` / `js/dom.js`                                          | 常量（API 地址、缓存 TTL/上限、附件上限）与节点引用缓存                                                                                 |
| `js/api.js`                                                           | HTTP 封装：`chat` / `chatStream`（解析 SSE `data:` 帧、错误携带 partial 与 retry）/ `resetSession` / `recall` / `getModelList` |
| `js/store.js` / `js/cache.js`                                         | 对话 localStorage 持久化；答案本地缓存（(模型,问题) 为键，TTL + LRU）                                                                 |
| `js/attach.js`                                                        | 附件管线：白名单、限额、base64、缩略图、粘贴/拖拽收集、上行 payload 与历史 compact                                                            |
| `js/render.js` / `js/sidebar.js` / `js/model-picker.js` / `js/app.js` | 渲染、侧栏与移动端、模型三态下拉、主流程（建会话 → 附件 → 查缓存 → SSE → 落库）                                                                  |

### 4.7 插件系统（`stlibs/plugins/` + `plugins/`）

* 一个插件 = 一个目录 + `plugin.json` + 入口文件；Python 跑在进程内（完全信任），JavaScript 跑在 node 子进程
  （一行一个 JSON 的同步协议，`fs.readSync(0)` × 专用读线程）。
* Hook：`on_load` / `on_unload` / `on_chat_send` / `on_chat_reply` / `on_system_prompt` / `on_command` / `on_event`。
* API：日志、提示、设置、私有存储、菜单项、命令注册、系统提示词、动作表情、`send_to_chat`、`run_on_ui`。
* 图标：清单 `icon` 指插件目录内的相对路径（png/svg/jpg/webp/ico/bmp），没有或文件不在时由 `icons.py`
  按插件名生成字母/汉字徽章（颜色由 id 哈希决定，进程级缓存）；没有 QGuiApplication 时一律返回空图标
  （Qt 在这种情况下构造 `QPixmap` 会**直接终止进程**，不是抛异常）。设置页表格首列与插件菜单组标题共用它。
* 菜单：`menu_groups()` 按插件分组（标题 = 清单 `menu`，默认 `name`），`stlibs/graphics/menu.py` 把每组挂成
  一层子菜单（`HackerMenu.addMenu` + 悬浮展开）；只有"一个插件 + 一条菜单"时平铺。`menu_items()` 保留扁平结果给
  SDK/探针等老调用方。
* 宿主挂载点：`core.py`（加载）、两个 shader（右键菜单 + `pet_click`）、`ModelChat`（发送前/回复后/提示词）、网页聊天（插件提示词）。
* 隔离：单个 hook 异常只记进该插件状态并提示一次；JS 单次调用有超时；插件目录 `.data/<id>.json` 存私有数据。
* 示例与玩法见 `plugins/README.md`；养成系统是完整玩法样例（`cultivation_model.py` 纯逻辑 + `cultivation_window.py` 面板 +
  `main.py` 接线），它和扭蛋机的图标由 `tools/manual/make_plugin_icons.py` 生成。

### 4.8 SDK 与 MCP

* `stlibs/sdk/`：宿主侧 UDP JSON-RPC（默认 `127.0.0.1:9000`）。
  `methods.py` 24 个方法分六类（基础/界面/聊天/配置/插件/记忆），支持事件推送
  （`pet_click`、`chat_finished`）、方法白名单与参数校验、`ADP_SDK_TOKEN` 鉴权、老方法名别名。
  报文格式与字段表见 `stlibs/sdk/README.md`。
* `mcp_servers/live2d_motion.py`：把「列出/播放 Live2D 动作表情」暴露成 MCP 工具给模型调用；
  它用的是 `mcp_servers/sdk/` 里那份**精简版客户端**（与 `stlibs/sdk` 独立，改协议要改两处）。

### 4.9 资源（`resources/`）

主配置 `configure.json`、提示词 `prompts.json`、静态形象清单 `static.json`、
动画映射 `animation/*.json`、Live2D 模型与静态帧、字体/图标/翻译、
长期记忆 `memory/lt_memory.json`、RAG 语料与向量库缓存、网页前端。

### 4.10 工具链与测试

* `tools/ci/`：零第三方依赖的 AST 门禁，54 项检查分 8 类
  （abstract 6 / ui 14 / theme 11 / config 4 / resource 6 / web 6 / hygiene 4 / import 3），
  支持 `# ci: ignore[=id]` 内联抑制、5 种输出格式（text/json/markdown/github/sarif）。
  用法：`python -m tools.ci [检查id|分类|前缀*] [--strict] [--format …]`。
* `tools/manual/`：真机联调脚本（附件/协作/养成/插件/技能/网页聊天各一个）、
  `shoot_ui.py` 离屏出图（提示条、各设置页、右键菜单、插件子菜单、养成面板、聊天窗）、
  `make_plugin_icons.py` 用 Pillow 画插件图标、`strip_doc_headers.py` 安全清理注释（AST 定位，默认 dry-run）。
* `tests/`：602 个用例。`tests/ci/` 是门禁自身的测试；UI 类用例走离屏 Qt；
  前端 js 用例用 node 跑真实脚本（`test_web_*.py`）；`conftest.py` 统一把临时目录收敛到 `.ci-tmp/`。

### 4.11 CI/CD

`.github/workflows/ci.yml`：门禁（可上传 SARIF 到 Code Scanning）→ ruff 语法级阻断 + 完整规则报告 →
`compileall` → pytest 矩阵（多 Python 版本 + 报告上传）。
`release.yml`：发布前再跑门禁与测试，然后在 Windows 上 PyInstaller 打包产物。

## 5. 关键调用链

**桌面一次问答**

```
Chat 窗口 → ModelChat._send_message
  → 插件 chat_send（改用户输入）/ 技能解析 / 附件取出
  → derfer.LLMAICallback(QThread).run()
      → local.LLM.chat() | cloud.LLM.chat()
          → Memory 记账 → 技能注入 → RAG 判断与检索 → 长期记忆注入 → fc 工具循环（可调 MCP 工具）
      → 文本 text_chunk 信号 → 气泡逐字追加
      → 音频/工具 tool_event 信号 → 气泡挂播放按钮（不自动播）
  → finished → 插件 chat_reply（改回复）→ 插件总线与 SDK 推 chat_finished
```

**网页一次问答**

```
浏览器 → POST /api/chat(/stream)
  → 校验（模型/问题/附件）→ 取会话实例（没有就建，池满回收）
  → LLM.chat + 插件系统提示词 → SSE：start → delta* → done（或 error+retry）
  → 前端：命中本地缓存则直接展示并 POST /api/chat/recall 补记服务端记忆
```

**插件一次交互**：事件/命令/菜单 → `PluginManager` 找到插件 → 调对应 hook（异常隔离）→ 结果回界面或聊天。

**SDK 一次调用**：外部程序发 UDP 数据报 → `SDKServer._on_data` 校验（token/方法/参数）→
`HostMethods` 执行 → 回 `{"id", "result"}`；事件则反向推给订阅者。

## 6. 改动时必须同步的地方

| 改什么                    | 还要动哪                                                                                                |
|:-----------------------|:----------------------------------------------------------------------------------------------------|
| 主题映射名 / 新增主题能力         | `_ThemeTypingProtocol` + `themes/base.py` + 主题包尾别名 + `tools/ci/contract.py`                         |
| 配置项增删                  | `stlibs/__init__.py::_BaseModelConfig` + `resources/configure.json` + 设置页 UI（CI `config/schema` 会拦） |
| 网页接口 / 前端 id / JS 命名空间 | 后端路由 + `index.html` + 对应 js（CI `web/*` 六项会拦）                                                        |
| 插件 API 增删              | `stlibs/plugins/api.py` + `runtime.js`（JS 侧）+ `plugins/README.md` + 两个示例                            |
| 插件清单字段增删              | `stlibs/plugins/manifest.py` + `plugins/README.md` 的 plugin.json 段 + 设置页插件表（列宽很紧，加列要一起调）             |
| SDK 方法增删               | `stlibs/sdk/methods.py` + `METHOD_HELP` + 客户端方法 + `stlibs/sdk/README.md`（`mcp_servers/sdk` 若也要用需同步） |
| 新增资源文件                 | 放进 `resources/` 并确认代码里的路径字面量（CI `resource/missing` 会拦）                                              |

## 7. 已知问题与风险

### 7.1 已核实并已修复（本轮）

| 问题                                                                 | 影响                                                                    | 处理                                                     |
|:-------------------------------------------------------------------|:----------------------------------------------------------------------|:-------------------------------------------------------|
| `stlibs/ai/local.py::LLM.complete()` 调用不存在的 `self._call_chat(...)` | 本地模型参与协作时必然 `AttributeError` → review 模式"主模型没有给出初稿"、parallel 全员失败（静默） | 改为走与 `chat()` 同一条 `function_call.run()` 链路，且不碰记忆；补回归测试 |
| `shader/live2d.py::emit_sdk_event()` 是空实现（只剩 docstring）            | 只有 Live2D 形象时 `pet_click` 到不了 SDK 订阅者                                 | 补齐为 `stlibs.emit_sdk_event(name, data)`                |

### 7.2 已核实、尚未修

| 问题                                             | 位置                                             | 影响                                                        |
|:-----------------------------------------------|:-----------------------------------------------|:----------------------------------------------------------|
| 压缩提示词用 `.replace('text', content)` 替换裸字符串      | `stlibs/ai/rag/context.py`                     | 占位符 `{text}` 替换后残留花括号、且会污染提示词里所有含 "text" 的单词              |
| `split_text` 缺 `overlap < chunk_size` 校验       | `stlibs/ai/rag/document.py`                    | 手改配置把 overlap 调到 ≥ chunks 会死循环、切块无限膨胀（界面点不到，但配置文件可改）      |
| `Config.rag['bm25_enable']` 只写不读               | 设置页写、`stlibs/ai/rag/` 从不读                      | UI 上的 BM25 开关是死开关                                         |
| `rag/vector.py` 无人引用，与 `engine/chroma.py` 大量重复 | `stlibs/ai/rag/vector.py`                      | 改向量行为容易只改一处                                               |
| `fc.run()` 原地 append 传入的 messages              | `stlibs/ai/fc/__init__.py`                     | 工具调用过程会写进短期记忆（`local.LLM.chat` 传的正是 `memory.messages` 本体） |
| 静态形象的旋转只写进 Config 不参与绘制                        | `shader/static.py`                             | 与 Live2D 行为不一致（后者是真旋转）                                    |
| RAG 判定、向量化、压缩、MCP 调用全部同步且无超时                   | `local._need_rag`、`embeddings`、`context`、`mcp` | Ollama/MCP 挂起会卡住调用线程（桌面端即 UI 线程）                          |
| 云端 `httpx.Client` 无 timeout 且从不关闭              | `stlibs/ai/cloud.py`                           | 潜在挂死与句柄泄漏                                                 |

### 7.3 分析提出、待验证

* MCP `_run_sync` 的 `future.result()` 无超时；`__aenter__/__aexit__` 分两次提交到不同 task 可能触发 anyio cancel scope
  报错。
* RAG `build()` 先清库再逐条写入、失败不回滚；`load()` 不校验语料与 embedding 模型是否变更。
* `_inject_rag` 把知识库拼成末尾 user 消息且在内容里重复了一遍用户问题。
* 关闭 MCP 开关会连带禁用本地注册的工具（`fc._stream_once` 只在开关打开时下发 schema）。
* 静态形象与 Live2D 的右键菜单项不一致（前者缺「在线聊天」、文案硬编码中文）。
* `mcp_servers/sdk/` 与 `stlibs/sdk/` 协议漂移无人把关。

> 说明：7.3 来自静态阅读，未逐一构造用例复现；要修的话建议先各写一个失败用例再动手。
