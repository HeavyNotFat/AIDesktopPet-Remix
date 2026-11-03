# 敏感配置（.env）

API Key 等敏感数据不再写进 `resources/configure.json`，而是放在仓库根目录的
`.env/` 目录里；整个目录被 `.gitignore` 忽略，首次保存时程序会自动创建。

## 文件格式

默认文件：`.env/secrets.json`

```json
{
  "models": {
    "DeepseekV4F": "sk-你的key",
    "另一个别名": "sk-..."
  }
}
```

模型别名必须与 `resources/configure.json` 里 `models` 的键一致。程序启动时
`ConfigLoader.load_config()` 会把 key 合并进内存里的 `Config.models`，运行时
云端后端能正常取到；写回配置时只写别名、模型名、Base URL，不会把 key 写进
`configure.json`。

## 环境变量

也可以不落盘，用环境变量：

```text
ADP_API_KEY_<别名>
```

别名转大写、非字母数字换成下划线，例如 `DeepseekV4F` → `ADP_API_KEY_DEEPSEEKV4F`。
环境变量的优先级低于 `.env`（`.env` 有值就用 `.env`）。

## 设置页

设置页「LLM → 新增 LLM」保存时，`ConfigLoader.save_config()` 会：

1. 把当前 `Config.models` 里的 key 同步到 `.env/secrets.json`；
2. 从写出的 `configure.json` 里删除 `apikey` / `api_key`；
3. 删除模型配置时同步删除对应密钥。

如果 `.env` 不可写，保存会在控制台报错，本次**不会**把 key 写回 `configure.json`；
请检查目录权限后重新填写即可。

## 安全边界

* SDK 的 `get_config("models")` 返回脱敏后的模型表，不暴露 key；
* `config.js` / 插件仍可能读进程内 `Config.models`，不要加载不可信插件；
* 旧的 `configure.json` 若还带着 key，下一次保存会自动迁移到 `.env` 并从配置里删掉。
