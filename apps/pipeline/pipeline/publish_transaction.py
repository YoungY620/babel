#!/usr/bin/env python3
"""Glue the publish phases together around the reviewed staging/ledger helpers.

Runs only inside the private control workflow. Uploading, pushing, dispatching and
deleting stay in the reviewed workflow shell so each action is visible in the job log;
every subcommand here is a pure, offline check that reads files the workflow prepared
and writes the file the next phase needs. Each subcommand prints exactly one
structured JSON line (step, ok, seconds, counts) and never sees a credential.
"""
import argparse
import json
import sys
import time
from pathlib import Path

import publish_assets
from build_catalog import write_json
from tts import file_hash


def log_step(step, ok, seconds, **counts):
    line = {"step": step, "ok": bool(ok), "seconds": round(float(seconds), 3)}
    line.update(counts)
    print(json.dumps(line, ensure_ascii=False), flush=True)
    return line


def plan_publish(ledger_path, staging):
    manifest = publish_assets.verify_staging(staging)
    ledger = publish_assets.load_ledger(ledger_path)
    return publish_assets.plan_uploads(ledger, manifest)


def check_release_assets(manifest, assets):
    """Every staged asset must be on the release with a matching sha256 digest and size.

    `assets` is the parsed `gh release view --json assets` payload; GitHub serves
    release asset digests as `sha256:<hex>`, and a missing digest means the installed
    gh is too old to verify the upload, which fails instead of skipping verification.
    """
    published = {asset.get("name"): asset for asset in assets.get("assets", [])}
    for asset in manifest["assets"].values():
        entry = published.get(asset["file"])
        if entry is None:
            raise ValueError(f"Staged asset is missing from the audio release: {asset['file']}")
        digest = str(entry.get("digest") or "")
        if not digest.startswith("sha256:") or digest.removeprefix("sha256:") != asset["sha256"]:
            raise ValueError(f"Release digest does not match the staged manifest: {asset['file']}")
        if entry.get("size") != asset["bytes"]:
            raise ValueError(f"Release size does not match the staged manifest: {asset['file']}")


def snapshot_changed(plan, catalog_path, receipt):
    """The transaction publishes when new assets exist or the deployed catalog differs."""
    if plan["new"]:
        return True
    if not isinstance(receipt, dict):
        return True
    return receipt.get("catalogSha256") != file_hash(catalog_path)


def check_receipt(receipt, catalog_path, data_revision, run_id):
    receipt = publish_assets.verify_receipt(receipt, catalog_path)
    if str(data_revision) != str(receipt.get("dataRevision")):
        raise ValueError("Receipt dataRevision does not match the pushed publication revision")
    if run_id is not None and int(run_id) != int(receipt["runId"]):
        raise ValueError("Receipt runId does not match the dispatched Pages run")
    return receipt


def advance_ledger_file(ledger_path, staging, receipt_path, catalog_path, out_path):
    manifest = publish_assets.verify_staging(staging)
    ledger = publish_assets.load_ledger(ledger_path)
    receipt = json.loads(Path(receipt_path).read_text())
    plan = publish_assets.plan_uploads(ledger, manifest)
    advanced = publish_assets.advance_ledger(ledger, manifest, receipt, catalog_path)
    write_json(Path(out_path), advanced)
    return advanced, plan


def _read_receipt(path):
    receipt_file = Path(path)
    if not receipt_file.exists():
        return None
    return json.loads(receipt_file.read_text())


def _handler_plan(args):
    plan = plan_publish(args.ledger, args.staging)
    write_json(Path(args.out), plan)
    return {"new": len(plan["new"]), "unchanged": len(plan["unchanged"])}


def _handler_check_upload(args):
    manifest = publish_assets.verify_staging(args.staging)
    check_release_assets(manifest, json.loads(Path(args.assets).read_text()))
    return {"verified": len(manifest["assets"])}


def _handler_snapshot_check(args):
    plan = json.loads(Path(args.plan).read_text())
    changed = snapshot_changed(plan, args.catalog, _read_receipt(args.receipt))
    with Path(args.out).open("a") as output:
        output.write(f"changed={'true' if changed else 'false'}\n")
    return {"changed": changed, "new": len(plan["new"])}


def _handler_check_receipt(args):
    receipt = check_receipt(_read_receipt(args.receipt), args.catalog, args.revision, args.run_id)
    return {"runId": receipt["runId"], "dataRevision": receipt["dataRevision"][:12]}


def _handler_advance(args):
    advanced, plan = advance_ledger_file(args.ledger, args.staging, args.receipt, args.catalog, args.out)
    return {"new": len(plan["new"]), "total": len(advanced["episodes"])}


def _handler_log(args):
    counts = {}
    for pair in args.count or []:
        key, value = pair.split("=", 1)
        try:
            value = int(value)
        except ValueError:
            try:
                value = float(value)
            except ValueError:
                pass
        counts[key] = value
    log_step(args.step, not args.fail, args.seconds, **counts)
    return 1 if args.fail else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    def command(name, handler, step):
        sub = subparsers.add_parser(name)
        sub.set_defaults(handler=handler, step=step)
        return sub

    plan = command("plan", _handler_plan, "ledger-plan")
    plan.add_argument("--ledger", type=Path, required=True)
    plan.add_argument("--staging", type=Path, required=True)
    plan.add_argument("--out", type=Path, required=True)

    check = command("check-upload", _handler_check_upload, "upload-verify")
    check.add_argument("--staging", type=Path, required=True)
    check.add_argument("--assets", type=Path, required=True)

    snap = command("snapshot-check", _handler_snapshot_check, "snapshot-check")
    snap.add_argument("--plan", type=Path, required=True)
    snap.add_argument("--catalog", type=Path, required=True)
    snap.add_argument("--receipt", type=Path)
    snap.add_argument("--out", type=Path, required=True)

    receipt = command("check-receipt", _handler_check_receipt, "receipt-verify")
    receipt.add_argument("--receipt", type=Path, required=True)
    receipt.add_argument("--catalog", type=Path, required=True)
    receipt.add_argument("--revision", required=True)
    receipt.add_argument("--run-id", type=int)

    advance = command("advance", _handler_advance, "ledger-advance")
    advance.add_argument("--ledger", type=Path, required=True)
    advance.add_argument("--staging", type=Path, required=True)
    advance.add_argument("--receipt", type=Path, required=True)
    advance.add_argument("--catalog", type=Path, required=True)
    advance.add_argument("--out", type=Path, required=True)

    log = command("log", _handler_log, None)
    log.add_argument("--step", required=True)
    log.add_argument("--fail", action="store_true")
    log.add_argument("--seconds", type=float, default=0.0)
    log.add_argument("--count", action="append")

    args = parser.parse_args(argv)
    if args.command == "log":
        return _handler_log(args)
    start = time.monotonic()
    try:
        counts = args.handler(args)
    except (OSError, ValueError, KeyError, TypeError) as error:
        log_step(args.step, False, time.monotonic() - start, error=type(error).__name__, detail=str(error))
        return 1
    log_step(args.step, True, time.monotonic() - start, **counts)
    return 0


if __name__ == "__main__":
    sys.exit(main())
