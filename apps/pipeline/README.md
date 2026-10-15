# Babel 音频流水线

从配置的 RSS 或音视频页面抓取英文音频，转录、区分说话人、翻译，选择预设音色生成中文音频，并生成文字稿和 RSS。

- 运行环境：Ubuntu、Python 3.12、FFmpeg。环境安装和任务由根目录 Moon 管理。
- 执行：私有 `YoungY620/babel-runner` 的 GitHub Actions 与独立 systemd runner。不要把常驻 runner 注册到公共代码仓库。
- 转录证据：CPU int8 faster-whisper 保留文字、时间与说话人标签；当前云端 `gpt-transcribe` 另行转录音频块。
- 语音：OpenAI Realtime 语音模型和预设音色，按语义分块，逐块做声音质量审核，不克隆、不自动切换低质量后端。
- 文本：默认 `gpt-6-astra` 按块纠错、翻译并另发审核请求，核对专名、数字、遗漏、语义与标点。每块最多重试一次；审核失败保留上次完成产物，发布条件变为未通过。
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

## 文本与发布质量

`transcript_en.json` 保留本地转录证据。`transcript_zh.json` 同时记录经音频证据校正的英文 `text` 和中文 `text_zh`，维持原始时间与说话人对应。`.text_parts/` 保存云端转录、已审核块及内容哈希；中断后复用已通过的块。

`text-review.json` 绑定源音频、原始转录、模型、策略和双语文字稿。`web-review.json` 绑定审核后的中英标题/摘要与完整文章。文章仅分段整理完整已审核文字稿，避免再次生成时遗漏内容。

可用 `script_override.json` 提供人工精修的对齐数组，每项含 `text` 和 `text_zh`。流水线核对其完整性并用原音频证据审核。通过后保留该版本；删除覆盖文件则回到自动生成。生成的 `transcript_zh.json` 本身不是手工输入接口。

`completion.py <slug>` 是统一发布检查。转换选集、目录导出、RSS 与上传都要求文本、双语元数据和音频同时通过。模型可用性、真实音质和完整产能仍需有效云端凭据实测，离线模拟测试不能替代该验收。

模型配置：`ASR_MODEL`（默认 `gpt-transcribe`）、`TEXT_MODEL` 与 `TEXT_REVIEW_MODEL`（均默认 `gpt-6-astra`）。使用 Responses 严格 JSON schema，不保留旧翻译模型或无审核降级分支。
