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
# 或直接给新源：--index N / --url URL / --cycle（本周期全部未处理单集）
```

等价的分步命令：`transcribe.py`（faster-whisper large-v3-turbo）→
`diarize.py`（resemblyzer 声纹聚类，打 SPEAKER_XX 标签）→
`samples.py`（每人剪 ~60s 克隆样本）→
`translate.py`（OpenAI 兼容 API，分块）→
`tts.py`（默认 XTTS v2 声纹克隆，逐段用对应说话人嗓音合成中文；
`--backend edge` 退化为 edge-tts 多音色）。

## 声纹克隆说明

- 样本在 `episodes/<slug>/samples/SPEAKER_XX.wav`，可人工替换成更干净的片段
- SPEAKER_00 = 全片说话时长最长者（通常为主播/主访谈人）
- 克隆真实人物嗓音用于公开发布涉及肖像/声音权，见根 README 版权提醒

## 精翻模式（短集/重要集）

可以不用 API：先跑 `transcribe.py`，然后由 agent 逐段精读
`transcript_en.json` 写出 `transcript_zh.json`（保持数组一一对应，含
`text_zh` 字段），再跑 `tts.py`。质量高于机器直译。参考
`episodes/trailer-what-is-acquired/` 的样例。

## 产物

`episodes/<slug>/zh.mp3` 与中英 SRT 字幕。下一步交给 babel-publish。
