import json
import sys
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
import build_catalog


class CatalogTests(unittest.TestCase):
    def test_export_uses_generated_clock_and_omits_private_or_unverified_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            episodes = root / "episodes"
            assets = root / "assets"
            (assets / "covers").mkdir(parents=True)
            (assets / "covers/babel.svg").write_text("<svg/>")
            label = {"zh-CN": "标题", "en": "Title"}
            series = [{"id": "babel", "title": label, "summary": label,
                       "cover": "covers/babel.svg", "links": []}]
            for slug in ["approved", "legacy"]:
                directory = episodes / slug
                directory.mkdir(parents=True)
                files = {
                    "meta.json": {"show": "babel", "pubDate": "Fri, 16 Oct 2026 00:00:00 GMT",
                                  "source": "https://example.com/show"},
                    "web.json": {"title": label, "summary": label, "article": label},
                    "transcript_zh.json": [{"text": "One source sentence.", "start": 500, "end": 600}],
                    "speech.json": {"audio_sha256": "a" * 64, "audio_bytes": 2000, "duration_seconds": 10,
                                    "model": "speech-model", "verification": {"model": "review-model", "reviewed_units": 2},
                                    "units": [{"start": 0, "end": 4, "speaker": "Narrator", "text": "第一句。", "source_indices": [0]},
                                              {"start": 4.2, "end": 9, "speaker": "Narrator", "text": "第二句。", "source_indices": [0]}]},
                    "secret.json": {"credential": "must-not-be-published"},
                }
                for name, value in files.items():
                    (directory / name).write_text(json.dumps(value))
            with patch.object(build_catalog, "is_current", side_effect=lambda path: path.name == "approved"):
                output = root / "public"
                result = build_catalog.export_catalog(output, episodes, series, assets, "https://example.com/audio")
            if shutil.which("pnpm"):
                subprocess.run(["pnpm", "--filter", "@babel/catalog", "validate", str(output)],
                               cwd=build_catalog.REPO, check=True, stdout=subprocess.DEVNULL)
            self.assertEqual([episode["id"] for episode in result["episodes"]], ["approved"])
            detail = json.loads((output / "episodes/approved/detail.json").read_text())
            self.assertEqual(len(detail["cues"]), 1)
            self.assertEqual(detail["cues"][0]["end"], 9)
            self.assertEqual(detail["cues"][0]["text"]["en"], "One source sentence.")
            self.assertIn("00:00:00.000 --> 00:00:09.000", (output / "episodes/approved/en.vtt").read_text())
            self.assertFalse(list(output.rglob("secret.json")))
            self.assertFalse(list(output.rglob("transcript_zh.json")))
            self.assertRaises(ValueError, build_catalog.export_catalog, output, episodes, series, assets, "https://example.com/audio")


if __name__ == "__main__":
    unittest.main()
