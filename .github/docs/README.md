# 文档总目录

项目文档统一收在这里，代码目录里的 `README.md` 跟着代码走（不搬家）：

| 文档 | 内容 |
|:---|:---|
| [API.md](API.md) | **网页聊天 HTTP 接口**：8 个接口的地址/用途/请求参数表/返回值解析/错误码 |
| [CI.md](CI.md) | **质量门禁与「怎么测」**：57 项检查清单、测试矩阵、真机联调步骤 |
| [STRUCTURE.md](STRUCTURE.md) | **代码结构与职责地图**：每个文件干什么、启动链路、契约同步点 |
| [FEATURES.md](FEATURES.md) | **功能详解**：长期记忆、多模型协作、提示条、模型刷新、技能、附件、插件、养成、SDK |
| [PROMPT.md](PROMPT.md) | 人设提示词草稿（与 `resources/prompts.json` 的 `general` 同源） |
| [showcase/](showcase) | README 与文档里用到的界面截图 |

跟着代码走的文档：

| 文档 | 内容 |
|:---|:---|
| [../README.md](../../README.md) | 项目主页：功能总览、部署、文档索引 |
| [../plugins/README.md](../../plugins/README.md) | **插件开发**：清单字段、hook 一览、API 参数表、两种语言模板、调试技巧、安全边界 |
| [../plugins/cultivation_system/README.md](../../plugins/cultivation_system/README.md) | **养成系统**：玩法、hook 接线、与旧版差异、数值公式 |
| [../stlibs/sdk/README.md](../../stlibs/sdk/README.md) | **SDK 接口说明**：12 组方法的参数与返回值、事件推送、五种报文格式、安全说明 |

`AGENTS.md`（AI 协作者规则）留在仓库根目录，工具链按根目录约定自动读取它。

## 文档维护约定

* **新文档一律放 `docs/`**，文件名用 `大写下划线.md`（例：`PLUGIN_UI.md`），并在本文件登记一行；
* 只有**跟目录强相关**的说明才写成该目录的 `README.md`（插件目录、SDK 目录那种）；
* 文档里引用代码用相对路径（`../stlibs/plugins/api.py`），引用别的文档写成同目录文件名（`CI.md`）；
* 改契约（主题映射、插件 API、SDK 方法）时，**代码与这里列出的对应文档要一起改**，
  同步清单见 [STRUCTURE.md](STRUCTURE.md) 的「契约同步点」一节。
