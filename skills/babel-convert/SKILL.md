---
name: babel-convert
description: 巴别塔 Babel — 把已抓取的英文音频转成中文配音（转录 → 翻译 → TTS）。当用户要求转换/翻译/生成中文音频，或继续处理某个 slug 时使用。
---

# babel-convert：转换为中文音频

工作目录：`apps/pipeline/`。单条命令跑完整链（幂等，缺哪步补哪步）：

```bash
cd apps/pipeline
export OPENAI_API_KEY=...            # 翻译、预设语音与音频校验
.venv/bin/python pipeline/convert.py --slug <slug>
# 或直接给新源：--index N / --url URL / --cycle（本周期全部未处理单集）
```

等价的分步命令：`transcribe.py`（faster-whisper large-v3-turbo）→
`diarize.py`（resemblyzer 声纹聚类，打 SPEAKER_XX 标签）→
`samples.py`（每人剪约 8s 的音色选择参考）→
`translate.py`（OpenAI 兼容 API，分块）→
`tts.py`（按声音风格选预设音色、保留语义停顿、逐块审核、统一响度）。

## 音色与完成状态

- 不克隆原声，不自动降级到旧后端。候选音色见 `voice-presets.json`。
- 样本在 `episodes/<slug>/samples/SPEAKER_XX.wav`，可替换成更干净的片段。
- SPEAKER_00 是本集说话时长最长者；该编号不能当作跨集人物身份。
- `tts.py <slug> --voice cedar` 可明确指定音色；否则依据可听到的风格自动选择。
- 必须检查 `speech.json` 的版本指纹和审核结果；仅有旧 `zh.mp3` 不算完成。
- 音频质量审核失败时修正原文或音色后重跑，不跳过审核，也不发布未通过产物。

## 精翻模式（短集/重要集）

翻译可以手动完成，但语音合成和审核仍需要 API。先跑 `transcribe.py`，然后由 agent 逐段精读
`transcript_en.json` 写出 `transcript_zh.json`（保持数组一一对应，含
`text_zh` 字段），再跑 `tts.py`。保持含义、专名和数字准确。参考
`episodes/trailer-what-is-acquired/` 的样例。

## 产物

`episodes/<slug>/zh.mp3`、`speech.json` 与文字稿。生成音频的字幕以 `speech.json` 时间轴为准，不能套用原音频时间。下一步交给 babel-publish。
