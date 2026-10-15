import io
import json
import math
import os
import shutil
import struct
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
import tts


def test_audio():
    stream = io.BytesIO()
    samples = []
    # Leading/trailing silence and an intentional interior pause.
    for seconds, audible in [(0.1, False), (0.5, True), (0.4, False), (0.5, True), (0.1, False)]:
        samples.extend(int(6000 * math.sin(2 * math.pi * 440 * n / 24000)) if audible else 0
                       for n in range(round(seconds * 24000)))
    with wave.open(stream, "wb") as wav:
        wav.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
        wav.writeframes(struct.pack(f"<{len(samples)}h", *samples))
    return stream.getvalue()


class SpeechTests(unittest.TestCase):
    def test_semantic_units_preserve_questions_exclamations_and_turns(self):
        units = tts.speech_units([
            {"speaker": "SPEAKER_00", "text_zh": "真的吗？当然！"},
            {"speaker": "SPEAKER_00", "text_zh": "增长了百分之十二点五。"},
            {"speaker": "SPEAKER_01", "text_zh": "为什么？我们继续看。"},
        ])
        self.assertEqual([u["text"] for u in units], ["真的吗？当然！增长了百分之十二点五。", "为什么？我们继续看。"])
        self.assertEqual(units[0]["source_indices"], [0, 1])
        self.assertEqual(units[0]["pause_seconds"], 0.35)
        self.assertRaises(ValueError, tts.speech_units, [{"text_zh": "尚未断句" * 200}])
        self.assertRaises(ValueError, tts.speech_units, [{"text_zh": ""}])

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg required")
    def test_real_audio_cache_invalidation_and_failed_verification(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"TTS_VOICE": ""}), \
                patch.object(tts, "request", return_value=test_audio()) as synth, \
                patch.object(tts, "verify_audio", return_value={"passed": True, "issues": []}):
            directory = Path(tmp)
            segments = [{"speaker": "SPEAKER_00", "text_zh": "真的吗？当然！"}]
            (directory / "transcript_zh.json").write_text(json.dumps(segments))
            first = tts.render(directory, segments, "cedar")
            self.assertTrue(tts.is_current(directory))
            self.assertGreater(first["units"][0]["end"], 1.3)  # Interior silence survives trimming.
            self.assertLess(first["units"][0]["end"], 1.6)
            self.assertEqual(first["voice_mode"], "cedar")
            shutil.rmtree(directory / ".speech_parts")
            audio = directory / "zh.mp3"
            stat = audio.stat()
            os.utime(audio, ns=(stat.st_atime_ns, stat.st_mtime_ns + 2_000_000_000))
            self.assertFalse(tts.is_current(directory))
            with patch.object(tts, "select_voices", side_effect=AssertionError("completed output must not reselect voices")):
                tts.render(directory, segments)
            self.assertTrue(tts.is_current(directory))
            self.assertEqual(synth.call_count, 1)
            saved = json.loads((directory / "speech.json").read_text())
            for review in [None, {**saved["verification"], "passed": False}]:
                invalid = {**saved, "verification": review}
                (directory / "speech.json").write_text(json.dumps(invalid))
                self.assertFalse(tts.is_current(directory))
            (directory / "speech.json").write_text(json.dumps(saved))
            segments[0]["text_zh"] = "新的文字，新的配音。"
            (directory / "transcript_zh.json").write_text(json.dumps(segments))
            self.assertFalse(tts.is_current(directory))
            second = tts.render(directory, segments)
            self.assertNotEqual(first["fingerprint"], second["fingerprint"])
            self.assertEqual(synth.call_count, 2)
            with patch.dict(os.environ, {"TTS_MODEL": "different-model"}):
                self.assertFalse(tts.is_current(directory))
            segments[0]["text_zh"] = "这次校验必须失败。"
            (directory / "transcript_zh.json").write_text(json.dumps(segments))
            with patch.object(tts, "verify_audio", return_value={"passed": False, "issues": ["missing clause"]}):
                with self.assertRaises(RuntimeError):
                    tts.render(directory, segments, "cedar")
            self.assertEqual(json.loads((directory / "speech.json").read_text())["fingerprint"], second["fingerprint"])
            self.assertEqual(tts.file_hash(directory / "zh.mp3"), second["audio_sha256"])
            self.assertFalse(tts.is_current(directory))

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg required")
    def test_auto_voice_output_survives_disposable_cache_removal(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"TTS_VOICE": ""}), \
                patch.object(tts, "request", return_value=test_audio()) as synth, \
                patch.object(tts, "verify_audio", return_value={"passed": True, "issues": []}):
            directory = Path(tmp)
            (directory / "samples").mkdir()
            (directory / "samples/SPEAKER_00.wav").write_bytes(test_audio())
            segments = [{"speaker": "SPEAKER_00", "text_zh": "语义清楚，音色一致。"}]
            (directory / "transcript_zh.json").write_text(json.dumps(segments))
            with patch.object(tts, "select_voices", return_value={"SPEAKER_00": "cedar"}):
                first = tts.render(directory, segments)
            shutil.rmtree(directory / ".speech_parts")
            with patch.object(tts, "select_voices", side_effect=AssertionError("unexpected paid voice analysis")):
                second = tts.render(directory, segments)
            self.assertEqual(first["fingerprint"], second["fingerprint"])
            self.assertEqual(synth.call_count, 1)
            self.assertTrue(tts.is_current(directory))

    def test_retry_repairs_a_partial_speaker_sample_directory(self):
        import convert
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"TTS_VOICE": ""}):
            root = Path(tmp)
            directory = root / "episodes/episode"
            (directory / "samples").mkdir(parents=True)
            segments = [{"speaker": f"SPEAKER_{i:02d}", "text": "hello", "text_zh": "你好。"} for i in range(2)]
            for name in ["transcript_en.json", "transcript_zh.json"]:
                (directory / name).write_text(json.dumps(segments))
            (directory / "diarization.json").write_text("{}")
            (directory / "article_zh.md").write_text("你好。")
            (directory / "samples/SPEAKER_00.wav").write_bytes(test_audio())
            def repair(script, slug):
                if script == "samples.py":
                    (directory / "samples/SPEAKER_01.wav").write_bytes(test_audio())
            with patch.object(convert, "ROOT", root), patch.object(convert, "run", side_effect=repair) as run:
                convert.process("episode")
                self.assertEqual([call.args[0] for call in run.call_args_list], ["samples.py", "tts.py"])
                run.reset_mock()
                convert.process("episode")
                self.assertEqual([call.args[0] for call in run.call_args_list], ["tts.py"])


if __name__ == "__main__":
    unittest.main()
