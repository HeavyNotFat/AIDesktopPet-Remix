# SDK（外部程序控制桌宠）

宿主启动时会在 `127.0.0.1:9000` 起一个 UDP 服务（`core.py` 里 `SDKServer().start()`），
外部脚本 / 别的语言写的工具都能通过它控制桌宠：播动作、弹提示、问模型、读改配置、管插件。

```
base.py      UDP + JSON-RPC 底座（请求 / 响应 / 事件三种报文）
methods.py   宿主能力实现（界面、聊天、配置、插件、记忆）
server.py    服务端：校验 + 派发 + 事件推送
client.py    Python 客户端：把协议包成普通方法调用
```

## Python 客户端

```python
from stlibs.sdk.client import SDKClient

with SDKClient("127.0.0.1", 9000) as client:
    print(client.ping())  # {'pong': True, 'time': ...}
    client.notify("来自外部脚本", "success")
    client.play_live2d_motion("摸摸头", 0)
    print(client.get_status())  # 主题 / 插件数 / 窗口状态 / 运行时长
    print(client.ask("用一句话介绍你自己"))  # 真跑一次模型（慢，客户端超时默认放开到 180s）

    # 事件：桌宠被点、聊天结束……
    client.subscribe("*")
    client.on("pet_click", lambda data, msg: print("被点了", data))
```

`SDKClient` 是同步接口：每个方法等到响应或超时。超时抛 `SDKTimeoutError`，
对端报错抛 `SDKRemoteError`（`exc.code` 是机器可读的原因），参数写错会直接 `TypeError`。

## 接口说明

所有方法都走同一个入口：`127.0.0.1:9000` 的 UDP 数据报，一行一个 JSON。
下面每个方法给出参数与返回值；`list_methods` 会返回同一份清单（含一行说明）。

### 1. 探活与元信息

- **接口地址：** `UDP 127.0.0.1:9000` → `ping` / `version` / `list_methods`
- **用途：** 确认服务在不在、协议版本、以及当前支持哪些方法。
- **请求参数：** 无。

#### 返回值解析

```json
{
    "id": "1",
    "result": {
        "pong": true,
        "time": 1712345678.9
    }
}
```

| 字段路径 | 类型 | 说明 |
| :--- | :--- | :--- |
| `pong` | Boolean | 固定 `true`（`ping`） |
| `time` | Float | 服务端时间戳（`ping`） |
| `protocol` | Integer | 协议版本，当前 `2`（`version`） |
| `methods[].name` | String | 方法名（`list_methods`） |
| `methods[].help` | String | 一行说明（`list_methods`） |

### 2. 宿主概况

- **接口地址：** `UDP 127.0.0.1:9000` → `get_status`
- **用途：** 主题、插件数、窗口是否打开、服务运行时长。
- **请求参数：** 无。

#### 返回值解析

```json
{
    "uptime": 128.4,
    "theme": "hacker",
    "assistant": "Hiyori桃濑日和",
    "live2d_model": "Hiyori桃濑日和",
    "chat_open": true,
    "settings_open": false,
    "plugins": {"total": 3, "loaded": 3},
    "methods": 24
}
```

| 字段路径 | 类型 | 说明 |
| :--- | :--- | :--- |
| `uptime` | Float | 服务已运行秒数 |
| `theme` | String | 当前主题包名 |
| `assistant` | String | 桌宠名字 |
| `live2d_model` / `static_model` | String | 当前 Live2D / 静态形象 |
| `chat_open` / `settings_open` | Boolean | 聊天窗 / 设置窗是否可见 |
| `plugins.total` / `plugins.loaded` | Integer | 插件总数 / 已加载数 |
| `methods` | Integer | 可调方法数量 |

### 3. 弹提示

- **接口地址：** `UDP 127.0.0.1:9000` → `notify`
- **用途：** 在桌宠界面上弹一条提示条（和程序内 `stlibs.notify` 同一条路）。
- **请求参数：**

| 参数名 | 必填 | 示例值 | 说明 |
| :--- | :--- | :--- | :--- |
| `text` | 是 | `来自外部脚本` | 提示内容 |
| `level` | 否 | `success` | `info` / `success` / `warning` / `error`，默认 `info` |
| `timeout` | 否 | `2600` | 停留毫秒数，默认 2600 |

#### 返回值解析

```json
{
    "notified": "来自外部脚本"
}
```

| 字段路径 | 类型 | 说明 |
| :--- | :--- | :--- |
| `notified` | String | 实际发出的文本 |

### 4. 播动作 / 切表情

- **接口地址：** `UDP 127.0.0.1:9000` → `play_live2d_motion` / `play_live2d_expression`
- **用途：** 让桌宠做一个动作或换一个表情（走宿主设置窗的信号，和界面按钮一致）。
- **请求参数：**

| 参数名 | 必填 | 示例值 | 说明 |
| :--- | :--- | :--- | :--- |
| `name` | 是 | `摸摸头` | 动作名 / 表情名（先用下面的列表方法查） |
| `index` | 否 | `0` | 同名动作的第几个，默认 0 |

#### 返回值解析

```json
{
    "played": "摸摸头",
    "index": 0
}
```

| 字段路径 | 类型 | 说明 |
| :--- | :--- | :--- |
| `played` | String | 实际播放的名字 |
| `index` | Integer | 实际使用的下标（仅动作） |

> 列表方法 `get_live2d_motion` / `get_live2d_expression` 无参数，返回名字数组；
> 没有数据时返回字符串 `"No Motion Data"` / `"No Expression Data"`。

### 5. 外观

- **接口地址：** `UDP 127.0.0.1:9000` → `get_appearance` / `set_appearance`
- **用途：** 读/改桌宠的尺寸、透明度、旋转角（改完会写回配置并立即生效）。
- **请求参数：**

| 参数名 | 必填 | 示例值 | 说明 |
| :--- | :--- | :--- | :--- |
| `size` | 否 | `140` | 尺寸（像素） |
| `opacity` | 否 | `80` | 透明度 |
| `rotate` | 否 | `15` | 旋转角（度） |

#### 返回值解析

```json
{
    "size": 140,
    "opacity": 80,
    "rotate": 15
}
```

| 字段路径 | 类型 | 说明 |
| :--- | :--- | :--- |
| `size` / `opacity` / `rotate` | Integer | 当前值；`set_appearance` 只返回被改到的键 |

### 6. 往聊天窗塞消息

- **接口地址：** `UDP 127.0.0.1:9000` → `send_to_chat`
- **用途：** 直接往聊天窗加一条消息，**不调模型**（做公告、外部程序回话都能用）。
- **请求参数：**

| 参数名 | 必填 | 示例值 | 说明 |
| :--- | :--- | :--- | :--- |
| `text` | 是 | `后台任务跑完了` | 消息内容 |
| `role` | 否 | `assistant` | `assistant` 显示成桌宠说的，`user` 显示成用户说的 |

#### 返回值解析

```json
{
    "sent": "后台任务跑完了",
    "role": "assistant"
}
```

| 字段路径 | 类型 | 说明 |
| :--- | :--- | :--- |
| `sent` | String | 实际写入的文本 |
| `role` | String | 实际使用的角色 |

### 7. 真问一次模型

- **接口地址：** `UDP 127.0.0.1:9000` → `ask`
- **用途：** 跑一次真实模型并等回答（慢方法，客户端超时记得调大；不碰桌面聊天窗的记忆）。
- **请求参数：**

| 参数名 | 必填 | 示例值 | 说明 |
| :--- | :--- | :--- | :--- |
| `question` | 是 | `用一句话介绍你自己` | 问题正文 |
| `model` | 否 | `qwen3.5:4b` | 模型标识；不传就用第一个可用本地模型 |
| `timeout` | 否 | `180` | 客户端等待秒数（Python 客户端参数） |

#### 返回值解析

```json
{
    "model": "qwen3.5:4b",
    "answer": "我是一个可以陪你聊天的桌面宠物。",
    "seconds": 3.215
}
```

| 字段路径 | 类型 | 说明 |
| :--- | :--- | :--- |
| `model` | String | 实际使用的模型 |
| `answer` | String | 完整回答 |
| `seconds` | Float | 本次耗时 |

### 8. 配置

- **接口地址：** `UDP 127.0.0.1:9000` → `get_config` / `set_config`
- **用途：** 读配置（整个或某个键）、改配置并落盘。
- **请求参数：**

| 参数名 | 必填 | 示例值 | 说明 |
| :--- | :--- | :--- | :--- |
| `key` | 否 | `theme` | 配置项名；`get_config` 不传就返回全部 |
| `value` | 是（set） | `hacker` | 新值；只允许改白名单里的键 |

白名单：`name`、`model_live2d`、`static_model`、`opacity`、`size`、`rotate`、`theme`、
`memory`、`rag`、`mcp`、`coop`、`skills`、`plugins`（`models` 里的 API key 不给外部读改）。

#### 返回值解析

```json
{
    "theme": "hacker"
}
```

| 字段路径 | 类型 | 说明 |
| :--- | :--- | :--- |
| `<key>` | Any | 该配置项的当前值；`set_config` 返回被改到的键 |

### 9. 插件

- **接口地址：** `UDP 127.0.0.1:9000` → `list_plugins` / `trigger_plugin_action` / `run_plugin_command`
- **用途：** 看插件状态、触发插件注册的菜单动作、跑一条插件命令。
- **请求参数：**

| 参数名 | 必填 | 示例值 | 说明 |
| :--- | :--- | :--- | :--- |
| `action` | 是（trigger） | `hello_python:greet` | 菜单项的动作名（`list_plugins` 里有） |
| `text` | 是（command） | `/统计` | 带斜杠的插件命令 |

#### 返回值解析

```json
{
    "enable": true,
    "directory": "./plugins",
    "plugins": [
        {"id": "hello_python", "name": "示例 · Python 插件", "language": "python",
         "version": "1.0.0", "enabled": true, "loaded": true, "error": "", "calls": 3}
    ],
    "problems": [],
    "commands": ["统计", "js统计"]
}
```

| 字段路径 | 类型 | 说明 |
| :--- | :--- | :--- |
| `plugins[].id` / `name` / `version` | String | 插件标识、显示名、版本 |
| `plugins[].enabled` / `loaded` | Boolean | 是否启用 / 是否加载成功 |
| `plugins[].error` | String | 加载或运行出错的原因（空串表示正常） |
| `plugins[].calls` | Integer | 被调用的次数 |
| `problems` | Array | 清单坏了、入口找不到之类的目录级问题 |
| `commands` | Array | 已注册的聊天命令名 |
| `result` | String | `trigger_plugin_action` 返回插件给出的文本 |

### 10. 记忆

- **接口地址：** `UDP 127.0.0.1:9000` → `memory_stats` / `memory_recall` / `memory_clear`
- **用途：** 看长期记忆概况、按关键词召回、清空。
- **请求参数：**

| 参数名 | 必填 | 示例值 | 说明 |
| :--- | :--- | :--- | :--- |
| `query` | 是（recall） | `我喜欢喝什么` | 召回关键词 |
| `top_k` | 否 | `3` | 返回条数，默认 3 |
| `scope` | 否 | `null` | `clear` 的范围，不传就是全部 |

#### 返回值解析

```json
{
    "instances": 2,
    "long_term": {
        "entries": 12,
        "pending": 4,
        "scopes": {"default": 12},
        "path": "resources/memory/lt_memory.json"
    }
}
```

| 字段路径 | 类型 | 说明 |
| :--- | :--- | :--- |
| `instances` | Integer | 活着的 LLM 实例数 |
| `long_term` | Object\|Null | 长期记忆概况（还没建过实例时为 `null`） |
| `long_term.entries` | Integer | 已入库的摘要条数 |
| `long_term.pending` | Integer | 攒着还没压缩的对话轮数 |
| `long_term.scopes` | Object | 各来源（session / scope）的条数 |
| `long_term.path` | String | 落盘文件路径 |
| `recall` 返回值 | Array | `memory_recall` 返回命中的摘要文本数组 |
| `removed` | Integer | `memory_clear` 删掉的条数 |

### 11. 事件推送

- **接口地址：** `UDP 127.0.0.1:9000` → 报文 `{"type": "subscribe", ...}`，服务端反向推 `{"type": "event", ...}`
- **用途：** 桌宠被点、聊天结束这类事情主动通知外部程序。
- **请求参数：**

| 参数名 | 必填 | 示例值 | 说明 |
| :--- | :--- | :--- | :--- |
| `event` | 否 | `pet_click` | 事件名；`*` 表示全部，默认 `*` |
| `action` | 否 | `subscribe` | `subscribe` 订阅 / `unsubscribe` 退订 |

#### 返回值解析

```json
{
    "type": "event",
    "name": "pet_click",
    "data": {"x": 512.0, "y": 300.5},
    "seq": 3,
    "time": 1712345678.9
}
```

| 字段路径 | 类型 | 说明 |
| :--- | :--- | :--- |
| `name` | String | 事件名：`pet_click`（点了桌宠）、`chat_finished`（一轮聊天结束） |
| `data` | Object | `pet_click` 带 `x`/`y`，`chat_finished` 带 `reply` |
| `seq` | Integer | 服务端自增序号 |
| `time` | Float | 事件时间戳 |

### 12. 别名（兼容老脚本）

- **接口地址：** `UDP 127.0.0.1:9000` → 与上面同一个方法，换个名字
- **用途：** 老脚本不用改就能继续跑。
- **映射：** `play_motion`→`play_live2d_motion`、`play_expression`→`play_live2d_expression`、
  `list_motions`→`get_live2d_motion`、`list_expressions`→`get_live2d_expression`、
  `chat`→`ask`、`status`→`get_status`、`plugins`→`list_plugins`。

## 报文格式（不用 Python 也能接）

一行一个 JSON 的 UDP 数据报，UTF-8。五种报文：

**请求**（客户端 → 服务端）

```json
{"id": "1", "method": "notify", "args": ["你好", "info", 2600], "kwargs": {}, "token": "可选"}
```

| 字段 | 类型 | 说明 |
| :--- | :--- | :--- |
| `id` | String | 请求标识，响应会原样带回（自己保证唯一） |
| `method` | String | 方法名，见上面的接口说明 |
| `args` | Array | 位置参数 |
| `kwargs` | Object | 关键字参数 |
| `token` | String | 设了 `ADP_SDK_TOKEN` 时才需要 |

**成功响应**（服务端 → 客户端）

```json
{"id": "1", "result": {"notified": "你好"}}
```

**失败响应**

```json
{"id": "1", "error": "没有这个方法：xxx（用 list_methods 看全部）", "code": "method_error"}
```

| `code` | 含义 |
| :--- | :--- |
| `method_error` | 方法名不存在，或参数个数/名字不对 |
| `unauthorized` | token 不对 |
| `bad_request` | 报文结构不对（`args` 不是数组之类） |
| `internal_error` | 方法内部抛了异常 |

**订阅 / 退订**

```json
{"id": "2", "type": "subscribe", "event": "*", "action": "subscribe"}
```

**事件推送**（服务端主动发，没有 `id`）

```json
{"type": "event", "name": "pet_click", "data": {"x": 512.0, "y": 300.5}, "seq": 3, "time": 1712345678.9}
```

## 安全

* 默认只监听 `127.0.0.1`（回环），同机进程才能访问；
* 设了环境变量 `ADP_SDK_TOKEN` 之后，请求必须带同样的 `token`，否则一律 `unauthorized`；
* `set_config` 有白名单；`ask` 会真的消耗模型资源，别在循环里狂调；
* 要跨机用，请自己套 SSH 隧道之类的加密通道，别把 9000 端口直接暴露到公网。

## 自测

```bash
python -m pytest tests/test_sdk.py -q
```

覆盖：协议校验（未知方法 / 缺参数 / 多参数 / 错参数名 / 非 JSON 报文 / token）、
每个方法在"没有界面"时的行为、事件订阅与推送、并发多个客户端、超时后不残留请求。
