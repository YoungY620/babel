"""Stable asset staging, drift-safe ledger planning and receipt-gated advance."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
import publish_assets
from tts import file_hash

CATALOG_DIGEST = hashlib.sha256(b"catalog").hexdigest()
RECEIPT = {"codeRevision": "b" * 40, "dataRevision": "a" * 40,
           "catalogSha256": CATALOG_DIGEST, "runId": 1}


def episode(episodes, slug, audio=b"verified-audio", duration=12.5):
    directory = episodes / slug
    directory.mkdir(parents=True)
    (directory / "zh.mp3").write_bytes(audio)
    (directory / "speech.json").write_text(json.dumps(
        {"audio_sha256": hashlib.sha256(audio).hexdigest(), "audio_bytes": len(audio),
         "duration_seconds": duration, "verification": {"passed": True}}))
    return directory


def manifest_for(*slugs, audio=b"verified-audio"):
    assets = {}
    for slug in slugs:
        digest = hashlib.sha256(audio).hexdigest()
        assets[slug] = {"file": publish_assets.asset_name(slug, digest), "sha256": digest,
                        "bytes": len(audio), "durationSeconds": 12.5, "contentVersion": digest}
    return {"schemaVersion": 1, "generatedAt": "2026-10-16T00:00:00Z", "assets": assets}


class PublishAssetTests(unittest.TestCase):
    def test_asset_names_are_deterministic_and_content_addressed(self):
        digest = hashlib.sha256(b"audio").hexdigest()
        name = publish_assets.asset_name("my-show-1", digest)
        self.assertEqual(name, f"my-show-1-zh-{digest[:12]}.mp3")
        self.assertEqual(name, publish_assets.asset_name("my-show-1", digest))
        other = hashlib.sha256(b"other").hexdigest()
        self.assertNotEqual(name, publish_assets.asset_name("my-show-1", other))
        self.assertRaises(ValueError, publish_assets.asset_name, "bad slug", digest)
        self.assertRaises(ValueError, publish_assets.asset_name, "ok-slug", "not-a-digest")

    def test_staging_skips_unverified_and_missing_audio_then_rehashes_every_asset(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            episodes = root / "episodes"
            ready = episode(episodes, "ready")
            episode(episodes, "draft")
            ghost = episodes / "ghost"
            ghost.mkdir()
            (ghost / "speech.json").write_text((ready / "speech.json").read_text())
            staging = root / "staging"
            with patch.object(publish_assets, "is_current", side_effect=lambda path: path.name != "draft"):
                manifest = publish_assets.stage_assets(staging, episodes)
            asset = manifest["assets"]["ready"]
            name = publish_assets.asset_name("ready", asset["contentVersion"])
            self.assertEqual(list(manifest["assets"]), ["ready"])
            self.assertEqual(asset["file"], name)
            self.assertEqual((staging / name).read_bytes(), b"verified-audio")
            self.assertEqual(asset["sha256"], file_hash(staging / name))
            self.assertEqual(asset["bytes"], len(b"verified-audio"))
            self.assertEqual(asset["durationSeconds"], 12.5)
            self.assertEqual(publish_assets.verify_staging(staging), manifest)
            (staging / name).write_bytes(b"tampered")
            self.assertRaises(ValueError, publish_assets.verify_staging, staging)
            (staging / name).write_bytes(b"verified-audio")
            broken = json.loads((staging / "manifest.json").read_text())
            broken["assets"]["ready"]["contentVersion"] = hashlib.sha256(b"tampered").hexdigest()
            (staging / "manifest.json").write_text(json.dumps(broken))
            self.assertRaises(ValueError, publish_assets.verify_staging, staging)
            broken["assets"]["ready"].pop("sha256")
            (staging / "manifest.json").write_text(json.dumps(broken))
            self.assertRaises(ValueError, publish_assets.verify_staging, staging)
            self.assertRaises(ValueError, publish_assets.stage_assets, staging, episodes)

    def test_plan_uploads_classifies_new_and_unchanged_and_rejects_drift(self):
        manifest = manifest_for("first", "second")
        ledger = {"schemaVersion": 1, "episodes": {}}
        self.assertEqual(publish_assets.plan_uploads(ledger, manifest)["new"], ["first", "second"])
        first = manifest["assets"]["first"]
        ledger["episodes"]["first"] = {"sha256": first["sha256"], "file": first["file"]}
        plan = publish_assets.plan_uploads(ledger, manifest)
        self.assertEqual(plan, {"new": ["second"], "unchanged": ["first"]})
        ledger["episodes"]["first"]["sha256"] = hashlib.sha256(b"older").hexdigest()
        self.assertRaises(ValueError, publish_assets.plan_uploads, ledger, manifest)
        ledger["episodes"]["first"] = "garbage"
        self.assertRaises(ValueError, publish_assets.plan_uploads, ledger, manifest)

    def test_ledger_advances_only_with_a_matching_receipt_and_retains_pruned_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            episodes = root / "episodes"
            episode(episodes, "ready")
            staging = root / "staging"
            with patch.object(publish_assets, "is_current", return_value=True):
                manifest = publish_assets.stage_assets(staging, episodes)
            catalog = root / "catalog.json"
            catalog.write_bytes(b"catalog")
            ledger_path = root / "ledger.json"
            ledger = publish_assets.load_ledger(ledger_path)
            advanced = publish_assets.advance_ledger(ledger, manifest, RECEIPT, catalog,
                                                     published_at="2026-10-16T00:00:00Z")
            entry = advanced["episodes"]["ready"]
            self.assertEqual(entry["contentVersion"], manifest["assets"]["ready"]["contentVersion"])
            self.assertEqual(entry["firstPublishedAt"], "2026-10-16T00:00:00Z")
            self.assertEqual(entry["dataRevision"], RECEIPT["dataRevision"])
            # A later snapshot without this episode (pruned caches) keeps the ledger entry.
            empty = {"schemaVersion": 1, "generatedAt": "2026-10-17T00:00:00Z", "assets": {}}
            retained = publish_assets.advance_ledger(advanced, empty, RECEIPT, catalog)
            self.assertEqual(retained["episodes"]["ready"], entry)
            # A matching receipt must also be present to add new entries at all.
            self.assertRaises(ValueError, publish_assets.advance_ledger, advanced, manifest,
                              dict(RECEIPT, catalogSha256="c" * 64), catalog)
            self.assertRaises(ValueError, publish_assets.advance_ledger, advanced, manifest,
                              dict(RECEIPT, dataRevision="not-a-sha"), catalog)
            self.assertRaises(ValueError, publish_assets.advance_ledger, advanced, manifest, [], catalog)

    def test_load_ledger_rejects_corrupt_state_but_starts_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.json"
            self.assertEqual(publish_assets.load_ledger(path)["episodes"], {})
            path.write_text("{not json")
            self.assertRaises(ValueError, publish_assets.load_ledger, path)
            path.write_text(json.dumps({"schemaVersion": 2, "episodes": {}}))
            self.assertRaises(ValueError, publish_assets.load_ledger, path)


if __name__ == "__main__":
    unittest.main()
