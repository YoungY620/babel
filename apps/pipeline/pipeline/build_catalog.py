#!/usr/bin/env python3
"""Export verified episodes to a fresh publication directory, then validate it.

web.json supplies reviewed bilingual title, summary and article fields. Missing
metadata excludes an episode; no source transcript, cache or credential is copied.
"""
import argparse
import json
import math
import shutil
import subprocess
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

from tts import is_current

REPO = Path(__file__).resolve().parents[3]
ROOT = REPO / "apps/pipeline"


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def timestamp(seconds):
    milliseconds = math.floor(seconds * 1000 + 0.5)
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    whole, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02}:{minutes:02}:{whole:02}.{milliseconds:03}"


def export_catalog(output, episodes, series, assets, audio_base):
    if output.exists() and any(output.iterdir()):
        raise ValueError("Catalog output directory must be empty")
    output.mkdir(parents=True, exist_ok=True)
    for show in series:
        cover = Path(show["cover"])
        if len(cover.parts) != 2 or cover.parts[0] != "covers" or ".." in cover.parts:
            raise ValueError("Invalid series cover path")
        target = output / cover
        target.parent.mkdir(exist_ok=True)
        shutil.copyfile(assets / cover, target)
    published = []
    for directory in sorted(episodes.iterdir()):
        if not is_current(directory) or not (directory / "web.json").is_file():
            continue
        slug = directory.name
        if not slug or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-" for c in slug):
            raise ValueError("Invalid episode ID")
        meta = json.loads((directory / "meta.json").read_text())
        web = json.loads((directory / "web.json").read_text())
        speech = json.loads((directory / "speech.json").read_text())
        source = json.loads((directory / "transcript_zh.json").read_text())
        show = next(s for s in series if s["id"] == meta["show"])
        # A long source segment can span several generated speech units. Merge
        # those ranges so its English words appear once on the new audio clock.
        groups = []
        for unit in speech["units"]:
            indices = set(unit["source_indices"])
            if groups and indices & groups[-1]["indices"]:
                groups[-1]["indices"].update(indices)
                groups[-1]["end"] = unit["end"]
                groups[-1]["zh"] += unit["text"]
            else:
                groups.append({"start": unit["start"], "end": unit["end"],
                               "speaker": unit["speaker"], "indices": indices, "zh": unit["text"]})
        cues = [{"start": group["start"], "end": group["end"], "speaker": group["speaker"],
                 "text": {"zh-CN": group["zh"],
                          "en": " ".join(source[i]["text"] for i in sorted(group["indices"]))}}
                for group in groups]
        prefix = f"episodes/{slug}"
        detail = {"schemaVersion": 1, "episodeId": slug, "article": web["article"], "cues": cues}
        write_json(output / prefix / "detail.json", detail)
        captions = {}
        for locale in ["zh-CN", "en"]:
            captions[locale] = f"{prefix}/{locale}.vtt"
            blocks = [f"{timestamp(cue['start'])} --> {timestamp(cue['end'])}\n" +
                      cue["text"][locale].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                      .replace("\n", " ").replace("\r", " ") for cue in cues]
            (output / captions[locale]).write_text("WEBVTT\n\n" + "\n\n".join(blocks) + "\n")
        published.append({"id": slug, "seriesId": show["id"], "title": web["title"], "summary": web["summary"],
            "publishedAt": parsedate_to_datetime(meta["pubDate"]).astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "sourceUrl": meta["source"], "cover": show["cover"],
            "audio": {"url": f"{audio_base}/{slug}-zh-{speech['audio_sha256'][:12]}.mp3",
                      "sha256": speech["audio_sha256"], "bytes": speech["audio_bytes"],
                      "durationSeconds": speech["duration_seconds"], "language": "zh-CN", "synthetic": True},
            "quality": {"kind": "verified-podcast", "model": speech["model"],
                        "reviewModel": speech["verification"]["model"],
                        "reviewedUnits": speech["verification"]["reviewed_units"]},
            "detail": f"{prefix}/detail.json", "captions": captions})
    catalog = {"schemaVersion": 1, "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
               "series": series, "episodes": sorted(published, key=lambda episode: episode["publishedAt"], reverse=True)}
    write_json(output / "catalog.json", catalog)
    return catalog


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audio-base", required=True)
    args = parser.parse_args()
    series = json.loads((REPO / "site/series.json").read_text())
    export_catalog(args.output, ROOT / "episodes", series, REPO / "site", args.audio_base)
    subprocess.run(["pnpm", "--filter", "@babel/catalog", "validate", str(args.output.resolve())], cwd=REPO, check=True)


if __name__ == "__main__":
    main()
