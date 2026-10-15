# Babel 音频流水线

从配置的 RSS 或音视频页面抓取英文音频，转录、区分说话人、翻译，选择预设音色生成中文音频，并生成文字稿和 RSS。

- 运行环境：Ubuntu、Python 3.12、FFmpeg。环境安装和任务由根目录 Moon 管理。
- 执行：私有 `YoungY620/babel-runner` 的 GitHub Actions 与独立 systemd runner。不要把常驻 runner 注册到公共代码仓库。
- 当前转录：CPU int8 faster-whisper，独立切片与续跑检查点；模型质量升级见实施计划。
- 语音：OpenAI 受测 TTS 快照和预设音色，按语义分块，逐块做声音质量审核，不克隆、不自动切换低质量后端。
- 产物：`zh.mp3`、`speech.json`、译文与文章。`speech.json` 记录基于生成音频的时间轴、内容指纹、响度与峰值；源转录时间轴不能直接用作中文音频字幕。
- 分发：公共 GitHub Releases 音频和 Pages/RSS。云端模型调用产生费用。

## 操作

在仓库根目录：

```bash
pnpm install
pnpm moon run pipeline:setup
pnpm moon run pipeline:check pipeline:test
```

在 `apps/pipeline` 下：

```bash
.venv/bin/python pipeline/fetch.py --list --show acquired
.venv/bin/python pipeline/convert.py --index 0 --show acquired
.venv/bin/python pipeline/convert.py --slug <slug>
.venv/bin/python pipeline/tts.py <slug> --voice cedar
```

语音选择、审核和翻译需要 `OPENAI_API_KEY`。配置与部署说明以根目录 [README](../../README.md) 和 [部署指南](../../deploy/README.md) 为准。
新模型需先运行原创样品评估，再启用到定时转换。产能数据必须包含完整流水线耗时、中文产出音频时长和完成集数。
