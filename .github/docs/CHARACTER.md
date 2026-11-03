# 形象与动画指南

本文说明三种形象（Live2D / Emote / 静态序列帧）的加载方式、动画设置和 AI 总开关。

## 目录与配置

| 类型 | 资源目录 | 配置字段 |
|:---|:---|:---|
| Live2D | `resources/character/model/<名字>/` | `model_live2d` |
| Emote | `resources/character/emote/<名字>/` | `model_emote` |
| 静态序列帧 | `resources/character/static/<名字>/` | `static_model` |

三个字段只保留一个非空。设置窗「常规设置 → 形象」会按目录自动发现并切换；
**跨类型切换需要重启程序**，同类型换模型立即生效。

动画动作配置：

* `resources/animation/live2d.json`
* `resources/animation/emote.json`
* `resources/animation/static.json`

## 每种形象的独立配置

外观参数按类型分开存在 `resources/config/`：

| 文件 | 类型 | 默认大小 |
|:---|:---|:---|
| `live2d.json` | Live2D | 基准值 110 |
| `static.json` | 静态序列帧 | Live2D 的 70%（默认 77） |
| `emote.json` | Emote | Live2D 的 25%（默认 28） |

文件字段：`model` / `opacity` / `size` / `rotate`。切换类型时会先保存当前类型的值，
再加载目标类型的值，所以三种形象互不覆盖。

在桌宠身上按住 **Ctrl + 鼠标滚轮** 可以快速调整当前类型的大小（每格 5%），
松手后自动写回对应类型的配置文件。设置页的「大小」滑块与滚轮使用同一份数值。

## Emote

### 目录结构

```text
resources/character/emote/
├── chocola-maid/
│   ├── chocola-maid.pure.psb.zip   # 或 .psb
│   ├── config.js                   # 可选：模型自带的点击互动配置
│   └── emote.json                  # 可选：入口、缩放、偏移
└── sounds/
    └── chocola/                    # config.js 里 ./sounds/... 的全局音频目录
```

`emote.json` 示例：

```json
{
  "model": "chocola-maid.pure.psb.zip",
  "scale": 0.5,
  "offset": [0, -20]
}
```

也可以在设置窗「动画设置 → Emote 动画 → 导入 Emote 模型」直接选择
`.psb` / `.psb.zip`，程序会复制到形象目录；压缩包里的 `config.js` / `emote.json`
会自动解出来。

### 加载与交互

Emote 由 QtWebEngine + FreeMote WebGL 运行时渲染：

* 运行时文件在 `resources/emote/runtime/`（FreeMoteDriver.js / emoteplayer.js / fflate.js）；
* 支持 `.psb` 和 `.psb.zip`；
* 主时间轴、差分时间轴、变量、眼动追踪、点击动作、音效；
* 点击命中用 WebGL 画布的 alpha 检测，透明区域自动鼠标穿透；
* 右键菜单可随机动作、重载模型、打开设置；
* 拖动、Ctrl+滚轮缩放、透明度、旋转、渲染倍率都可用；
* 模型自带的 `config.js` 会按 `getConfig()` 读取
  `bust / eye / face / head / pant` 互动组，和 NekoparaDesktopPet 的格式兼容。

如果 WebEngine 的私有协议不可用，程序会自动退回本地 HTTP 服务；两种方式都失败时
会在提示条里说明原因。

> Emote 在受限启动器/沙箱里运行时，QtWebEngine 渲染进程可能被系统直接终止
> （日志：`AbnormalTerminationStatus, 18`）。`main.py` 默认给 WebEngine 追加
> `--no-sandbox`；如果不需要（例如已确定环境允许沙箱），启动前设置
> `ADP_EMOTE_KEEP_SANDBOX=1`。

### 自定义动作

「动画设置 → Emote 动画 → 自定义动作」：

1. 选一个动作（捏耳朵 / 拍拍头 / … / 程序启动 / 程序退出）；
2. 点「录入坐标」，在桌宠身上点起点、终点；
3. 从「动画」「表情（差分）」里选时间轴，点「绑定到动作」。

绑定保存在 `resources/animation/emote.json`。点击时先匹配自定义矩形，
再走模型自带的 `config.js`，都没有就随机播放一个主动画。

## Live2D 自定义动画

「动画设置 → Live2D 动画」：

* 智能控制：空闲时自动播一个动作；
* AI 控制：允许模型/插件决定动作（AI 总开关关闭时隐藏）；
* 自定义动作：选动作后「录入坐标」，在桌宠身上点两次得到矩形；
  再从动作/表情列表里选一个绑定，点「试播」可立即预览；
* 程序启动 / 程序退出：绑定一个动作，启动时自动播放、关闭前延时播放。

动作字符串使用 Live2D 的 `组名;文件名` 格式，播放时按当前模型的组内序号调用。
坐标记录的是桌宠窗口内的局部坐标，窗口移动后依然有效。

## 静态序列帧

「动画设置 → 静态动画」：

1. 选目标形象（或输入新形象名）；
2. 点「导入一组图片」，多选图片；
3. 程序按文件名自然排序（`2` 在 `10` 前面），可以「上一张 / 下一张」逐张预览，
   也可以「播放预览」；
4. 填动画名、FPS、是否循环，点「保存为动画」；
5. 之后从动画下拉框选它，点「在桌宠上播放」。

图片会复制到 `resources/character/static/<形象>/<动画>/`，
并在 `resources/static.json` 里登记显式帧列表。也支持旧的「前缀」格式
（`idle_1.png`、`idle_2.png` …）。

「点击动作」区域可以给静态形象绑定点击/悬停时播放哪一组动画。

## AI 总开关

`resources/configure.json` 的 `ai_enabled` 默认是 `false`。

关闭时：

* 隐藏设置窗里的 LLM 与语音页；
* 隐藏桌宠右键菜单的「聊天」「网页聊天」；
* 不创建聊天窗、不启动网页聊天服务；
* 不扫描 Ollama 模型、不初始化 MCP；
* SDK 的 `ask` / `send_to_chat` / 聊天记录 / 记忆方法直接返回错误；
* 插件聊天 hook 不再执行；
* 「AI 控制」开关隐藏，动画配置里的 `ai_control` 强制为 false。

开关在「设置 → 常规设置 → AI 功能总开关」。打开后网页聊天会立即启动，
LLM/语音页和聊天入口会立即出现，无需重启。
