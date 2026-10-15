#!/usr/bin/env python3
"""Fetch the AUDIO TRACK of a video (YouTube/Bilibili/...) via yt-dlp,
so interview videos flow through the same audio-only pipeline.

Usage:
  fetch_video.py <url> [--slug NAME]
"""
import argparse, json, os, re, subprocess, sys
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EPISODES = ROOT / "episodes"

# prefer the yt-dlp living next to the venv python (usually newer than PATH's)
_venv_ytdlp = Path(sys.executable).parent / "yt-dlp"
YTDLP = str(_venv_ytdlp) if _venv_ytdlp.exists() else "yt-dlp"


def slugify(title: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", title.lower()).strip("-")
    return s[:60]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--slug", default=None)
    args = ap.parse_args()

    extra = os.environ.get("YTDLP_EXTRA_ARGS", "").split()  # e.g. --cookies-from-browser chrome

    # 长期 cookies：monorepo 根 secrets/cookies.txt 存在则自动使用
    cookies = ROOT.parent.parent / "secrets" / "cookies.txt"
    if cookies.exists() and "--cookies" not in extra and not any(
            a.startswith("--cookies-from-browser") for a in extra):
        extra = ["--cookies", str(cookies), *extra]

    info = json.loads(subprocess.run(
        [YTDLP, "--dump-json", "--no-playlist", *extra, args.url],
        check=True, capture_output=True, text=True).stdout)

    title = info.get("title", "untitled")
    slug = args.slug or slugify(title)
    d = EPISODES / slug
    d.mkdir(parents=True, exist_ok=True)

    # audio track only -> source.mp3 (voice-grade: mono, speech bitrate)
    subprocess.run([
        YTDLP, "-x", "--audio-format", "mp3", "--audio-quality", "64K",
        "--no-playlist", *extra, "-o", str(d / "source.%(ext)s"), args.url,
    ], check=True)

    upload = info.get("upload_date")  # YYYYMMDD
    if upload:
        dt = datetime.strptime(upload, "%Y%m%d").replace(tzinfo=timezone.utc)
        pub_date = format_datetime(dt)
    else:
        pub_date = format_datetime(datetime.now(timezone.utc))

    dur = info.get("duration") or 0
    meta = {
        "title": title,
        "slug": slug,
        "pubDate": pub_date,
        "description": (info.get("description") or "")[:1000],
        "url": args.url,
        "bytes": (d / "source.mp3").stat().st_size,
        "duration": f"{int(dur//3600)}:{int(dur%3600//60):02d}:{int(dur%60):02d}",
        "source": info.get("webpage_url", args.url),
        "channel": info.get("uploader", ""),
    }
    (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    print(f"OK {d}  ({meta['duration']}, audio track only)")


if __name__ == "__main__":
    main()
