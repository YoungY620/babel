# Babel 音频流水线

从配置的 RSS 或音视频页面抓取英文音频，转录、区分说话人、翻译，选择预设音色生成中文音频，并生成文字稿和 RSS。

- 运行环境：Ubuntu、Python 3.12、FFmpeg。环境安装和任务由根目录 Moon 管理。
- 执行：私有 `YoungY620/babel-runner` 的 GitHub Actions 与独立 systemd runner。不要把常驻 runner 注册到公共代码仓库。
- 转录证据：CPU int8 faster-whisper 保留文字、时间与说话人标签；当前云端 `gpt-transcribe` 另行转录音频块。
- 语音：OpenAI Realtime 语音模型和预设音色，按语义分块，逐块做声音质量审核，不克隆、不自动切换低质量后端。
- 文本：默认 `gpt-6-astra` 按块纠错、翻译并另发审核请求，核对专名、数字、遗漏、语义与标点。每块最多重试一次；审核失败保留上次完成产物，发布条件变为未通过。
- 产物：`zh.mp3`、`speech.json`、译文与文章。`speech.json` 记录基于生成音频的时间轴、内容指纹、响度与峰值；源转录时间轴不能直接用作中文音频字幕。
- 分发：公共 GitHub Releases 音频和 Pages/RSS。云端模型调用产生费用。

## 私有运行目录

生产工作流设置绝对路径 `BABEL_DATA_DIR=/srv/babel/data`。本地默认使用被忽略的 `.data`。所有下载、原稿、说话人样本、人工精修输入、审核记录和续跑缓存都位于该目录的 `episodes/<id>` 下。发布配置位于该目录的 `config.env`；代码、节目源配置和音色配置仍从当前检出的仓库读取。重新检出代码不会删除生产数据；旧的源码内 `episodes` 路径不再读取。

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

云端转录固定使用 `gpt-transcribe`，不支持旧模型接口。文本模型配置：`TEXT_MODEL` 与 `TEXT_REVIEW_MODEL`（均默认 `gpt-6-astra`）。使用 Responses 严格 JSON schema，不保留旧翻译模型或无审核降级分支。

## 说话人和音色参考的断点

声纹计算使用固定的 CPU Resemblyzer 0.1.4。每段结果绑定音频哈希、模型和取样范围；中断后复用已完成片段，损坏缓存会重算。零个或一个可靠声纹不进入多样本聚类，暂用单组标签；`diarization.json` 记录可靠片段数和各组秒数。这些编号不是人物身份。

`diarize.py <id> --speakers N` 将明确选择保存在私有 `speaker-input.json`；`--speakers auto` 清除选择，重新使用节目配置。聚类、标签或源音频变化会使相关完成记录失效。

音色参考默认 8 秒，允许保留明确指定的 2–60 秒长度。短语音也可组合，不再把不足 0.8 秒的全部片段丢掉。参考 WAV 和来源/参数都记录在 `samples.json` 中。需要更干净的人工参考时，把 WAV 放到单集的 `voice-references/SPEAKER_XX.wav`；它是明确输入，不直接修改生成的 `samples` 文件。更新输入后，重新运行 `convert.py --slug`。明确选择预设音色时不需要音色参考，但仍检查源转录和说话人记录。

依赖与算法：[Resemblyzer](https://pypi.org/project/Resemblyzer/)、[SciPy cut_tree](https://docs.scipy.org/doc/scipy/reference/generated/scipy.cluster.hierarchy.cut_tree.html)。
