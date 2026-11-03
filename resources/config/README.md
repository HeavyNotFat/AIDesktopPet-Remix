# 形象配置文件

每种形象类型有自己的外观配置，切换类型不会互相覆盖：

| 文件 | 类型 | 默认大小 |
|:---|:---|:---|
| `live2d.json` | Live2D | 基准值 110 |
| `static.json` | 静态序列帧 | Live2D 的 70%（默认 77） |
| `emote.json` | Emote | Live2D 的 25%（默认 28） |

字段：`model`（当前模型名）、`opacity`、`size`、`rotate`。

首次缺少某个文件时，`stlibs/config_profiles.py` 会按上面的比例生成默认值；
之后在桌宠上 `Ctrl + 滚轮` 调整大小会写回当前类型的文件。
主配置 `resources/configure.json` 仍保存全局设置与当前选中的类型。
