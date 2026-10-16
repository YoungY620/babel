#!/usr/bin/env python3
"""Stage verified episode audio under stable content-addressed names and plan ledger advances.

Nothing is uploaded and no remote state is written. Staged files carry the exact
basename their catalog enclosure URL already publishes, so a private publisher
can verify the publication receipt before uploading anything to the audio release.
"""
import argparse
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from build_catalog import ROOT, write_json
from completion import is_current
from paths import data_root
from tts import file_hash

SCHEMA_VERSION = 1
SHA256 = re.compile(r"[0-9a-f]{64}")
EPISODE_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def asset_name(episode_id, audio_sha256):
    if not EPISODE_ID.fullmatch(episode_id) or not SHA256.fullmatch(audio_sha256):
        raise ValueError("Invalid episode ID or audio digest")
    return f"{episode_id}-zh-{audio_sha256[:12]}.mp3"


def stage_assets(output, episodes):
    if output.exists() and any(output.iterdir()):
        raise ValueError("Asset staging directory must be empty")
    output.mkdir(parents=True, exist_ok=True)
    assets = {}
    for directory in sorted(episodes.glob("*")):
        if not is_current(directory):
            continue
        temporary = output / f".{directory.name}.part"
        try:
            speech = json.loads((directory / "speech.json").read_text())
            name = asset_name(directory.name, speech["audio_sha256"])
            shutil.copyfile(directory / "zh.mp3", temporary)
            digest = file_hash(temporary)
            if digest != speech["audio_sha256"]:
                raise ValueError("Final audio does not match the verified speech manifest")
            staged = output / name
            temporary.replace(staged)
            assets[directory.name] = {"file": name, "sha256": digest, "bytes": staged.stat().st_size,
                                      "durationSeconds": speech["duration_seconds"],
                                      "contentVersion": speech["audio_sha256"]}
        except (OSError, ValueError, KeyError, TypeError):
            temporary.unlink(missing_ok=True)
            print(f"skip unstaged episode: {directory.name}")
    manifest = {"schemaVersion": SCHEMA_VERSION,
                "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "assets": assets}
    write_json(output / "manifest.json", manifest)
    verify_staging(output)
    return manifest


def verify_staging(staging):
    manifest = json.loads((staging / "manifest.json").read_text())
    if not isinstance(manifest, dict) or manifest.get("schemaVersion") != SCHEMA_VERSION \
            or not isinstance(manifest.get("assets"), dict):
        raise ValueError("Invalid asset manifest")
    for episode_id, asset in manifest["assets"].items():
        try:
            stable = asset_name(episode_id, asset["contentVersion"]) == asset["file"]
            staged = staging / asset["file"]
            intact = file_hash(staged) == asset["sha256"] and staged.stat().st_size == asset["bytes"]
        except (OSError, KeyError, TypeError):
            raise ValueError(f"Staged asset does not match the manifest: {episode_id}") from None
        if not stable:
            raise ValueError(f"Manifest entry does not match its stable asset name: {episode_id}")
        if not intact:
            raise ValueError(f"Staged asset does not match the manifest: {asset['file']}")
    return manifest


def load_ledger(path):
    try:
        ledger = json.loads(Path(path).read_text())
    except FileNotFoundError:
        return {"schemaVersion": SCHEMA_VERSION, "episodes": {}}
    if not isinstance(ledger, dict) or ledger.get("schemaVersion") != SCHEMA_VERSION \
            or not isinstance(ledger.get("episodes"), dict):
        raise ValueError("Invalid publication ledger")
    return ledger


def plan_uploads(ledger, manifest):
    new, unchanged = [], []
    for episode_id, asset in sorted(manifest["assets"].items()):
        entry = ledger["episodes"].get(episode_id)
        if entry is None:
            new.append(episode_id)
        elif not isinstance(entry, dict) or entry.get("sha256") != asset["sha256"]:
            raise ValueError(f"Refusing to republish {episode_id}: staged {asset['sha256']} "
                             f"does not match the published ledger entry")
        else:
            unchanged.append(episode_id)
    return {"new": new, "unchanged": unchanged}


def verify_receipt(receipt, catalog_path):
    if isinstance(receipt, (str, Path)):
        receipt = json.loads(Path(receipt).read_text())
    data_revision = receipt.get("dataRevision") if isinstance(receipt, dict) else None
    if not isinstance(receipt, dict) or not SHA256.fullmatch(str(receipt.get("catalogSha256", ""))) \
            or (data_revision is not None and not re.fullmatch(r"[0-9a-f]{40}", str(data_revision))) \
            or file_hash(catalog_path) != receipt["catalogSha256"]:
        raise ValueError("Publication receipt does not match the staged catalog")
    return receipt


def advance_ledger(ledger, manifest, receipt, catalog_path, published_at=None):
    receipt = verify_receipt(receipt, catalog_path)
    episodes = dict(ledger["episodes"])
    stamp = published_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    for episode_id in plan_uploads(ledger, manifest)["new"]:
        asset = manifest["assets"][episode_id]
        episodes[episode_id] = {"contentVersion": asset["contentVersion"], "file": asset["file"],
                                "sha256": asset["sha256"], "bytes": asset["bytes"],
                                "firstPublishedAt": stamp, "dataRevision": receipt.get("dataRevision")}
    return {"schemaVersion": SCHEMA_VERSION, "episodes": episodes}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="Empty asset staging directory")
    args = parser.parse_args()
    manifest = stage_assets(args.output, data_root(ROOT) / "episodes")
    print(f"Staged {len(manifest['assets'])} verified assets with a verified manifest: {args.output}")


if __name__ == "__main__":
    main()
