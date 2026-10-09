# 插件开发

一个插件 = 插件目录下的一个文件夹，里面必须有 `plugin.json` 和入口文件。
支持 **Python**（进程内）和 **JavaScript**（node 子进程）。
设置页 →「插件」里可以启用/停用、重载、打开插件目录；插件自己注册的设置页也挂在同一个
**「插件」分类**下（见下面的「设置页导航项」）。

宿主侧的实现都在 `stlibs/plugins/` 下，按"作者看的"和"宿主怎么管"分成两层：

```
stlibs/plugins/
├── api.py            插件能用到的那套 API（本文件下面那张表）
├── errors.py         PluginError（参数不对、加载失败都抛它）
├── pages.py          设置页导航项的注册表（不依赖 Qt）
├── manifest.py       plugin.json 的解析与校验
└── manager/          管插件的那一摊
    ├── core.py           PluginManager：发现 / 加载 / 派发 hook / 卸载
    ├── python_plugin.py  Python 插件的导入与 hook 表
    ├── js_plugin.py      JavaScript 插件的 node 子进程桥
    ├── runtime.js        跑在 node 里的那一半
    └── panel.py          设置页「插件」页背后的逻辑（不依赖 Qt）
```

声明式设置页由 `stlibs/graphics/plugin_page.py` 渲染成控件（用当前主题的控件类，
所以换主题时插件页跟着变）。

宿主入口是 `stlibs.plugin_manager()`；单例本体在 `stlibs.plugins.manager.core.manager`
（`stlibs.plugins.manager` 是子包，别拿它当单例用）。

## plugin.json

```json
{
  "id": "my_plugin",
  // 必填，字母数字/下划线/点/短横线，不能与别的插件重名
  "name": "我的插件",
  // 显示名
  "version": "1.0.0",
  "description": "一句话说明",
  "author": "你",
  "language": "python",
  // python | javascript
  "entry": "main.py",
  // 默认 main.py / main.js
  "order": 100,
  // 小的先执行（hook 按这个顺序串）
  "icon": "icon.png",
  // 可选：插件图标，插件目录内的相对路径（png/svg/jpg/webp/ico/bmp）
  // 不写或文件不在，就按插件名生成一枚字母徽章兜底
  "menu": "我的插件",
  // 可选：右键菜单里这一组的标题，默认取 name
  "hooks": [
    "on_chat_reply"
  ],
  // 只是声明，便于阅读；不填也能跑
  "settings": [
    // 可选：api.get_setting 读它；add_settings_page 不写 form 时按它自动生成设置页
    {
      "key": "suffix",
      "label": "后缀",
      "type": "text",
      "default": "喵"
    }
  ]
}
```

## 接口说明

Python 与 JavaScript **同名同义**（JS 用驼峰：`storage_get` ↔ `storageGet`）。
`api` 是插件唯一能碰到的宿主入口，下面按用途分组。

### 1. 日志与提示

- **接口地址：** `api.log(msg)` / `api.notify(text, level, timeout)`
- **用途：** 打日志（控制台里带 `[plugin:<id>]` 前缀）、在界面上弹一条提示条。
- **请求参数：**

| 参数名       | 必填        | 示例值       | 说明                                                 |
|:----------|:----------|:----------|:---------------------------------------------------|
| `msg`     | 是（log）    | `加载完成`    | 日志内容                                               |
| `text`    | 是（notify） | `喂我点吃的吧～` | 提示内容（会自动加 `[插件名]` 前缀）                              |
| `level`   | 否         | `success` | `info` / `success` / `warning` / `error`，默认 `info` |
| `timeout` | 否         | `3000`    | 停留毫秒数，默认 2600                                      |

#### 返回值解析

```python
api.log("加载完成")  # 无返回值
api.notify("喂我点吃的吧～", "success", 3000)  # 无返回值
```

### 2. 设置与存储

- **接口地址：** `api.get_setting` / `api.set_setting` / `api.storage_get` / `api.storage_set` / `api.storage_all`
- **用途：** 读 `plugin.json` 里声明的设置项；把插件自己的数据落盘（每个插件一个文件）。
- **请求参数：**

| 参数名       | 必填     | 示例值      | 说明              |
|:----------|:-------|:---------|:----------------|
| `key`     | 是      | `suffix` | 设置项 / 存储键名      |
| `default` | 否      | `喵`      | 读不到时返回它         |
| `value`   | 是（set） | `汪`      | 要写的值（会做 JSON 化） |

#### 返回值解析

```python
api.get_setting("suffix", "喵")  # -> "汪"（设置页里改过的值优先）
api.storage_set("count", 3)
api.storage_get("count", 0)  # -> 3
api.storage_all()  # -> {"count": 3, ...}
```

| 存储位置                        | 说明                             |
|:----------------------------|:-------------------------------|
| `plugins/.data/<插件id>.json` | 插件私有数据，已 gitignore；设置项本身存在主配置里 |

### 3. UI Hook

- **接口地址：** `api.add_menu_item` / `api.send_to_chat` / `api.play_motion` / `api.play_expression` / `api.motions` /
  `api.expressions`
- **用途：** 往界面上挂东西：桌宠右键菜单项、往聊天窗塞消息、控制 Live2D 动作与表情。
- **请求参数：**

| 参数名              | 必填      | 示例值                 | 说明                       |
|:-----------------|:--------|:--------------------|:-------------------------|
| `label`          | 是（menu） | `打个招呼`              | 菜单上显示的文字                 |
| `action`         | 否       | `greet`             | 动作名；点了会带着它走 `on_command` |
| `text` / `role`  | 是 / 否   | `后台跑完了`、`assistant` | 往聊天窗塞的内容与角色              |
| `name` / `index` | 是 / 否   | `摸摸头`、`0`           | 动作或表情名（先用 `motions()` 查） |

注册的菜单项会**一层平铺**在右键菜单上（不套子菜单）：

* 条目文字 = 「插件名 · 菜单名」，插件名取清单里的 `menu`（没写就是 `name`）；
  菜单名里已经能看出插件名时（`养成系统：打开面板` 配插件名 `养成系统`）就不重复前缀；
* 每条左边带**这个插件自己的图标**，所以一眼能看出哪条是谁加的；
* 顺序 = 插件加载顺序（`order` 小的在前）× 组内注册顺序。

一个插件注册多条时就是往下排：

```python
# 右键菜单里长这样：
#   养成系统 · 打开面板
#   养成系统 · 喂食
#   养成系统 · 商店
api.add_menu_item("打开面板", "panel")
api.add_menu_item("喂食", "feed")
api.add_menu_item("商店", "shop")
```

#### 返回值解析

```python
api.add_menu_item("打个招呼", "greet")  # 无返回值
api.motions()  # -> ["摸摸头", "挥手", ...]（拿不到时是空列表）
api.expressions()  # -> ["开心", "生气", ...]
api.play_motion("摸摸头", 0)
api.send_to_chat("后台跑完了", "assistant")
```

### 4. 设置页导航项

- **接口地址：** `api.add_settings_page` / `api.remove_settings_page` / `api.settings_pages` /
  `api.refresh_settings_page`
- **用途：** 在**设置窗 →「插件」分类**下加一页自己的界面（改参数、按按钮）。挂载、排序、卸载
  都由宿主负责：插件不用碰分类、不用自己开窗口；插件被停用/重载时它的页面会自动摘掉。
- **请求参数：**

| 参数名       | 必填 | 示例值                         | 说明                                |
|:----------|:---|:----------------------------|:----------------------------------|
| `title`   | 是  | `养成设置`                      | 导航项文字（显示成「插件名 · 标题」）              |
| `form`    | 否  | `[{"type": "switch", ...}]` | 声明式表单，两种语言都能用（见下张表）               |
| `builder` | 否  | `build_page`                | **Python 专用**：调用后返回 `QWidget` 的函数 |
| `key`     | 否  | `settings`                  | 页面标识；同一个插件里重名＝覆盖旧页                |
| `order`   | 否  | `100`                       | 同一插件内多页的排序，小的在前                   |
| `hint`    | 否  | `改完立刻生效`                    | 页面顶部的一行说明                         |

`form` 与 `builder` 都不给时，宿主按 `plugin.json` 里声明的 `settings` 自动生成表单。

页面可以**随时重新注册**（同 key 覆盖）：插件拿到新数据后再调一次 `add_settings_page`，宿主会重建这一页，
状态映射、下拉项、进度都能这么刷。重建不会把你踢到别的页面，也不会打乱「插件」分类里的顺序。

#### 表单行（`form` 的每一项）

| `type`           | 必填字段            | 说明                                                                   |
|:-----------------|:----------------|:---------------------------------------------------------------------|
| `text`           | `key`           | 单行输入框                                                                |
| `password`       | `key`           | 密码输入框（值按**明文**存在 `configure.json` 里）                                 |
| `number`         | `key`           | 数字输入框，可给 `min` / `max`，超出会夹回来                                        |
| `switch`         | `key`           | 开关                                                                   |
| `select`         | `key`、`options` | 下拉框；`options` 支持 `"文本"` / `["值", "文本"]` / `{"value": …, "label": …}` |
| `button`         | `action`        | 按钮，点了触发 `on_settings_action`                                         |
| `label` / `hint` | `text`          | 一行正文 / 一行灰色说明                                                        |
| `section`        | `rows`          | 一块**栅格卡片**：把若干行按 `columns` 分列摆（见下）                                   |
| `map`            | `items`         | 一组**「名称 → 值」只读展示**，用来显示状态（见下）                                        |

公共字段：`label`（卡片标题）、`hint`（卡片下的说明）、`default`（没存过设置时的初始值）、
`placeholder`（输入框占位符）、`span`（在 `section` 里跨几列）。单页最多 64 行、每行最多 64 个下拉项，
看不懂的行会被跳过。

#### 分区与栅格（`section` / `columns` / `span`）

不想让所有控件一路竖着排，就把它们收进 `section`：`columns` 给 1–4 列（默认 1，超出会夹回来），
子行的 `span` 决定跨几列（默认 1；`label` / `hint` / `map` 默认整行）。

```python
api.add_settings_page("我的设置", key="settings", form=[
    {"type": "section", "title": "连接", "columns": 2, "hint": "两列排开", "rows": [
        {"type": "text", "key": "server_url", "label": "服务器", "span": 2},  # 整行
        {"type": "number", "key": "threads", "label": "线程数"},  # 左列
        {"type": "number", "key": "timeout", "label": "超时"},  # 右列
        {"type": "button", "action": "ping", "text": "测试连接"},  # 两个按钮并排
        {"type": "button", "action": "reset", "text": "恢复默认"},
    ]},
])
```

子行里**不允许再嵌 `section`**（会被跳过）；一块 `section` 最多 32 个子行。老写法（直接一串行）
照旧能用，两种可以混着写。

#### 状态映射（`map`）

要显示「当前状态」这类只读信息时，用 `map` 比堆一行行 `label` 整齐：`items` 支持
`{"名称": 值}` / `[["名称", 值]]` / `[{"key": …}]` 三种写法，值不是字符串也行（数字、布尔、列表、字典
都会被转成人能看的样子，空值显示成 `—`）。插件每次重建页面就能刷新它，所以「任务进度」也能这么做。

```python
api.add_settings_page("状态", key="status", form=[
    {"type": "map", "title": "当前状态", "items": {
        "素材站": api.get_setting("server_url", "未配置"),
        "账号": api.storage_get("username", None),
        "进度": "3 / 10",
    }},
])
```

#### 值怎么存、怎么回传

* 带 `key` 的行改完会**立刻写进** `resources/configure.json` 的 `plugins.settings.<插件id>.<key>`，
  插件侧用 `api.get_setting(key, 默认值)` 直接读，不用自己存；
* 每次改动都会调一次插件的 `on_settings_action(api, ctx)`：

| `ctx` 字段 | 类型     | 说明                          |
|:---------|:-------|:----------------------------|
| `page`   | String | 页面 key                      |
| `action` | String | 这一行的 `action`（没写就是行的 `key`） |
| `key`    | String | 改动对应的设置名；按钮是空串              |
| `value`  | Any    | 新值；按钮是 `null`               |

回调里返回字符串会弹一条提示条；想让页面重新读一遍值，调 `api.refresh_settings_page(key)`。

#### 返回值解析

```python
api.add_settings_page(...)  # -> "settings"（页面 key，之后用它刷新/摘除）
api.settings_pages()  # -> [{"key": "settings", "title": "养成设置", "form": [...]}]
api.refresh_settings_page()  # -> 被重建的页数
api.remove_settings_page()  # -> 被摘掉的页数（不传 key 就是全部）
```

JavaScript 同名同义（驼峰）：`api.addSettingsPage(title, form, key, order)`、
`api.removeSettingsPage(key)`、`api.settingsPages()`、`api.refreshSettingsPage(key)`。

**Python：声明式表单 + 按钮**

```python
def on_load(api):
    api.add_settings_page("养成设置", key="settings", hint="改完立刻生效", form=[
        {"type": "number", "key": "click_coin", "label": "点一下最多给几枚金币", "default": 5, "min": 1, "max": 50},
        {"type": "switch", "key": "mood_prompt", "label": "饿了时提醒 AI", "default": True},
        {"type": "button", "action": "open", "label": "打开面板"},
    ])


def on_settings_action(api, ctx):
    if ctx["action"] == "open":
        api.notify("面板打开了")
        return "面板打开了"
```

**Python：自己画界面（builder）**

```python
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


def build_page(parent=None):
    page = QWidget(parent)
    QVBoxLayout(page).addWidget(QLabel("这里想怎么画就怎么画"))
    return page


def on_load(api):
    api.add_settings_page("我的界面", builder=build_page, key="custom")
```

**JavaScript：只能声明式表单**

```js
module.exports = {
    on_load(api) {
        api.addSettingsPage('我的设置', [
            {
                type: 'section', title: '连接', columns: 2, rows: [
                    {type: 'text', key: 'suffix', label: '后缀', default: '喵', span: 2},
                    {type: 'number', key: 'threads', label: '线程数'},
                    {type: 'button', action: 'hello', text: '打个招呼'}
                ]
            },
            {type: 'map', title: '状态', items: {账号: null, 进度: '3 / 10'}}
        ], 'settings');
    },
    on_settings_action(api, ctx) {
        if (ctx.action === 'hello') return '你好！';
        return null;
    }
};
```

### 5. 增强 Hook 的注册

- **接口地址：** `api.register_command` / `api.append_system_prompt` / `api.run_on_ui`
- **用途：** 注册聊天命令、往系统提示词里加一段、把回调丢回 Qt 主线程（Python 专用）。
- **请求参数：**

| 参数名            | 必填         | 示例值            | 说明                    |
|:---------------|:-----------|:---------------|:----------------------|
| `name`         | 是（command） | `统计`           | 命令名，聊天里用 `/统计` 触发     |
| `help`         | 否          | `显示调用次数`       | 命令说明（给用户看的）           |
| `text`         | 是（prompt）  | `回答尽量简短。`      | 追加的系统提示词（本地与网页聊天都会带上） |
| `fn` / `*args` | 是          | `self.refresh` | 要在主线程执行的函数与参数         |

#### 返回值解析

```python
api.register_command("统计", "显示调用次数")
api.append_system_prompt("回答尽量简短。")
api.run_on_ui(self.refresh)  # Python 专用：别的线程里碰 Qt 必须走它
```

## Hook 一览

两种语言的 hook 名字与参数完全一致：**第一个参数是 `api`，第二个（如果有）是事件数据**。
Python 也允许写成 `def on_load():` 这种不要参数的形式。

| hook                           | 何时调用                              | 返回值                   |
|:-------------------------------|:----------------------------------|:----------------------|
| `on_load(api)`                 | 插件加载后一次                           | 无                     |
| `on_unload(api)`               | 卸载/停用/退出前                         | 无                     |
| `on_chat_send(api, ctx)`       | 用户点发送后、发给模型前                      | 字符串=替换用户输入；None/空=不改  |
| `on_chat_reply(api, ctx)`      | 模型回复完成后                           | 字符串=替换回复；None/空=不改    |
| `on_system_prompt(api)`        | 每轮拼系统提示词时                         | 字符串=追加一段（本地与网页聊天都会带上） |
| `on_command(api, ctx)`         | 聊天里 `/命令` 或菜单项被点                  | 字符串=作为回复显示            |
| `on_settings_action(api, ctx)` | 设置页里的控件动了                         | 字符串=弹一条提示条            |
| `on_event(api, ctx)`           | 宿主事件（`pet_click`、`chat_finished`） | 无                     |

`ctx` 字段：

| hook                             | 字段         | 类型     | 说明                                |
|:---------------------------------|:-----------|:-------|:----------------------------------|
| `on_chat_send` / `on_chat_reply` | `text`     | String | 当前文本（前一个插件改过的结果）                  |
|                                  | `role`     | String | `user` 或 `assistant`              |
|                                  | `original` | String | 插件链开始前的原文                         |
| `on_command`                     | `name`     | String | 命令名或菜单动作名                         |
|                                  | `args`     | String | 命令后面的参数                           |
|                                  | `text`     | String | 整条输入                              |
| `on_event`                       | `name`     | String | 事件名：`pet_click` / `chat_finished` |
|                                  | `data`     | Object | 事件数据                              |
| `on_settings_action`             | `page`     | String | 页面 key（`add_settings_page` 的返回值）  |
|                                  | `action`   | String | 行的 `action`（没写就是行的 `key`）         |
|                                  | `key`      | String | 改动对应的设置名；按钮是空串                    |
|                                  | `value`    | Any    | 新值；按钮是 `null`                     |

## 最小模板

**Python**

```python
def on_load(api):
    api.add_menu_item("打个招呼", "greet")
    api.register_command("统计")
    # 设置窗「插件 → 我的插件 · 打个招呼设置」里的一页
    api.add_settings_page("打个招呼设置", form=[
        {"type": "text", "key": "suffix", "label": "后缀", "default": "喵"},
    ])


def on_chat_reply(api, ctx):
    return ctx["text"] + "（来自我的插件）"


def on_command(api, ctx):
    if ctx["name"] == "greet":
        api.notify("你好！")
        return "打个招呼"
    return f"参数是 {ctx['args']}"


def on_settings_action(api, ctx):
    return f"{ctx['key']} 改成了 {ctx['value']}"
```

**JavaScript**

```js
module.exports = {
    on_load(api) {
        api.addMenuItem('打个招呼', 'greet');
        api.registerCommand('统计');
        api.addSettingsPage('打个招呼设置', [
            {type: 'text', key: 'suffix', label: '后缀', default: '喵'}
        ], 'greet-settings');
    },
    on_chat_reply(api, ctx) {
        return ctx.text + '（来自我的插件）';
    },
    on_command(api, ctx) {
        if (ctx.name === 'greet') {
            api.notify('你好！');
            return '打个招呼';
        }
        return '参数是 ' + ctx.args;
    },
    on_settings_action(api, ctx) {
        return ctx.key + ' 改成了 ' + ctx.value;
    }
};
```

## 调试

* 日志：控制台里所有插件输出都带 `[plugin:<id>]` 前缀；hook 抛异常会记在插件状态里，
  管理页的「状态」列会显示 `运行出错：…`；
* 改完代码不用重启：管理页选中该行 →「重载插件」；重载会把它的设置页摘掉再加回来，
  设置页里的值存在 `configure.json` 里，不会跟着丢；
* 设置页排错：页面挂不上先看「插件」分类里有没有这一项（页面标题是「插件名 · 标题」），
  声明式表单写错行会被静默跳过，`builder` 抛异常会显示成一张写着原因的页面；
* JavaScript 插件需要 node（`ADP_NODE` 环境变量可以指定路径）；找不到 node 时它会显示加载失败，
  不影响 Python 插件；
* 单个 hook 卡住会被超时掐掉（默认 3 秒，`configure.json` 的 `plugins.timeout` 可调），
  之后这个插件进程会被停用并在状态里写明原因。

### 两个容易踩的坑

1. **入口文件不能用相对导入**。插件是按文件路径加载的（不是包），
   `from .helper import x` 会报 `attempted relative import with no known parent package`；
   请用绝对导入：`from helper import x`（插件加载期间到卸载之前，插件目录一直在 `sys.path` 里，
   所以放在函数里**懒加载**也没问题）。
2. **插件内部的模块名要起得独特**。`sys.path` 是全局的，两个插件都叫 `helper.py` / `model.py`
   时，第二个插件会 import 到第一个的模块；建议加前缀，比如 `cultivation_model.py`。

## 安全边界（说清楚，别误解）

* **Python 插件是进程内的**：它和宿主同一个进程、同一份权限，能读写你的文件。
  只装你自己信任的插件。
* **JavaScript 插件跑在 node 子进程里**：它只能调用上表里那些 api 方法，
  碰不到 Qt、碰不到宿主内存 —— 这是隔离，但不是沙箱（node 本身没有沙箱）。
* 插件只能写自己的存储文件（`plugins/.data/<id>.json`），但 Python 插件理论上不受这个限制。
