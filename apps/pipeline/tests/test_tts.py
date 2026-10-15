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
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"TTS_VOICE": "cedar"}), \
                patch.object(tts, "request", return_value=test_audio()) as synth, \
                patch.object(tts, "verify_audio", return_value={"passed": True, "issues": []}):
            directory = Path(tmp)
            segments = [{"speaker": "SPEAKER_00", "text_zh": "真的吗？当然！"}]
            (directory / "transcript_zh.json").write_text(json.dumps(segments))
            first = tts.render(directory, segments, "cedar")
            self.assertTrue(tts.is_current(directory))
            self.assertGreater(first["units"][0]["end"], 1.3)  # Interior silence survives trimming.
            self.assertLess(first["units"][0]["end"], 1.6)
            tts.render(directory, segments, "cedar")
            self.assertEqual(synth.call_count, 1)
            segments[0]["text_zh"] = "新的文字，新的配音。"
            (directory / "transcript_zh.json").write_text(json.dumps(segments))
            self.assertFalse(tts.is_current(directory))
            second = tts.render(directory, segments, "cedar")
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


if __name__ == "__main__":
    unittest.main()
