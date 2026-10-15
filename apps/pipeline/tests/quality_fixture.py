"""Synthetic provider fixture; never evidence of live speech or translation quality."""
import json
import os
from unittest.mock import patch
import text_quality
import polish
import transcribe
import diarize


def result(instructions, content, schema, name, model):
    if name == "bilingual_lines":
        return {"lines": [{"id": row["id"], "text": row["text"], "text_zh": "通过验证，才能发布。"}
                          for row in content["timed_asr"]]}
    if name.endswith("review"):
        return {"passed": True, "issues": []}
    if name == "web_metadata":
        return {"title": {"zh-CN": "测试节目", "en": "Test episode"},
                "summary": {"zh-CN": "用于自动化测试。", "en": "An automated test fixture."}}
    raise AssertionError(name)


def approve(directory):
    (directory / "source.mp3").write_bytes(b"synthetic-source")
    (directory / "transcript_en.json").write_text(json.dumps([
        {"start": 0, "end": 1.5, "speaker": "SPEAKER_00", "text": "A faithful sentence."}]))
    raw = json.loads((directory / "transcript_en.json").read_text())
    transcribe.save(directory / "transcribe.json", {"plan": transcribe.source_plan(directory), "rawSha256": transcribe.raw_digest(raw)})
    with patch.object(diarize, "extract_embeddings", return_value=[None]):
        diarize.prepare(directory)
    with patch.object(text_quality, "duration", return_value=1.5), patch.dict(os.environ, {"OPENAI_API_KEY": "example"}), \
            patch.object(text_quality, "ffmpeg", side_effect=lambda *args: args[-1].write_bytes(b"audio-fixture")), \
            patch.object(text_quality, "transcribe_audio", return_value={"text": "A faithful sentence."}), \
            patch.object(text_quality, "structured", side_effect=result), \
            patch.object(polish, "structured", side_effect=result):
        text_quality.prepare(directory)
        polish.prepare(directory)
