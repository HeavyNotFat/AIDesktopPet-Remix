# 插件开发

一个插件 = 插件目录下的一个文件夹，里面必须有 `plugin.json` 和入口文件。
支持 **Python**（进程内）和 **JavaScript**（node 子进程）。
设置页 →「插件」里可以启用/停用、重载、打开插件目录。

宿主侧的实现都在 `stlibs/plugins/` 下，按"作者看的"和"宿主怎么管"分成两层：

```
stlibs/plugins/
├── api.py            插件能用到的那套 API（本文件下面那张表）
├── manifest.py       plugin.json 的解析与校验
└── manager/          管插件的那一摊
    ├── core.py           PluginManager：发现 / 加载 / 派发 hook / 卸载
    ├── python_plugin.py  Python 插件的导入与 hook 表
    ├── js_plugin.py      JavaScript 插件的 node 子进程桥
    ├── runtime.js        跑在 node 里的那一半
    └── panel.py          设置页「插件」页背后的逻辑（不依赖 Qt）
```

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
  "hooks": [
    "on_chat_reply"
  ],
  // 只是声明，便于阅读；不填也能跑
  "settings": [
    // 可选：会显示在管理页/可被 api.get_setting 读取
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

| 参数名 | 必填 | 示例值 | 说明 |
| :--- | :--- | :--- | :--- |
| `msg` | 是（log） | `加载完成` | 日志内容 |
| `text` | 是（notify） | `喂我点吃的吧～` | 提示内容（会自动加 `[插件名]` 前缀） |
| `level` | 否 | `success` | `info` / `success` / `warning` / `error`，默认 `info` |
| `timeout` | 否 | `3000` | 停留毫秒数，默认 2600 |

#### 返回值解析

```python
api.log("加载完成")            # 无返回值
api.notify("喂我点吃的吧～", "success", 3000)   # 无返回值
```

### 2. 设置与存储

- **接口地址：** `api.get_setting` / `api.set_setting` / `api.storage_get` / `api.storage_set` / `api.storage_all`
- **用途：** 读 `plugin.json` 里声明的设置项；把插件自己的数据落盘（每个插件一个文件）。
- **请求参数：**

| 参数名 | 必填 | 示例值 | 说明 |
| :--- | :--- | :--- | :--- |
| `key` | 是 | `suffix` | 设置项 / 存储键名 |
| `default` | 否 | `喵` | 读不到时返回它 |
| `value` | 是（set） | `汪` | 要写的值（会做 JSON 化） |

#### 返回值解析

```python
api.get_setting("suffix", "喵")     # -> "汪"（设置页里改过的值优先）
api.storage_set("count", 3)
api.storage_get("count", 0)         # -> 3
api.storage_all()                   # -> {"count": 3, ...}
```

| 存储位置 | 说明 |
| :--- | :--- |
| `plugins/.data/<插件id>.json` | 插件私有数据，已 gitignore；设置项本身存在主配置里 |

### 3. UI Hook

- **接口地址：** `api.add_menu_item` / `api.send_to_chat` / `api.play_motion` / `api.play_expression` / `api.motions` / `api.expressions`
- **用途：** 往界面上挂东西：桌宠右键菜单项、往聊天窗塞消息、控制 Live2D 动作与表情。
- **请求参数：**

| 参数名 | 必填 | 示例值 | 说明 |
| :--- | :--- | :--- | :--- |
| `label` | 是（menu） | `打个招呼` | 菜单上显示的文字 |
| `action` | 否 | `greet` | 动作名；点了会带着它走 `on_command` |
| `text` / `role` | 是 / 否 | `后台跑完了`、`assistant` | 往聊天窗塞的内容与角色 |
| `name` / `index` | 是 / 否 | `摸摸头`、`0` | 动作或表情名（先用 `motions()` 查） |

#### 返回值解析

```python
api.add_menu_item("打个招呼", "greet")   # 无返回值
api.motions()          # -> ["摸摸头", "挥手", ...]（拿不到时是空列表）
api.expressions()      # -> ["开心", "生气", ...]
api.play_motion("摸摸头", 0)
api.send_to_chat("后台跑完了", "assistant")
```

### 4. 增强 Hook 的注册

- **接口地址：** `api.register_command` / `api.append_system_prompt` / `api.run_on_ui`
- **用途：** 注册聊天命令、往系统提示词里加一段、把回调丢回 Qt 主线程（Python 专用）。
- **请求参数：**

| 参数名 | 必填 | 示例值 | 说明 |
| :--- | :--- | :--- | :--- |
| `name` | 是（command） | `统计` | 命令名，聊天里用 `/统计` 触发 |
| `help` | 否 | `显示调用次数` | 命令说明（给用户看的） |
| `text` | 是（prompt） | `回答尽量简短。` | 追加的系统提示词（本地与网页聊天都会带上） |
| `fn` / `*args` | 是 | `self.refresh` | 要在主线程执行的函数与参数 |

#### 返回值解析

```python
api.register_command("统计", "显示调用次数")
api.append_system_prompt("回答尽量简短。")
api.run_on_ui(self.refresh)        # Python 专用：别的线程里碰 Qt 必须走它
```

## Hook 一览

两种语言的 hook 名字与参数完全一致：**第一个参数是 `api`，第二个（如果有）是事件数据**。
Python 也允许写成 `def on_load():` 这种不要参数的形式。

| hook | 何时调用 | 返回值 |
| :--- | :--- | :--- |
| `on_load(api)` | 插件加载后一次 | 无 |
| `on_unload(api)` | 卸载/停用/退出前 | 无 |
| `on_chat_send(api, ctx)` | 用户点发送后、发给模型前 | 字符串=替换用户输入；None/空=不改 |
| `on_chat_reply(api, ctx)` | 模型回复完成后 | 字符串=替换回复；None/空=不改 |
| `on_system_prompt(api)` | 每轮拼系统提示词时 | 字符串=追加一段（本地与网页聊天都会带上） |
| `on_command(api, ctx)` | 聊天里 `/命令` 或菜单项被点 | 字符串=作为回复显示 |
| `on_event(api, ctx)` | 宿主事件（`pet_click`、`chat_finished`） | 无 |

`ctx` 字段：

| hook | 字段 | 类型 | 说明 |
| :--- | :--- | :--- | :--- |
| `on_chat_send` / `on_chat_reply` | `text` | String | 当前文本（前一个插件改过的结果） |
| | `role` | String | `user` 或 `assistant` |
| | `original` | String | 插件链开始前的原文 |
| `on_command` | `name` | String | 命令名或菜单动作名 |
| | `args` | String | 命令后面的参数 |
| | `text` | String | 整条输入 |
| `on_event` | `name` | String | 事件名：`pet_click` / `chat_finished` |
| | `data` | Object | 事件数据 |

## 最小模板

**Python**

```python
def on_load(api):
    api.add_menu_item("打个招呼", "greet")
    api.register_command("统计")


def on_chat_reply(api, ctx):
    return ctx["text"] + "（来自我的插件）"


def on_command(api, ctx):
    if ctx["name"] == "greet":
        api.notify("你好！")
        return "打个招呼"
    return f"参数是 {ctx['args']}"
```

**JavaScript**

```js
module.exports = {
    on_load(api) {
        api.addMenuItem('打个招呼', 'greet');
        api.registerCommand('统计');
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
    }
};
```

## 调试

* 日志：控制台里所有插件输出都带 `[plugin:<id>]` 前缀；hook 抛异常会记在插件状态里，
  管理页的「状态」列会显示 `运行出错：…`；
* 改完代码不用重启：管理页选中该行 →「重载插件」；
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
