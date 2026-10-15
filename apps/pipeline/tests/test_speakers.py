"""Speaker edge cases, actual short-clip WAVs and interrupted embedding reuse."""
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
import diarize
import samples
import transcribe
from tts import ffmpeg, save


def source_stamp(directory, rows):
    save(directory / "transcript_en.json", rows)
    save(directory / "transcribe.json", {"plan": transcribe.source_plan(directory), "rawSha256": transcribe.raw_digest(rows)})


class Vector(list):
    def tolist(self):
        return list(self)


class SpeakerTests(unittest.TestCase):
    def test_no_or_one_reliable_embedding_and_short_context_are_safe(self):
        rows = [{"start": 0, "end": .3, "text": "short"}, {"start": .3, "end": 2, "text": "long"}]
        for vectors in [[None, None], [None, [1.0] * 256]]:
            assigned, seconds = diarize.assign_speakers(rows, vectors, 2)
            self.assertEqual([row["speaker"] for row in assigned], ["SPEAKER_00"] * 2)
            self.assertEqual(seconds, {"SPEAKER_00": 2})
        rows.append({"start": 2, "end": 5, "text": "other"})
        with patch.object(diarize, "cluster_labels", return_value=[5, 9]):
            assigned, seconds = diarize.assign_speakers(rows, [None, [1], [2]], 2)
        self.assertEqual([row["speaker"] for row in assigned], ["SPEAKER_01", "SPEAKER_01", "SPEAKER_00"])
        self.assertEqual(sum(seconds.values()), 5)
        self.assertRaises(ValueError, diarize.assign_speakers, [], [], 2)

    @unittest.skipUnless(importlib.util.find_spec("numpy") and importlib.util.find_spec("scipy"), "Scientific dependencies required")
    def test_real_ward_cut_produces_the_requested_two_groups(self):
        self.assertEqual(len(set(diarize.cluster_labels([[1., 0.], [0., 1.]], 2))), 2)
        self.assertEqual(len(set(diarize.cluster_labels([[1., 0.], [.99, .01], [0., 1.]], 2))), 2)
        self.assertEqual(diarize.cluster_labels([[1., 0.], [0., 1.]], 1), [0, 0])

    def test_interruption_and_corrupt_embedding_cache_do_not_repeat_approved_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "source.mp3").write_bytes(b"source")
            rows = [{"start": i, "end": i + 1, "text": "speech"} for i in range(2)]
            encoder = Mock()
            encoder.embed_utterance.side_effect = [Vector([1.] * 256), RuntimeError("interrupted")]
            module = types.SimpleNamespace(VoiceEncoder=Mock(return_value=encoder), preprocess_wav=lambda _: [0] * 4000)
            spec = {"source": diarize.file_hash(directory / "source.mp3")}
            with patch.dict(sys.modules, {"resemblyzer": module}), patch.object(diarize, "ffmpeg", side_effect=lambda *args: args[-1].write_bytes(b"wav")):
                self.assertRaises(RuntimeError, diarize.extract_embeddings, directory, rows, spec)
                self.assertEqual(len(list((directory / ".speaker_parts").glob("*.json"))), 1)
                encoder.embed_utterance.side_effect = [Vector([2.] * 256)]
                vectors = diarize.extract_embeddings(directory, rows, spec)
                self.assertEqual([vector[0] for vector in vectors], [1., 2.])
                self.assertEqual(encoder.embed_utterance.call_count, 3)
                first = next(path for path in (directory / ".speaker_parts").glob("*.json") if json.loads(path.read_text())["vector"][0] == 1)
                record = json.loads(first.read_text())
                record["vector"][0] = 99
                save(first, record)
                encoder.embed_utterance.side_effect = [Vector([1.] * 256)]
                self.assertEqual(diarize.extract_embeddings(directory, rows, spec)[0][0], 1)
                self.assertEqual(encoder.embed_utterance.call_count, 4)

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg required")
    def test_short_voice_references_are_bound_to_source_and_preserve_explicit_inputs(self):
        with tempfile.TemporaryDirectory(prefix="babel-speaker-'") as tmp, patch.dict(os.environ, {"TTS_VOICE": ""}):
            directory = Path(tmp)
            (directory / "meta.json").write_text('{"title":"Test"}')
            ffmpeg("-f", "lavfi", "-i", "sine=frequency=220:duration=2", "-ac", "1", directory / "source.mp3")
            rows = [{"start": 0, "end": .3, "text": "first"}, {"start": .4, "end": .7, "text": "second"}]
            source_stamp(directory, rows)
            with patch.object(diarize, "extract_embeddings", return_value=[None, None]) as extractor:
                diarize.prepare(directory)
                diarize.prepare(directory)
                self.assertEqual(extractor.call_count, 1)
            self.assertTrue(diarize.is_current(directory))
            samples.prepare(directory)
            self.assertTrue(samples.is_current(directory))
            self.assertTrue(samples.valid_wav(directory / "samples/SPEAKER_00.wav"))
            before = (directory / "samples/SPEAKER_00.wav").read_bytes()
            (directory / "samples/SPEAKER_00.wav").write_bytes(b"corrupt")
            self.assertFalse(samples.is_current(directory))
            samples.prepare(directory)
            self.assertEqual((directory / "samples/SPEAKER_00.wav").read_bytes(), before)
            overrides = directory / "voice-references"
            overrides.mkdir()
            ffmpeg("-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-ac", "1", "-ar", "16000", overrides / "SPEAKER_00.wav")
            self.assertFalse(samples.is_current(directory))
            samples.prepare(directory, 12)
            self.assertTrue(samples.is_current(directory))
            self.assertNotEqual((directory / "samples/SPEAKER_00.wav").read_bytes(), before)
            self.assertEqual(json.loads((directory / "samples.json").read_text())["seconds"], 12)
            save(directory / "speaker-input.json", {"speakers": 1})
            self.assertFalse(diarize.is_current(directory))
            self.assertFalse(samples.is_current(directory))
            with patch.object(diarize, "extract_embeddings", return_value=[None, None]):
                diarize.prepare(directory)
            self.assertTrue(diarize.is_current(directory))
            (directory / "source.mp3").write_bytes(b"changed recording")
            self.assertFalse(diarize.is_current(directory))
            self.assertFalse(samples.is_current(directory))
