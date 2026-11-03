# Emote 运行时

本目录放 Emote（E-mote / FreeMote）的 WebGL 运行时和说明。

```text
runtime/
├── index.html         页面骨架（服务器/私有协议会注入 window.EMOTE_CONFIG）
├── fflate.js          解压 .psb.zip（MIT）
├── FreeMoteDriver.js  FreeMote SDK v3.9（LGPLv3 源码 / CC BY-NC-SA 4.0 二进制）
├── emoteplayer.js     EmotePlayer 设备与播放器封装
└── LICENSE.txt        第三方许可见上
```

模型放在 `resources/character/emote/<名字>/`：

```text
resources/character/emote/chocola-maid/
├── chocola-maid.pure.psb.zip
├── config.js         可选，模型自带的点击互动（getConfig() 返回 bust/eye/face/head/pant）
└── emote.json        可选，指定入口与缩放：{"model": "...", "scale": 0.5, "offset": [0, -20]}
```

也可以在设置窗「动画设置 → Emote 动画 → 导入 Emote 模型」直接导入。

音频按 `config.js` 里的相对路径查找：先找模型目录下的同名文件，再找
`resources/character/emote/sounds/`。

完整说明见 [形象指南](../../.github/docs/CHARACTER.md#emote)。
