# UI / 架构质量门禁（adpci）

`tools/ci` 是这个仓库的 CI/CD 质量门禁。它做的是**静态分析**：
只依赖 Python 标准库（`ast` / `tomllib` / `json`），
所以 CI 里不需要装 PySide6、ollama、chromadb，几秒钟就能出结果。

```
python -m tools.ci                 # 跑全部 54 项检查
python -m tools.ci --list          # 列出检查项
python -m tools.ci ui/*            # 只跑某一类
python -m tools.ci --strict        # warning 也算失败
python -m tools.ci --format sarif --output ci.sarif
python -m tools.ci --format markdown --output ci-report.md
```

退出码：`0` 通过、`1` 发现问题、`3` 检查自身崩溃（不会静默放过）。

---

## 1. 为什么需要它

### 1.1 Qt + ABCMeta 的抽象约束在运行期不生效

这是实测量出来的结论，也是 `abs/*` 这一组检查存在的根本原因：

```
纯 Python ABCMeta          → Child.__abstractmethods__ = frozenset({'foo'})，实例化 TypeError ✅
Qt 类 + CombinedMeta       → __abstractmethods__ 根本不存在，缺抽象方法照样能 new ❗
```

原因是 PySide6 的 `Shiboken.ObjectType.__new__` 在 MRO 里排在 `ABCMeta.__new__`
前面，`__abstractmethods__` 永远不会被计算出来。
`tests/test_platform_behaviour.py` 把这条行为固化成了金丝雀测试：
哪天 PySide6 改成会管了，测试会失败提醒我们重新评估。

也就是说，`stlibs/themes/base.py` 里那一堆 `*ABS` 契约、
`shader/__init__.py` 里的 `on_init/on_draw/on_resize`，
**只能靠静态检查保证**——这正是 `abs/contract`、`abs/instantiate` 在做的事。

### 1.2 主题是可插拔的，缺一个映射要等用户点到才炸

`stlibs/themes/<name>/` 每个目录都是一个完整 UI 实现，
`SharingData.theme` 指向哪个包，界面就用谁的控件。
少一个 `ChatWidget`、少一个 `general.GeneralPage`，
运行期只会 `AttributeError: module ... has no attribute ...`，
而且往往要用户点开某个设置页才暴露。

`theme/*` 这一组把「主题必须提供什么」变成可检查的契约，
契约本身来自 `stlibs/__init__.py::_ThemeTypingProtocol` 与
`stlibs/themes/base.py` 的抽象基类——**改了契约，CI 自动跟着变**。

### 1.3 UI 冲突大多是静默的

样式选择器写错类名、布局和 `setGeometry` 抢同一个控件、
信号连到参数对不上的槽……这些都不会在启动时报错。
`ui/*` 这一组把它们提前到提交阶段。

---

## 2. 检查清单

### 抽象类 / 抽象方法 `abs/*`

| id | 拦什么 |
| --- | --- |
| `abs/contract` | 抽象基类的实现类没补齐抽象成员（会被构造时算 error） |
| `abs/instantiate` | 直接构造一个还带抽象成员的类 |
| `abs/decorator-order` | `@abstractmethod` 没放在最内层，约束失效 |
| `abs/not-enforced` | 写了 `@abstractmethod` 却没有 ABCMeta 元类（`shader/__init__.py` 就踩过） |
| `abs/metaclass` | 直接混合 Qt 基类与抽象基类却没写 `metaclass=CombinedMeta` |
| `abs/signature` | 实现签名与抽象声明不兼容（多出必填参数 → error；位置参数改名 → warning） |

### UI 冲突 `ui/*`

| id | 拦什么 |
| --- | --- |
| `ui/duplicate-class` | 同一模块里同名类定义两次，后者覆盖前者 |
| `ui/object-name-collision` | 同一个 `objectName` 被多个类使用，`#id` 样式必然打架 |
| `ui/stylesheet-class` | 样式里的类选择器在项目/Qt 里都不存在（拼写错误 → 整条规则失效） |
| `ui/stylesheet-dead-id` | `#objectName` 全项目没有对应 `setObjectName`（自动跳过十六进制颜色） |
| `ui/double-parent` | 同一个控件被 `addWidget` 进两个布局 |
| `ui/layout-vs-geometry` | 控件既被布局接管又手工 `setGeometry` |
| `ui/duplicate-setlayout` | 同一分支里对一个控件调了两次 `setLayout` |
| `ui/size-constraint` | `setFixed*` 与 `setMinimum*/setMaximum*` 互相覆盖 |
| `ui/window-flags` | 互斥的窗口标志（如 `StaysOnTop` + `StaysOnBottom`） |
| `ui/signal-clash` | 信号名与同类方法/另一个信号重名 |
| `ui/signal-slot` | 信号参数比槽函数必填参数少，触发即 TypeError |
| `ui/style-overwrite` | 同一分支里重复 `setStyleSheet`，后者整体覆盖前者 |
| `ui/dead-control` | 下拉框填了数据却没有任何信号连接（点了没反应） |
| `ui/missing-super-init` | 子类收了 `parent` 却没传给 `super().__init__` |

### UI 主题类映射 `theme/*`

| id | 拦什么 |
| --- | --- |
| `theme/mapping-missing` | 主题缺少契约要求的类映射（`Window`/`Button`/`ChatWidget`/…） |
| `theme/submodule-missing` | 主题缺少必需子模块（`general`/`llm`/`tts`/`settings`/`animation`） |
| `theme/member-missing` | 映射类缺少契约成员（`Window.addNavigation`、`IconList.CHAT`…） |
| `theme/member-kind` | 抽象声明是 `property`，实现却是方法（或反过来） |
| `theme/usage-unsupported` | 代码里用到的 `SharingData.theme.X` 有主题提供不了 |
| `theme/module-member` | `theme.<子模块>.<页面>` 在该主题里不存在 |
| `theme/protocol-drift` | 代码用到的映射没写进 `_ThemeTypingProtocol`（契约漂移） |
| `theme/kind-mismatch` | 同一个映射名在不同主题里形态不一致（类 / 实例 / 函数） |
| `theme/alias-duplicate` | 两个映射名绑到同一个对象，多半是复制粘贴漏改 |
| `theme/protocol-declared` | 契约本身丢了，整套主题检查会形同虚设 |
| `theme/abc-mapping` | 契约引用的抽象基类被改名/删除 |

### 配置与资源 `config/*` `resource/*`

| id | 拦什么 |
| --- | --- |
| `config/schema` | `resources/configure.json` 与 `_BaseModelConfig` 字段对不上（多写的键保存时会被静默丢弃） |
| `config/missing-key` | 代码里 `Config.x['y']` 用到的键在 JSON 里没有（运行期 KeyError） |
| `config/animation` | `MAPPING_ANIMATION` 指向的字段在动画 JSON / dataclass 里不存在 |
| `config/prompts` | `prompts.json` 缺键 |
| `resource/missing` | 代码里写死的 `./resources/...` 路径不存在（打包后最容易出现的空白界面） |
| `resource/web-asset` | HTML/CSS 引用的静态文件不存在 |
| `resource/character` | 角色目录缺 `*.model3.json` / `*.moc3` / 版本标记文件 |
| `resource/static-model` | `static.json` 声明的帧前缀找不到对应图片 |
| `resource/json-valid` | `resources/**/*.json` 必须都能解析（多余逗号、BOM、非 UTF-8） |
| `resource/icon` | `resources/icons` 下没有代码引用的素材（info） |

### 前后端契约 `web/*`

| id | 拦什么 |
| --- | --- |
| `web/api-route` | JS 里 `post('/x')` 后端没有这个接口 |
| `web/api-port` | 前端 `API_BASE` 的端口与后端 `config.PORT` 不一致 |
| `web/config-key` | `QW.config.xxx` 没定义（`store.js` 曾因此把 localStorage 写成 `"undefined"` 键） |
| `web/dom-id` | JS 取的 DOM id 在 `index.html` 里不存在 |
| `web/namespace` | 调用了 `QW.xxx.yyy` 但没人导出 `yyy` |
| `web/script-loaded` | js 文件没被 `index.html` 引入，写了不生效 |

### 基础卫生 `hygiene/*` `import/*`

| id | 拦什么 |
| --- | --- |
| `hygiene/parse-error` | 文件读不了/语法错误 |
| `hygiene/bare-except` | 裸 `except:` 会把 `KeyboardInterrupt`/`SystemExit` 一起吞掉 |
| `hygiene/attr-typo` | 调用了与 Qt API 只差一个字母、且全项目不存在的属性（`bounds.ottom()` 就是这么抓到的） |
| `hygiene/todo` | TODO/FIXME 统计（info） |
| `import/cycle` | 模块级循环导入（函数内延迟导入不算） |
| `import/requirements` | 用到的第三方库没写进 `requirements.txt`（`PIL` 曾漏声明） |
| `import/unused-req` | `requirements.txt` 里没人用的依赖（info） |

---

## 3. 抑制误报

三层机制，从近到远：

```python
# 1) 整行忽略（所有检查）
do_something()  # ci: ignore

# 2) 只忽略指定检查
do_something()  # ci: ignore=ui/window-flags,hygiene/bare-except
```

```toml
# 3) pyproject.toml —— 全局配置（exclude 是**追加**在默认排除项之后）
[tool.adpci]
fail-on = "error"                 # error / warning / info
ignore = ["hygiene/todo"]         # 仍然运行，但结果不计入报告
disable = ["resource/icon"]       # 完全不跑
exclude = ["一些/额外/路径/*"]     # 默认排除项始终生效
allow = ["ui/stylesheet-class:QCustomThing"]   # 细粒度白名单
```

环境变量：`ADPCI_FAIL_ON=warning` 可以让 CI 变成"零 warning"模式。

---

## 4. 加一个主题要做什么

1. 建 `stlibs/themes/<name>/`，写 `__init__.py` 与
   `general.py` / `llm.py` / `tts.py` / `settings.py` / `animation.py`；
2. 在 `__init__.py` 里导出 `_ThemeTypingProtocol` 声明的全部映射；
3. 让 `Window` 继承 `MainWindowABS`、`Menu` 继承 `MenuWidgetABS`、
   `ModelChat` 继承 `ModelChatABS`、`IconList` 继承 `IconListABS`
   （Qt 子类记得 `metaclass=CombinedMeta`）；
4. `python -m tools.ci theme/* ui/* abs/*` 跑到全绿。

`stlibs/themes/__init__.py` 会自动发现新主题，
设置页的「主题」下拉框也会自动列出来（改完重启生效）。

---

## 5. 怎么测

三个层次，从快到慢：

### 5.1 门禁 + 测试套件（几秒~几十秒，CI 每次都跑）

```bash
python -m tools.ci            # 54 项静态检查，9 秒左右
python -m tools.ci ui/*       # 只跑某一类
python -m tools.ci --strict   # warning 也算失败
python -m pytest tests -q     # 153 个用例：门禁自身 + 实例隔离 + 平台金丝雀
pytest tests/ci -q            # 只测门禁框架
pytest tests/test_onlinechat.py -q   # 只测网页聊天实例池
```

单个检查/单个用例：

```bash
python -m tools.ci abs/signature --no-color     # 看某项检查的全部输出
pytest tests/ci/test_theme.py::test_missing_mapping_is_error -q
```

想验证"门禁到底管不管用"，可以在临时目录里造一份写坏的迷你仓库再跑：

```bash
python -m tools.ci --root /tmp/某个坏仓库 --no-color
```

`tests/ci/*` 里每个用例都是这么干的（`mini_repo` 夹具），
所以新增规则时照抄一个用例就能覆盖。

### 5.2 网页聊天真打接口（验证"新实例"）

网页聊天服务**不依赖 Qt、不依赖桌面端主程序**，可以单独拉起来：

```bash
# 终端 A
python -m stlibs.mproc.onlinechat          # 默认 127.0.0.1:52493

# 终端 B
python tools/manual/probe_onlinechat.py glm4:latest
```

预期输出（实测）：

```
== 用 glm4:latest 给两个不同 session 各发一条（instances_created 应 +2）==
   [manual-a] HTTP 200: '我是人工智能助手，致力于为您提供专业的信息支持和智能服务。'
   pool -> {'sessions': 1, ..., 'instances_created': 1, ...}
   [manual-b] HTTP 200: '我是一个热爱学习、乐于助人的语言模型。'
   pool -> {'sessions': 2, ..., 'instances_created': 2, ...}

== 同一个 session 再发一条（instances_created 不变、turns 递增）==
   pool -> {..., 'instances_created': 2, 'live': [..., {'session_id': 'manual-a', 'turns': 2, ...}]}

== /api/reset 丢掉 session-a（另一个 session 不受影响）==
    (200, {'dropped': 1})
   pool -> {'sessions': 1, ..., 'evicted': 1, ...}
```

三条结论一眼可见：**每会话一个独立实例**（`instances_created` 随 session 递增）、
**同会话复用实例且记忆独立**（`turns` 递增但不新建）、
**生命周期互不影响**（`/reset` 只丢弃指定 session）。

手工打单个接口（PowerShell）：

```powershell
$b = @{ model = "glm4:latest"; question = "你好"; session_id = "s1" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:52493/api/chat `
  -ContentType 'application/json' -Body $b
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:52493/api/status -ContentType 'application/json' -Body '{}'
```

调池子行为不用改代码，用环境变量就行：

```bash
WEBCHAT_MAX_SESSIONS=2 WEBCHAT_SESSION_TTL=10 python -m stlibs.mproc.onlinechat
```

### 5.3 完整程序 + 浏览器（端到端）

```bash
python main.py          # 起桌宠 + 网页聊天线程
```

然后浏览器打开 <http://127.0.0.1:52493> 聊两句，
右侧模型下拉里换一个模型再聊 —— 后台会重建实例，`/api/status` 的
`instances_created` 会 +1。

> 如果 MCP 服务起不来（比如没网、没装 npx），现在只会打印
> `[MCP] 启动 'xxx' 失败，跳过该工具`，聊天本身照常可用。

---

## 6. CI/CD 流水线

`.github/workflows/ci.yml`：

| 任务 | 内容 |
| --- | --- |
| `quality` | `python -m tools.ci`，并把结果写成 Job Summary + SARIF（Code Scanning 里能行内标注） |
| `lint` | ruff：`E9` 语法级问题阻断，完整规则先作为建议输出到 Job Summary |
| `compile` | Ubuntu + Windows × Python 3.11/3.12 全量 `compileall` |
| `tests` | pytest（门禁自身 + 网页聊天实例隔离 + 平台行为金丝雀） |
| `web` | `node --check` 所有 JS（JSON 资源由 `quality` 里的 `resource/json-valid` 负责） |
| `package` | PyInstaller 打包冒烟：确认 `resources/` 被收进产物且关键文件齐全 |

> 为什么 ruff 不一上来就全量阻断：存量代码还有一批风格债（未使用导入等），
> 全量阻断会让 CI 从第一天就红着，反而遮住真问题。
> 先把 `E9`（语法级）设为阻断，其余在 Job Summary 里持续可见，逐步清零后再收紧。

`.github/workflows/release.yml`：打 `v*` tag 时先过门禁、再跑测试、
再打包并发布 GitHub Release（产物为 `AI-Desktop-Pet-<tag>-win64.zip`）。

本地等价操作：

```bash
python -m tools.ci            # = quality
ruff check .                  # = lint
python -m pytest tests -q     # = tests
```

`pre-commit install` 之后，提交前会自动跑门禁：

```bash
pip install pre-commit
pre-commit install                        # 装 pre-commit 钩子（门禁 + ruff）
pre-commit install --hook-type pre-push   # 装 pre-push 钩子（跑 pytest）
```

> 注意第二步：`pre-push` 阶段的钩子不会随 `pre-commit install` 一起装，
> 不装的话 `adpci-tests` 永远不会执行。
>
> 另外 `.ci-tmp/` 下是测试临时目录、点开头的目录默认不扫描
> （`.venv`/`.git`/`.idea`/`.PluginDevOld` 这类本地残留）——
> 也就是说**不要把需要检查的 Python 代码放进点目录**。

---

## 7. 已知的、故意保留的提示

这几条当前以 `info` 或已修的方式存在，属于"知道但不阻塞"：

* `resource/icon`：`resources/icons` 下有 9 个素材暂时没接进界面（info）；
* `hygiene/todo`：`stlibs/ai/__init__.py` 里还有 3 处待实现（info）；
* `import/unused-req`：`requirements.txt` 里 `PySide6-Fluent-Widgets`、`pypiwin32`、
  `markdown`、`requests` 暂时没有代码引用（info）——要不要删属于产品决策，
  门禁只负责让它可见。

### 检查能力的已知边界

诚实地列出"看起来在拦、其实拦不住"的地方，避免过度信任：

* **15 个主题映射里只有 6 个有成员契约**：`Window`/`Menu`/`ModelChat`/`IconList`
  来自 `base.py` 的抽象基类，`ChatWidget`/`ChatBubble` 是显式列出的；
  其余 9 个（`Button`/`Label`/`Action`/`ScrollArea`/`TextEdit`/`LineEdit`/
  `Slider`/`ComboBox`/`CardWidget`）只校验"名字存在 + 各主题形态一致"。
  想加成员约束，就在 `tools/ci/contract.py` 的 `EXTRA_MEMBERS` 里补上调用点来源。
* **点开头的目录不扫描**（`.venv`/`.git`/`.idea`/`.PluginDevOld` 这类本地残留）。
  代价是 `.github/` 之类也在扫描范围之外——所以**不要把需要检查的代码放进点目录**。
* **`hygiene/attr-typo` 是启发式**：只在"首字母小写 + 长度 ≥5 + 与 Qt 专用名
  编辑距离 1 + 全项目没有同名定义"时才报，不做通用拼写检查。
* **样式/JS 检查基于正则**：复杂嵌套选择器、动态拼接的样式表可能漏过；
  它们的目标是挡住绝大多数手写错误，不是完整的 CSS/JS 解析器。

历史修复记录（由本门禁发现并已修）：

* `stlibs/__init__.py` `Physics.update` 里的 `bounds.ottom()` 拼写错误；
* `main.py` 里 `QPainter("./resources/icons/startup.png")`（构造函数收的是 QPaintDevice）；
* `MenuWidgetABS.addAction()` 与实现 `addAction(action)` 签名不一致；
* `MainWindowABS.addNavigation` 的位置参数名与实现不一致；
* `shader/__init__.py` 的 `@abstractmethod` 没有 ABCMeta；
* `stlibs/themes/hacker/llm.py` 里 `remove_mcp` 在未选中行时会误删最后一条 MCP；
* `requirements.txt` 漏声明 `Pillow`（`shader/static.py` 在用）；
* 设置页的「主题」下拉框填了数据却没有接任何信号（选了不生效，现在会持久化到
  `configure.json` 的 `theme` 字段，重启生效）；
* `main.py` 里 `bounds.ottom()` 式的拼写问题（`stlibs/__init__.py::Physics.update`）；
* `stlibs/themes/hacker/settings.py` 的 `available_themes()` 依赖进程工作目录（打包后失效）；
* `MenuWidgetABS.addAction()` 与实现签名不一致导致的抽象契约失效；
* 报表里 `Location(path, line, "符号")` 被当成列号（SARIF/GitHub 注解会算错位置）。
