# 功能详解

下面的内容是各功能的实现说明与操作细节，按需要跳读。

## 长期记忆

`stlibs/ai/__init__.py::LTMemory`：把对话按 `window` 轮攒起来压缩成摘要，
落盘到 `resources/memory/lt_memory.json`（运行时数据，已 gitignore），
之后按字符二元组相似度召回并注入到 system 位置。

* 开关就是设置页里的「长期存储记忆」（`Config.memory['longterm']`）——之前是个空开关；
* 默认抽取式摘要，不额外调模型；想换成模型摘要就传 `summarizer=`；
* 多个实例（多个网页会话）共享同一个文件，写入走文件锁 + 原子替换；
* 召回刻意不依赖向量库，没装 chromadb / rank_bm25 也能工作。

## 多模型协作

设置页 →「协作 设置」：

| 项 | 说明 |
| --- | --- |
| 开启多模型协作 | 总开关（`Config.coop['enable']`），改动会同步给已经建好的 LLM 实例 |
| 协作模式 | `评审改稿`（主模型出稿 → 协作模型评审 → 主模型定稿）/ `并行汇总`（各自回答 → 主模型汇总） |
| 评审轮数 | 1~3 轮 |
| 模型表 | 每行 = 模型 + 角色名 + 角色提示词，提示词留空则用默认评审提示词 |

* 实现在 `stlibs/ai/__init__.py::MultiAgentCoop`：协作成员的实例按 `(模型, 角色提示词)` 缓存复用，
  某个成员失败只记一条 `agent_error`；全部失败就退回普通回答，不会把整轮带崩；
* 成员模型既可以是 `Config.models` 里的别名（走云端），也可以是 Ollama 的模型名；
* 出稿/评审/定稿都走 `LLM.complete(messages)`（不碰短期记忆），只有最终定稿由 `LLM.chat()` 统一记账，
  所以记忆里不会出现"一问三答"；
* 过程用 `coop_signal` 抛给界面：桌面端弹提示（"小A 正在评审…"），网页端只拿最终答案。

联调（真模型，实测 12s 出稿 → 25s 评审 → 定稿）：

```bash
python tools/manual/probe_coop.py glm4:latest huihui_ai/gemma-4-abliterated:e4b
```

## 界面提示

主题提供 `Notify`（hacker 主题是**贴在窗口顶部居中的横幅**：带级别图标、彩色描边和左侧色条、
投影、从上方滑入，几条同时出现会往下叠，几秒后自己退场），
业务代码统一走 `stlibs.notify(text, level)`，`level` 取 `info` / `success` / `warning` / `error`。

* 贴哪里：先看有没有传 parent → 当前激活的窗口 → 设置窗/聊天窗/桌宠窗，都没有才退化成屏幕右下角浮层；
* 没有界面（或主题没提供 `Notify`）时自动退化成打印，所以测试里也能随便调。

已覆盖的反馈：添加/删除 API 模型、协作开关与模式切换、增删协作模型、保存协作配置、
协作每个阶段与失败原因。

排版不放心时可以离屏出图看（不需要显示器）：

```bash
python tools/manual/shoot_ui.py            # 输出到 .tmp/ui-shots/
```

## 模型列表刷新

新增 API 模型后三个地方同时跟上（入口是 `stlibs.refresh_models()`）：

* **桌面聊天窗**：重扫本地 + API 模型、重建左侧列表并自动选中新加的那个
  （`Chat.reload_models()`；分类头不会重复叠加）；
* **网页端注册表**：`registry.invalidate()`，下一次 `/api/getmodellist` 立刻重扫；
* **网页端下拉**：每次展开模型菜单都静默重拉一次，浏览器不用刷新页面。

注册表读的是**配置文件**而不是进程内存里的 `Config`，
所以网页聊天单独开进程（`python -m stlibs.mproc.onlinechat`）时也能看到桌面端刚加的模型。

## 聊天窗里的技能 / 复制 / 语音

![技能设置页](showcase/skills-page.png)

**技能（Skills）**：设置页 →「技能 Skills」里维护「技能名 / 说明 / 提示词」，
聊天窗有三种用法：

* 点输入框左边的「技能」按钮，从菜单里挑一个（菜单每次展开都重读配置）；
* 直接在输入框打 `/技能名 正文`，前缀只用来选技能，**不会发给模型**；
* 只打 `/技能名` 就是切换技能，不发送；技能会一直生效到点「×」或选「取消技能」。

选中后输入框上方显示「当前技能：xx」，用户气泡上会标出「技能 · xx」。
运行机制：技能提示词作为 **system 消息**插在原有 system 之后（`inject_skill`），
用户消息原样保留——所以记忆面板里不会混进一大段提示词，也不影响长期记忆的摘要。

**复制**：AI 回复下面一排小按钮，第一个是「复制」（复制整条回复，含流式拼起来的全文）。

**语音**：多模态模型返回音频时**不再自动播放**，而是在回复下面出现「▶ 播放」按钮，
点了才播（没声卡/解码失败会弹提示）。`derfer.LLMAICallback` 只负责把音频事件抛给界面。

```bash
python -m pytest tests/test_skills.py tests/test_chat_ui.py -q   # 技能解析 + 聊天窗交互
python tools/manual/shoot_ui.py                                  # 离屏看排版（含聊天窗）
```

## 附件：图片与文档

桌面聊天窗和网页聊天都支持，三条入口：**选文件**（「附件」按钮 / 回形针图标）、
**Ctrl+V 粘贴**、**把文件拖进来**。

| 类型 | 处理方式 | 展示 |
| --- | --- | --- |
| 图片（png/jpg/webp/gif/bmp、剪切板位图） | 走多模态：本地给 ollama 的 `images` 字段，云端给 OpenAI 的 `image_url` | 气泡里放缩略图 |
| 文本类文档（txt/md/csv/json/yaml/py…） | 抽出正文（上限 8000 字）当上下文，附在用户消息前面 | 气泡里放「文件名 · 大小 · 已读入正文」标签 |
| .docx | 装了 python-docx 就抽段落和表格 | 同上 |
| 其它二进制 | 只带文件名和大小，正文读不出来会说明 | 同上 |

* 分类、限额、正文抽取、给模型的消息形状都收在 [`stlibs/ai/attachment.py`](../../stlibs/ai/attachment.py)，
  桌面端和网页端共用一套规则（网页端统一传 base64，后端自己判断是图还是文档）；
* 一次最多 6 个、单个最大 8 MB（图片）/ 4 MB（文档），网页端后端各有一道限制
  （`MAX_ATTACHMENTS` / `WEBCHAT_MAX_ATTACHMENTS`）；
* 带附件的那一轮**不查本地回答缓存**（同样的问题配不同的图，答案不是一回事）；
* 网页端的历史记录只存缩略图和小段文本预览，避免把 localStorage 撑爆；
* 选了**纯文本模型**又发图片时，界面会直接提示"这个模型看不了图片"
  （能力来自 `ollama show` 的 capabilities，云端模型查不到就不提示）。

两个实现上的坑（都踩过并写了回归测试）：

* 桌面端 Ctrl+V 得在 `keyPressEvent` 里拦 —— `QTextEdit.paste()` 不会走
  `insertFromMimeData` 这个虚函数，图片会被当成富文本资源塞进文档，界面上什么都看不到；
* 剪切板里的图片是 **QImage** 而不是 QPixmap（只有代码里 `setImageData(QPixmap)` 才是），
  只判 QPixmap 的话真实 Ctrl+V 一张图都加不进来。

联调（确定性判据：让模型读附件里的暗号；图片只校验消息形状，
因为本机 4B 级模型的视觉能力不稳）：

```bash
python tools/manual/probe_attachment.py glm4:latest --web
```

```
== 1) 图片的消息形状 ==      字段 ['content','images','role']，base64 与原文件一致 ✓
== 2) 文档正文（桌面链路）==   回答：7391-ABCD
== 3) 网页链路 ==            回答：7391-ABCD；空问题（应被拒）：400 {"detail":"问题不能为空"}
```

## 插件（Python + JavaScript）

插件目录 `plugins/<id>/`，一个 `plugin.json` + 一个入口文件；设置页 →「插件」里启用/停用、
重载、打开目录，插件自己注册的设置页也挂在**同一个「插件」分类**下（页面标题是「插件名 · 标题」，
左边带插件图标）。完整开发文档见 [`plugins/README.md`](../../plugins/README.md)，
宿主侧代码按「作者看的 / 宿主怎么管」分层：

```
stlibs/plugins/
├── api.py        插件能用到的那套 API
├── errors.py     PluginError
├── pages.py      设置页注册表（页面规格 + 表单校验，不依赖 Qt）
├── manifest.py   plugin.json 的解析与校验
└── manager/      管插件的一切
    ├── core.py           发现 / 加载 / 派发 hook / 卸载
    ├── python_plugin.py  Python 插件导入
    ├── js_plugin.py      node 子进程桥
    ├── runtime.js        node 侧那一半
    └── panel.py          设置页背后的逻辑（不依赖 Qt，单独可测）
```

设置页有两种写法：**声明式表单**（`form=[{"type": "switch", "key": "loud", ...}]`，两种语言都能用，
宿主按当前主题渲染成开关/输入框/下拉/按钮）和 **Python 自己的 QWidget**（`builder=build_page`）。
带 `key` 的行改完直接写进 `configure.json` 的 `plugins.settings.<id>.<key>`，
每次改动回调解一次 `on_settings_action`；插件卸载或重载时页面会被摘掉，不会留下孤儿。

| | Python | JavaScript |
| --- | --- | --- |
| 运行方式 | 进程内（`importlib`） | node 子进程（stdin/stdout 一行一个 JSON） |
| 能力 | 全部 api，另可 `run_on_ui` 回主线程 | api 里的那些方法（碰不到 Qt/宿主内存） |
| 依赖 | 无 | 需要 node（可用 `ADP_NODE` 指定；没有则只标记这个插件失败） |

Hook（两种语言名字与参数一致，第一个参数是 `api`）：

| hook | 作用 |
| --- | --- |
| `on_load` / `on_unload` | 生命周期 |
| `on_chat_send` / `on_chat_reply` | 增强：改用户输入 / 改 AI 回复（多个插件按 `order` 串起来） |
| `on_system_prompt` | 增强：追加系统提示词（**本地与网页聊天都会带上**） |
| `on_menu` + `api.add_menu_item` | UI Hook：桌宠右键菜单项，点了走 `on_command` |
| `on_command` | 增强：聊天里 `/命令` |
| `on_settings_action` | UI Hook：设置页里的控件动了（`ctx` 带 `page`/`action`/`key`/`value`） |
| `on_event` | 宿主动作（`chat_finished` 等） |

api 里还有：`notify` 提示、`storage_*` 私有存储（`plugins/.data/<id>.json`）、
`add_settings_page` 系列（设置窗「插件」分类下的页面）、
`play_motion` / `play_expression` 控制 Live2D、`send_to_chat` 直接往聊天窗塞消息。

* 插件出错只影响它自己：hook 抛异常记进状态、界面提示一次，绝不影响聊天；
* JS 插件单次调用有超时（默认 3s，`plugins.timeout` 可调），卡住就停用它并写明原因；
* 安全边界：Python 插件**是进程内的，等于完全信任**；JS 插件跑在子进程、只能调 api ——
  是隔离但不是沙箱。

示例插件（`plugins/hello_python`、`plugins/hello_javascript`）演示了菜单、命令、
回复加工、系统提示词和持久化。实测：

```bash
python tools/manual/probe_plugin.py glm4:latest
```

```
== 1) 发现与加载 ==      hello_python python 已加载(in-process) / hello_javascript javascript 已加载(node)
== 2) 回复被插件加工 ==   [JS] 插件是给软件加功能的小程序。 / （来自 Python 插件）    ← 两个插件依次加工
== 3) 命令与菜单 ==       /统计 -> True ... / JS 菜单 -> ...
== 4) 系统提示词进模型 ==  回答： 【插件生效】我是一个…        ← 暗号判据，确定性
```

## 养成系统（插件示例：完整玩法）

`plugins/cultivation_system` 是从旧的 PyQt5 插件移植过来的养成玩法：
点桌宠赚金币 → 商店买吃的 → 喂食涨饥饿/好感/经验 → 升级；AI 回答也会给经验。

![养成面板](showcase/cultivation-panel.png)

* 入口：右键桌宠 →「养成系统：打开面板」，或聊天里 `/养成`；
* 命令：`/状态`、`/买 可乐`、`/喂食 汉堡`；
* 接了 7 个 hook：`on_load`（读存档 + 起定时器 + 注册设置页）、`on_unload`、`on_command`、
  `on_chat_reply`（按回答长度给奖励）、`on_event`（`pet_click` 给金币）、
  `on_system_prompt`（饿了就提醒模型"我想吃东西"）、
  `on_settings_action`（设置页里的按钮复用菜单动作）；
* 设置页：设置 →「插件」→「养成系统 · 养成设置」里可改金币上限、饥饿提醒开关，
  另有「打开养成面板」「看看当前状态」两个按钮；
* 数值逻辑在 [`cultivation_model.py`](../../plugins/cultivation_system/cultivation_model.py)，
  纯 Python 可单测；界面在 `cultivation_window.py`；`main.py` 只做 hook 装配。

```bash
python -m pytest tests/test_cultivation.py tests/test_cultivation_hooks.py -q
python tools/manual/probe_cultivation.py     # 走真实插件管理器 + 离屏 Qt 的面板检查
```

## SDK：外部程序控制桌宠

宿主启动时在 `127.0.0.1:9000` 起一个 UDP JSON-RPC 服务，24 个方法覆盖界面、聊天、配置、
插件与记忆，另有事件推送（桌宠被点、聊天结束）。文档见 [`stlibs/sdk/README.md`](../../stlibs/sdk/README.md)。

```python
from stlibs.sdk.client import SDKClient

with SDKClient("127.0.0.1", 9000) as client:
    client.notify("来自外部脚本", "success")
    client.play_live2d_motion("摸摸头", 0)
    print(client.ask("用一句话介绍你自己"))

    client.subscribe("*")                        # 事件：点了桌宠、聊天结束……
    client.on("pet_click", lambda data, msg: print("被点了", data))
```

要点：方法白名单与参数校验（错的参数会明确告诉你错哪了）、`ADP_SDK_TOKEN` 可开鉴权、
`set_config` 有白名单（`models` 里的 key 不给读改）、只监听回环地址。
一行一个 JSON 的报文格式见 SDK 文档，非 Python 语言照着接即可。

```bash
python -m pytest tests/test_sdk.py -q
```
