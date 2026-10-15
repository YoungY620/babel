---
name: babel-convert
description: 巴别塔 Babel — 把已抓取的英文音频转成中文配音（转录 → 翻译 → TTS）。当用户要求转换/翻译/生成中文音频，或继续处理某个 slug 时使用。
---

# babel-convert：转换为中文音频

工作目录：`apps/pipeline/`。单条命令跑完整链（幂等，缺哪步补哪步）：

```bash
cd apps/pipeline
export OPENAI_API_KEY=...            # 翻译需要；OPENAI_BASE_URL / TRANSLATE_MODEL 可选
.venv/bin/python pipeline/convert.py --slug <slug>
# 或直接给新源：--index N / --url URL / --next（最新未处理的一集）
```

等价的分步命令：`transcribe.py`（faster-whisper large-v3-turbo）→
`translate.py`（OpenAI 兼容 API，分块）→ `tts.py`（edge-tts，默认
zh-CN-YunjianNeural，`--voice` 可换）。

## 精翻模式（短集/重要集）

可以不用 API：先跑 `transcribe.py`，然后由 agent 逐段精读
`transcript_en.json` 写出 `transcript_zh.json`（保持数组一一对应，含
`text_zh` 字段），再跑 `tts.py`。质量高于机器直译。参考
`episodes/trailer-what-is-acquired/` 的样例。

## 产物

`episodes/<slug>/zh.mp3` 与中英 SRT 字幕。下一步交给 babel-publish。
