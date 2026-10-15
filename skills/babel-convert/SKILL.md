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
`translate.py`（独立云端转录证据、逐块纠错/翻译和审核）→
`polish.py`（双语元数据审核、完整文章整理）→
`tts.py`（按声音风格选预设音色、保留语义停顿、逐块审核、统一响度）。

## 音色与完成状态

- 不克隆原声，不自动降级到旧后端。候选音色见 `voice-presets.json`。
- 样本在 `episodes/<slug>/samples/SPEAKER_XX.wav`，可替换成更干净的片段。
- SPEAKER_00 是本集说话时长最长者；该编号不能当作跨集人物身份。
- `tts.py <slug> --voice cedar` 可明确指定音色；显式选择会保留；`--voice auto` 重新启用自动选择。
- 用 `completion.py <slug>` 核对文本、双语元数据和语音审核的完整指纹；仅有旧 `zh.mp3` 不算完成。
- 音频质量审核失败时修正原文或音色后重跑，不跳过审核，也不发布未通过产物。

## 精翻模式（短集/重要集）

把精修后的对齐数组写入 `script_override.json`，每项含 `text` 和 `text_zh`，数量与原始转录一致。运行完整 `convert.py --slug`，由原音频的独立转录证据审核后合成。保留覆盖文件会保留精修输入；删除它会回到自动生成。
不要直接修改完成产物后绕过文本或声音审核。

## 产物

`episodes/<slug>/zh.mp3`、`speech.json` 与文字稿。生成音频的字幕以 `speech.json` 时间轴为准，不能套用原音频时间。下一步交给 babel-publish。
