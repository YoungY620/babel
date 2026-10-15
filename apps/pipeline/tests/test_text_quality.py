import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
import text_quality
import polish
import transcribe
from quality_fixture import approve, result


class TextQualityTests(unittest.TestCase):
    def test_long_segments_always_advance_and_invalid_timelines_fail(self):
        segments = [{"start": 0, "end": 2, "text": "a" * 5000}, {"start": 2, "end": 4, "text": "next"}]
        self.assertEqual([[r["id"] for r in group] for group in text_quality.chunks(segments)], [[0], [1]])
        for end in [float("inf"), -1, 601]:
            self.assertRaises(ValueError, text_quality.chunks, [{"start": 0, "end": end, "text": "speech"}])

    def test_review_cache_integrity_and_rejection_preserve_last_completed_script(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(text_quality, "duration", return_value=1.5):
            directory = Path(tmp)
            (directory / "meta.json").write_text(json.dumps({"title": "Test", "description": "Source"}))
            approve(directory)
            self.assertTrue(text_quality.is_current(directory))
            self.assertTrue(polish.is_current(directory))
            before = (directory / "transcript_zh.json").read_bytes()
            (directory / "transcript_zh.json").write_bytes(before + b" ")
            self.assertFalse(text_quality.is_current(directory))
            with patch.object(text_quality, "structured", side_effect=AssertionError("reuse approved block")):
                text_quality.prepare(directory)
            self.assertTrue(text_quality.is_current(directory))
            with patch.object(text_quality, "structured", side_effect=AssertionError("unexpected paid request")):
                text_quality.prepare(directory)
                polish.prepare(directory)
            (directory / "source.mp3").write_bytes(b"changed-source")
            self.assertFalse(transcribe.is_current(directory))
            raw = json.loads((directory / "transcript_en.json").read_text())
            transcribe.save(directory / "transcribe.json", {"plan": transcribe.source_plan(directory), "rawSha256": transcribe.raw_digest(raw)})
            self.assertFalse(text_quality.is_current(directory))
            self.assertFalse(polish.is_current(directory))
            def reject(instructions, content, schema, name, model):
                if name == "script_review": return {"passed": False, "issues": ["Unsupported number"]}
                return result(instructions, content, schema, name, model)
            with patch.dict(os.environ, {"OPENAI_API_KEY": "example"}), \
                    patch.object(text_quality, "ffmpeg", side_effect=lambda *args: args[-1].write_bytes(b"audio")), \
                    patch.object(text_quality, "transcribe_audio", return_value={"text": "Source evidence"}), \
                    patch.object(text_quality, "structured", side_effect=reject):
                self.assertRaises(RuntimeError, text_quality.prepare, directory)
            self.assertEqual((directory / "transcript_zh.json").read_bytes(), before)
            self.assertFalse(text_quality.is_current(directory))

    def test_human_override_is_reviewed_retained_and_can_be_cleared(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(text_quality, "duration", return_value=1.5), patch.dict(os.environ, {"OPENAI_API_KEY": "example"}):
            directory = Path(tmp)
            (directory / "meta.json").write_text('{"title":"Test"}')
            approve(directory)
            override = [{"text": "A faithful sentence.", "text_zh": "人工修正的句子。"}]
            (directory / "script_override.json").write_text(json.dumps(override))
            def review_only(instructions, content, schema, name, model):
                self.assertEqual(name, "script_review")
                return {"passed": True, "issues": []}
            with patch.object(text_quality, "transcribe_audio", side_effect=AssertionError("reuse source evidence")), \
                    patch.object(text_quality, "structured", side_effect=review_only):
                text_quality.prepare(directory)
            self.assertEqual(json.loads((directory / "transcript_zh.json").read_text())[0]["text_zh"], override[0]["text_zh"])
            with patch.object(text_quality, "structured", side_effect=AssertionError("retain approved override")):
                text_quality.prepare(directory)
            (directory / "script_override.json").unlink()
            self.assertFalse(text_quality.is_current(directory))
            with patch.object(text_quality, "structured", side_effect=AssertionError("reuse approved automatic block")):
                text_quality.prepare(directory)
            self.assertTrue(text_quality.is_current(directory))

    def test_retry_reuses_approved_blocks_and_rejects_duplicate_ids(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(text_quality, "duration", return_value=4), patch.dict(os.environ, {"OPENAI_API_KEY": "example"}):
            directory = Path(tmp)
            (directory / "source.mp3").write_bytes(b"source")
            segments = [{"start": i * 2, "end": i * 2 + 1, "text": "word " * 500, "speaker": "SPEAKER_00"} for i in range(2)]
            (directory / "transcript_en.json").write_text(json.dumps(segments))
            transcribe.save(directory / "transcribe.json", {"plan": transcribe.source_plan(directory), "rawSha256": transcribe.raw_digest(segments)})
            def interrupted(instructions, content, schema, name, model):
                if name == "bilingual_lines" and content["timed_asr"][0]["id"] == 1:
                    raise RuntimeError("interrupted")
                return result(instructions, content, schema, name, model)
            with patch.object(text_quality, "ffmpeg", side_effect=lambda *args: args[-1].write_bytes(b"audio")), \
                    patch.object(text_quality, "transcribe_audio", return_value={"text": "Audio evidence"}) as asr, \
                    patch.object(text_quality, "structured", side_effect=interrupted):
                self.assertRaises(RuntimeError, text_quality.prepare, directory)
                self.assertEqual(asr.call_count, 2)
            with patch.object(text_quality, "transcribe_audio", side_effect=AssertionError("evidence must resume")), \
                    patch.object(text_quality, "structured", side_effect=result) as model:
                text_quality.prepare(directory)
                self.assertEqual(model.call_count, 2)
            self.assertTrue(text_quality.is_current(directory))
            group = [{"id": 0}, {"id": 1}]
            self.assertFalse(text_quality.valid_lines([{"id": 0, "text": "a", "text_zh": "甲"}] * 2, group))
            web = directory / "web.json"
            (directory / "meta.json").write_text('{"title":"Test"}')
            def complete_context(instructions, content, schema, name, model):
                self.assertEqual(len(content["script"]), len(segments))
                self.assertEqual([row["text"] for row in content["script"]], [row["text"] for row in segments])
                return result(instructions, content, schema, name, model)
            with patch.object(polish, "structured", side_effect=complete_context): polish.prepare(directory)
            self.assertTrue(polish.is_current(directory))
            web.write_text(web.read_text().replace("测试节目", "过期标题"))
            self.assertFalse(polish.is_current(directory))

    def test_cloud_evidence_covers_source_edges_and_splits_below_upload_limit(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"OPENAI_API_KEY": "example"}):
            directory = Path(tmp)
            (directory / "source.mp3").write_bytes(b"source")
            rows = [{"start": 10, "end": 20, "text": "Speech"}]
            transcribe.save(directory / "transcript_en.json", rows)
            transcribe.save(directory / "transcribe.json", {
                "plan": transcribe.source_plan(directory), "rawSha256": transcribe.raw_digest(rows)})
            def crop(*args):
                args[-1].write_bytes(b"wave")
            with patch.object(text_quality, "duration", return_value=650), \
                    patch.object(text_quality, "ffmpeg", side_effect=crop) as ffmpeg, \
                    patch.object(text_quality, "transcribe_audio", return_value={"text": "Complete source speech"}), \
                    patch.object(text_quality, "structured", side_effect=result):
                text_quality.prepare(directory)
            ranges = [(call.args[1], call.args[5]) for call in ffmpeg.call_args_list]
            self.assertEqual(ranges, [(0, 300), (300, 300), (600, 50)])
            self.assertTrue(all(call.args[-1].suffix == '.wav' for call in ffmpeg.call_args_list))
            self.assertTrue(text_quality.is_current(directory))


if __name__ == "__main__":
    unittest.main()
