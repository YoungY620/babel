"""Publish transaction glue: structured logs, release verification and file handoffs."""
import contextlib
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
import publish_transaction
from test_publish_assets import CATALOG_DIGEST, RECEIPT, episode, manifest_for
from tts import file_hash

PIPELINE = Path(__file__).resolve().parents[1] / "pipeline"


def staged(root, *slugs):
    episodes = root / "episodes"
    for slug in slugs:
        episode(episodes, slug)
    staging = root / "staging"
    with patch.object(publish_transaction.publish_assets, "is_current", return_value=True):
        publish_transaction.publish_assets.stage_assets(staging, episodes)
    return staging


def release_assets(manifest):
    return {"assets": [{"name": asset["file"], "size": asset["bytes"],
                        "digest": f"sha256:{asset['sha256']}"}
                       for asset in manifest["assets"].values()]}


class PublishTransactionTests(unittest.TestCase):
    def test_log_step_emits_one_sanitized_json_line(self):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            line = publish_transaction.log_step("upload", True, 1.23456, new=2)
        self.assertEqual(stream.getvalue().count("\n"), 1)
        self.assertEqual(json.loads(stream.getvalue()), line)
        self.assertEqual(line, {"step": "upload", "ok": True, "seconds": 1.235, "new": 2})

    def test_plan_classifies_new_and_unchanged_and_writes_the_plan_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            staging = staged(root, "first", "second")
            plan_file = root / "plan.json"
            ledger = root / "ledger.json"
            manifest = publish_transaction.publish_assets.verify_staging(staging)
            ledger.write_text(json.dumps({"schemaVersion": 1, "episodes": {
                "first": {"sha256": manifest["assets"]["first"]["sha256"]}}}))
            plan = publish_transaction.plan_publish(ledger, staging)
            self.assertEqual(plan, {"new": ["second"], "unchanged": ["first"]})
            # A missing durable ledger is the bootstrap state: everything is new.
            fresh = publish_transaction.plan_publish(root / "missing", staging)
            self.assertEqual(fresh["new"], ["first", "second"])
            # Drift between the durable ledger and the staged bytes refuses to publish.
            ledger.write_text(json.dumps({"schemaVersion": 1, "episodes": {
                "second": {"sha256": hashlib.sha256(b"older").hexdigest()}}}))
            self.assertRaises(ValueError, publish_transaction.plan_publish, ledger, staging)

    def test_release_assets_must_match_name_digest_and_size(self):
        manifest = manifest_for("ready")
        publish_transaction.check_release_assets(manifest, release_assets(manifest))
        broken = release_assets(manifest)
        broken["assets"][0]["digest"] = "sha256:" + hashlib.sha256(b"tampered").hexdigest()
        self.assertRaises(ValueError, publish_transaction.check_release_assets, manifest, broken)
        broken = release_assets(manifest)
        broken["assets"][0]["size"] += 1
        self.assertRaises(ValueError, publish_transaction.check_release_assets, manifest, broken)
        broken = release_assets(manifest)
        broken["assets"][0].pop("digest")
        self.assertRaises(ValueError, publish_transaction.check_release_assets, manifest, broken)
        self.assertRaises(ValueError, publish_transaction.check_release_assets, manifest, {"assets": []})

    def test_snapshot_changed_requires_no_new_assets_and_a_matching_deployed_catalog(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            catalog = root / "catalog.json"
            catalog.write_bytes(b"catalog")
            empty_plan = {"new": [], "unchanged": ["ready"]}
            self.assertFalse(publish_transaction.snapshot_changed(
                empty_plan, catalog, dict(RECEIPT)))
            self.assertTrue(publish_transaction.snapshot_changed(
                empty_plan, catalog, dict(RECEIPT, catalogSha256="d" * 64)))
            self.assertTrue(publish_transaction.snapshot_changed(empty_plan, catalog, None))
            self.assertTrue(publish_transaction.snapshot_changed({"new": ["ready"]}, catalog, dict(RECEIPT)))
            out = root / "github_output"
            receipt = root / "receipt.json"
            receipt.write_text(json.dumps(RECEIPT))
            code = publish_transaction.main(
                ["snapshot-check", "--plan", self._write_plan(root), "--catalog", str(catalog),
                 "--receipt", str(receipt), "--out", str(out)])
            self.assertEqual(code, 0)
            self.assertEqual(out.read_text().strip(), "changed=false")

    def test_receipt_must_match_revision_and_dispatched_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            catalog = root / "catalog.json"
            catalog.write_bytes(b"catalog")
            receipt = root / "receipt.json"
            receipt.write_text(json.dumps(RECEIPT))
            checked = publish_transaction.check_receipt(
                json.loads(receipt.read_text()), catalog, RECEIPT["dataRevision"], 1)
            self.assertEqual(checked["runId"], 1)
            self.assertRaises(ValueError, publish_transaction.check_receipt,
                              json.loads(receipt.read_text()), catalog, "e" * 40, 1)
            self.assertRaises(ValueError, publish_transaction.check_receipt,
                              json.loads(receipt.read_text()), catalog, RECEIPT["dataRevision"], 2)

    def test_advance_writes_the_advanced_ledger_and_retains_pruned_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            staging = staged(root, "ready")
            catalog = root / "catalog.json"
            catalog.write_bytes(b"catalog")
            receipt = root / "receipt.json"
            receipt.write_text(json.dumps(RECEIPT))
            out = root / "ledger-next" / "ledger.json"
            advanced, plan = publish_transaction.advance_ledger_file(
                root / "ledger.json", staging, receipt, catalog, out)
            self.assertEqual(plan["new"], ["ready"])
            self.assertEqual(advanced["episodes"]["ready"]["dataRevision"], RECEIPT["dataRevision"])
            self.assertEqual(publish_transaction.publish_assets.load_ledger(out)["episodes"],
                             advanced["episodes"])
            receipt.write_text(json.dumps(dict(RECEIPT, catalogSha256="d" * 64)))
            self.assertRaises(ValueError, publish_transaction.advance_ledger_file,
                              root / "ledger.json", staging, receipt, catalog, out)

    def test_cli_logs_one_json_line_and_exits_nonzero_on_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            staging = staged(root, "ready")
            plan_file = root / "plan.json"
            ok = subprocess.run(
                [sys.executable, str(PIPELINE / "publish_transaction.py"), "plan",
                 "--ledger", str(root / "ledger.json"), "--staging", str(staging),
                 "--out", str(plan_file)],
                capture_output=True, text=True)
            self.assertEqual(ok.returncode, 0, ok.stderr)
            logged = json.loads(ok.stdout.strip())
            self.assertEqual((logged["step"], logged["ok"], logged["new"]), ("ledger-plan", True, 1))
            self.assertEqual(json.loads(plan_file.read_text())["new"], ["ready"])
            bad = subprocess.run(
                [sys.executable, str(PIPELINE / "publish_transaction.py"), "check-upload",
                 "--staging", str(staging), "--assets", str(plan_file)],
                capture_output=True, text=True)
            self.assertEqual(bad.returncode, 1)
            self.assertFalse(json.loads(bad.stdout.strip())["ok"])
            failed = subprocess.run(
                [sys.executable, str(PIPELINE / "publish_transaction.py"), "log",
                 "--step", "preflight", "--fail", "--seconds", "1"],
                capture_output=True, text=True)
            self.assertEqual(failed.returncode, 1)
            self.assertEqual(json.loads(failed.stdout.strip())["ok"], False)

    def _write_plan(self, root):
        plan = root / "plan.json"
        plan.write_text(json.dumps({"new": [], "unchanged": ["ready"]}))
        return str(plan)


if __name__ == "__main__":
    unittest.main()
