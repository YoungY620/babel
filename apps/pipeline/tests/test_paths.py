"""Persistent episode state survives replacement of the source checkout."""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
import fetch
import transcribe
from paths import data_root, episode_directory


class RuntimePathTests(unittest.TestCase):
    def test_private_state_survives_clean_checkout_and_all_cli_checks_use_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            checkout, runtime = root / "checkout", root / "private-data"
            source = Path(fetch.__file__).parent
            def fresh_checkout():
                shutil.copytree(source, checkout / "pipeline", ignore=shutil.ignore_patterns("__pycache__"))
                shutil.copy(source.parent / "voice-presets.json", checkout)
            fresh_checkout()
            item = {"title": "Stable episode", "pubDate": "Fri, 16 Oct 2026 00:00:00 GMT", "description": "",
                    "url": "https://example.com/source.mp3", "bytes": 10, "duration": "60", "image": ""}
            environment = {**os.environ, "BABEL_DATA_DIR": str(runtime)}
            with patch.dict(os.environ, environment), patch.object(fetch, "ROOT", checkout), \
                    patch.object(fetch, "load_feed", return_value=({"title": "Show", "description": "", "image": ""}, [item])), \
                    patch.object(fetch.urllib.request, "urlopen", return_value=io.BytesIO(b"source audio")):
                slug = fetch.download({"id": "show", "rss": "https://example.com/feed"}, 0)
            directory = episode_directory(runtime, slug)
            rows = [{"start": 0, "end": 1, "text": "A stable sentence."}]
            transcribe.save(directory / "transcript_en.json", rows)
            transcribe.save(directory / "transcribe.json", {
                "plan": transcribe.source_plan(directory), "rawSha256": transcribe.raw_digest(rows)})
            checkpoint = directory / ".text_parts/approved-block.json"
            checkpoint.parent.mkdir()
            checkpoint.write_text('{"passed":true}')
            shutil.rmtree(checkout)
            fresh_checkout()
            result = subprocess.run([sys.executable, str(checkout / "pipeline/transcribe.py"), slug],
                                    env=environment, check=True, capture_output=True, text=True)
            self.assertIn("Verified raw ASR unchanged", result.stdout)
            # The same completion CLI reads persistent state; no text/audio review means failure.
            result = subprocess.run([sys.executable, str(checkout / "pipeline/completion.py"), slug],
                                    env=environment, capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(json.loads(checkpoint.read_text()), {"passed": True})
            self.assertFalse((checkout / "episodes").exists())
            self.assertFalse((checkout / ".data").exists())

    def test_default_absolute_override_and_storage_escape_guards(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=True):
            root = Path(tmp).resolve()
            self.assertEqual(data_root(root), root / ".data")
            with patch.dict(os.environ, {"BABEL_DATA_DIR": "relative"}):
                self.assertRaises(ValueError, data_root, root)
            with patch.dict(os.environ, {"BABEL_DATA_DIR": str(root / "persistent")}):
                self.assertEqual(data_root(root), root / "persistent")
            for slug in ["", ".", "../outside", "a/b", "a--b", "a" * 161]:
                self.assertRaises(ValueError, episode_directory, root, slug)
            outside = root / "outside"
            outside.mkdir()
            storage = root / "persistent"
            storage.mkdir()
            (storage / "episodes").symlink_to(outside, target_is_directory=True)
            self.assertRaises(ValueError, episode_directory, storage, "episode")
