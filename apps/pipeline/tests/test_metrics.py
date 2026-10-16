"""Stage metrics: pure summaries, JSONL append, corrupt-line tolerance, run() wiring."""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
import convert
from metrics import (append_stage_record, percentile, stages_file,
                     summarize_stage_seconds, tail_stage_records)


class PercentileTests(unittest.TestCase):
    def test_percentile_interpolation(self):
        self.assertEqual(percentile([], 0.9), 0.0)
        self.assertEqual(percentile([7], 0.9), 7.0)
        self.assertEqual(percentile([10, 20], 0.5), 15.0)
        self.assertAlmostEqual(percentile(list(range(1, 11)), 0.9), 9.1)
        self.assertEqual(percentile([30, 10, 20], 0.0), 10.0)

    def test_summarize_groups_stages_and_ignores_bad_rows(self):
        rows = [
            {"episode": "a", "stage": "transcribe.py", "seconds": 10, "ok": True},
            {"episode": "b", "stage": "transcribe.py", "seconds": 20, "ok": True},
            {"episode": "b", "stage": "transcribe.py", "seconds": 30, "ok": False},
            {"episode": "a", "stage": "tts.py", "seconds": 5.5, "ok": True},
            {"stage": "", "seconds": 1},
            {"stage": "tts.py", "seconds": "long"},
            {"stage": "tts.py", "seconds": True},
            {"stage": "tts.py"},
            "not-a-dict",
        ]
        summary = summarize_stage_seconds(rows)
        self.assertEqual(summary["transcribe.py"],
                         {"count": 3, "median": 20.0, "p90": 28.0})
        self.assertEqual(summary["tts.py"], {"count": 1, "median": 5.5, "p90": 5.5})
        self.assertEqual(summarize_stage_seconds([]), {})


class JsonlTests(unittest.TestCase):
    def test_append_creates_directory_and_round_trips(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            record = {"episode": "ep-one", "stage": "tts.py", "seconds": 1.5, "ok": True}
            append_stage_record(root, record)
            append_stage_record(root, {**record, "episode": None, "ok": False})
            self.assertEqual(tail_stage_records(stages_file(root)),
                             [record, {**record, "episode": None, "ok": False}])

    def test_tail_tolerates_corrupt_blank_and_non_object_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp).resolve() / "metrics" / "stages.jsonl"
            path.parent.mkdir(parents=True)
            good = {"episode": "ep", "stage": "polish.py", "seconds": 3, "ok": True}
            path.write_text("\n".join([
                json.dumps(good), "garbage{", "", "[1, 2]", json.dumps(good),
            ]) + "\n")
            self.assertEqual(tail_stage_records(path, 200), [good, good])
            self.assertEqual(tail_stage_records(path, 1), [good])
            self.assertEqual(tail_stage_records(path, 0), [])

    def test_tail_missing_file_is_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(tail_stage_records(Path(tmp) / "absent.jsonl"), [])


class ConvertRunMetricsTests(unittest.TestCase):
    def test_run_records_success_and_failure_without_hiding_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            calls = []

            def fake_run(argv, check, env):
                calls.append((argv, check, env))

            def failing_run(argv, check, env):
                raise subprocess.CalledProcessError(3, argv)

            with patch.dict(os.environ, {"BABEL_DATA_DIR": str(root)}, clear=True), \
                    patch.object(convert, "subprocess", SimpleNamespace(run=fake_run)):
                convert.run("transcribe.py", "ep-one")
            with self.assertRaises(subprocess.CalledProcessError), \
                    patch.dict(os.environ, {"BABEL_DATA_DIR": str(root)}), \
                    patch.object(convert, "subprocess", SimpleNamespace(run=failing_run)):
                convert.run("tts.py", "ep-one")

            self.assertEqual(len(calls), 1)
            argv, check, env = calls[0]
            self.assertEqual(argv[1].endswith("pipeline/transcribe.py"), True)
            self.assertTrue(check)
            self.assertEqual(env.get("OMP_NUM_THREADS"), "2")
            records = tail_stage_records(stages_file(root))
            self.assertEqual(stages_file(root).read_text().count("\n"), 2)
            self.assertEqual([r["episode"] for r in records], ["ep-one", "ep-one"])
            self.assertEqual([r["stage"] for r in records], ["transcribe.py", "tts.py"])
            self.assertEqual([r["ok"] for r in records], [True, False])
            for record in records:
                self.assertIsInstance(record["seconds"], float)
                self.assertGreaterEqual(record["seconds"], 0.0)

    def test_metrics_failure_only_warns_and_never_aborts_the_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            ran = []
            with patch.dict(os.environ, {"BABEL_DATA_DIR": "relative"}), \
                    patch.object(convert, "subprocess",
                                 SimpleNamespace(run=lambda *a, **k: ran.append(a))), \
                    contextlib.redirect_stderr(io.StringIO()) as err:
                convert.run("polish.py", "ep-two")
            self.assertEqual(len(ran), 1)
            self.assertIn("stage metrics warning", err.getvalue())


if __name__ == "__main__":
    unittest.main()
