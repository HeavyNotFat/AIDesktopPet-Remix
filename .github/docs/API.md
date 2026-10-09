# 网页聊天 HTTP 接口

服务端由 `stlibs/mproc/onlinechat/` 提供（FastAPI），地址 <http://127.0.0.1:52493>，
端口可用环境变量 `ONLINECHAT_PORT` 覆盖。请求体一律 `application/json`，
出错返回 `{"detail": "..."}`。字段与真实响应逐条核对过，可直接照着接。

## 1. 一次性问答

- **接口地址：** `POST /api/chat`
- **用途：** 问一轮，等模型把话说完再一次性返回完整回答（前端默认走流式，这个接口给脚本/第三方用）。
- **Content-Type：** `application/json`

### 请求参数

| 参数名           | 必填 | 示例值                                                           | 说明                                                        |
|:--------------|:---|:--------------------------------------------------------------|:----------------------------------------------------------|
| `model`       | 是  | `qwen3.5:4b`、`DSV4`                                           | 模型标识：本地 Ollama 模型名，或云端别名（`/api/getmodellist` 给出的 `value`） |
| `question`    | 否  | `用一句话介绍你自己`                                                   | 问题正文；为空时必须有 `attachments`                                 |
| `session_id`  | 否  | `chat-1712345678`                                             | 会话标识，同一 id 复用同一个实例与记忆；不传就是一次性会话                           |
| `attachments` | 否  | `[{"name":"cat.png","mime":"image/png","data":"iVBORw0..."}]` | 附件数组（图片 / 文本文档），`data` 是 base64；最多 6 个                    |

### 返回值解析

```json
{
  "answer": "我是一个可以陪你聊天的桌面宠物。"
}
```

| 字段路径     | 类型     | 说明                 |
|:---------|:-------|:-------------------|
| `answer` | String | 模型回答的完整文本（已去掉首尾空白） |

### 错误码

| HTTP  | 触发条件                                  |
|:------|:--------------------------------------|
| `400` | 问题与附件都为空；模型名不认识；附件解析不出来               |
| `409` | 会话已被回收（LRU / 空闲超时 / 前端删了对话）——前端重发一次即可 |
| `502` | 后端真出错了（`detail` 里带异常类型与信息）            |

## 2. 流式问答

- **接口地址：** `POST /api/chat/stream`
- **用途：** 逐字返回回答，前端「边生成边显示」走的就是它。
- **Content-Type：** `application/json`

### 请求参数

与 `POST /api/chat` 完全一致（`model` / `question` / `session_id` / `attachments`）。

### 返回值解析

响应是 `text/event-stream`，每个事件一行 `data: {json}`，共四种：

```text
data: {"type": "start", "session_id": "chat-1712345678"}
data: {"type": "delta", "text": "我"}
data: {"type": "delta", "text": "是"}
data: {"type": "done"}
```

| 字段路径         | 类型           | 说明                                                |
|:-------------|:-------------|:--------------------------------------------------|
| `type`       | String       | 事件类型：`start` 开始、`delta` 增量文本、`done` 结束、`error` 出错 |
| `session_id` | String\|Null | `start` 事件里回显的会话 id                               |
| `text`       | String       | `delta` 事件里的这一小段文本，按顺序拼接即完整回答                     |
| `detail`     | String       | `error` 事件里的错误信息                                  |
| `retry`      | Boolean      | `error` 事件里为 `true` 时表示会话被回收，前端可原样重发              |

> 客户端断开时后端会立刻停止生成并交还会话锁，已经收到的 `delta` 仍然留在前端对话里。

## 3. 补记缓存问答

- **接口地址：** `POST /api/chat/recall`
- **用途：** 前端命中本地缓存（没真调模型）时，把这一问一答补进会话记忆，保证下次上下文完整。
- **Content-Type：** `application/json`

### 请求参数

| 参数名          | 必填 | 示例值               | 说明                  |
|:-------------|:---|:------------------|:--------------------|
| `model`      | 是  | `qwen3.5:4b`      | 模型标识（决定补记到哪个实例的记忆里） |
| `question`   | 是  | `刚才那个问题`          | 当时的问题               |
| `answer`     | 是  | `当时的回答`           | 当时缓存的回答             |
| `session_id` | 否  | `chat-1712345678` | 会话标识                |

### 返回值解析

```json
{
  "recorded": true
}
```

| 字段路径       | 类型      | 说明                         |
|:-----------|:--------|:---------------------------|
| `recorded` | Boolean | 是否真的写进了记忆（会话不存在时为 `false`） |

## 4. 丢弃会话

- **接口地址：** `POST /api/reset`
- **用途：** 丢掉某个会话的 LLM 实例与记忆（前端「删除对话」时调用）。
- **Content-Type：** `application/json`

### 请求参数

| 参数名          | 必填 | 示例值               | 说明              |
|:-------------|:---|:------------------|:----------------|
| `session_id` | 否  | `chat-1712345678` | 会话标识；不传等于清掉所有会话 |

### 返回值解析

```json
{
  "dropped": 1
}
```

| 字段路径      | 类型      | 说明       |
|:----------|:--------|:---------|
| `dropped` | Integer | 实际释放的实例数 |

## 5. 实例池观测

- **接口地址：** `POST /api/status`
- **用途：** 看实例池现状：几个会话、建过多少实例、淘汰过多少（排查"串记忆/串模型"用）。
- **Content-Type：** `application/json`

### 请求参数

无。

### 返回值解析

```json
{
  "assistant": "Hiyori桃濑日和",
  "models": 4,
  "pool": {
    "sessions": 1,
    "max_sessions": 8,
    "ttl": 1800,
    "instances_created": 3,
    "evicted": 2
  }
}
```

| 字段路径                     | 类型      | 说明                                        |
|:-------------------------|:--------|:------------------------------------------|
| `assistant`              | String  | 桌宠名字（`resources/configure.json` 的 `name`） |
| `models`                 | Integer | 当前可用模型数                                   |
| `pool.sessions`          | Integer | 活着的会话数                                    |
| `pool.max_sessions`      | Integer | 会话上限（`WEBCHAT_MAX_SESSIONS`）              |
| `pool.ttl`               | Integer | 空闲回收秒数（`WEBCHAT_SESSION_TTL`）             |
| `pool.instances_created` | Integer | 累计创建过的实例数（换模型/换会话都会 +1）                   |
| `pool.evicted`           | Integer | 累计淘汰数                                     |

## 6. 可选模型列表

- **接口地址：** `POST /api/getmodellist`
- **用途：** 列出可选模型：本地 Ollama（扫描得到）+ 云端别名（配置里配的）。
- **Content-Type：** `application/json`

### 请求参数

无。

### 返回值解析

```json
{
  "models": [
    {
      "value": "qwen3.5:4b",
      "label": "qwen3.5:4b",
      "backend": "local",
      "vision": false
    },
    {
      "value": "DSV4",
      "label": "DSV4 (API)",
      "backend": "cloud"
    }
  ]
}
```

| 字段路径               | 类型      | 说明                                        |
|:-------------------|:--------|:------------------------------------------|
| `models[].value`   | String  | 传给 `/api/chat` 的 `model` 值（云端是配置里的别名）     |
| `models[].label`   | String  | 下拉框显示的名字（云端会带 `(API)` 后缀）                 |
| `models[].backend` | String  | `local`（Ollama）或 `cloud`（OpenAI 兼容）       |
| `models[].vision`  | Boolean | 只有本地模型会带：能不能看图（`false` 时前端会提示"这个模型看不见图片"） |

## 7. 桌宠名字

- **接口地址：** `POST /api/getmodelname`
- **用途：** 问宿主当前桌宠叫什么（前端标题栏、问候语用）。
- **Content-Type：** `application/json`

### 请求参数

无。

### 返回值解析

```json
{
  "name": "Hiyori桃濑日和"
}
```

| 字段路径   | 类型     | 说明                                   |
|:-------|:-------|:-------------------------------------|
| `name` | String | `resources/configure.json` 里的 `name` |

## 8. 探活

- **接口地址：** `GET /api/health`
- **用途：** 服务是否活着；也用于启动脚本轮询。
- **Content-Type：** 无（GET）

### 请求参数

无。

### 返回值解析

```json
{
  "ok": true
}
```

| 字段路径 | 类型      | 说明        |
|:-----|:--------|:----------|
| `ok` | Boolean | 固定 `true` |

前端行为：

* 逐字渲染（实测首字延迟约 0.13s），停止按钮会中断流并把已收到的部分留在对话里；
* 回答按「模型 + 问题」缓存在浏览器本地（默认 7 天 / 200 条，`CACHE_TTL`、`CACHE_MAX` 可调），
  命中时直接展示并标注「本地缓存」，侧边栏的数据库图标可一键清空；
* 对话记录存 localStorage，刷新页面继续用同一个 `session_id`。

## 实例隔离

网页聊天**不复用**桌面端聊天窗缓存的 LLM 实例
（`stlibs.themes.hacker.cache_llm_class`）。它有自己的实例池：

* 每个网页会话 id（前端把本地对话 id 当 `session_id` 传上来）一个独立实例与独立记忆；
* 换模型一定重建实例；LRU + 空闲超时回收（`WEBCHAT_MAX_SESSIONS` / `WEBCHAT_SESSION_TTL`）；
* 调用时对 `local.LLM` 显式 `should_emit=False`；`cloud.LLM` 没有这个开关，
  它的 `memory_signal` 从不连接，所以也不会碰到桌面端 Qt 界面；
* 流式生成期间会话锁由一个专用线程持有，客户端断开时自动收手并交还锁；
* 会话被回收后重发不会报 502，而是 409（`SessionClosedError`）。

细节与回归防线见 `tests/test_onlinechat.py`。
