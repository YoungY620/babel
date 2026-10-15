#!/usr/bin/env python3
"""List or download episodes from the Acquired RSS feed.

Usage:
  fetch.py --list [--limit N]
  fetch.py --download <index>     # index from --list
"""
import argparse, json, re, sys, urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

FEED_URL = "https://feeds.transistor.fm/acquired"
ROOT = Path(__file__).resolve().parent.parent
EPISODES = ROOT / "episodes"
ITUNES = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"


def slugify(title: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", title.lower()).strip("-")
    return s[:60]


def load_items():
    with urllib.request.urlopen(FEED_URL) as r:
        ch = ET.parse(r).getroot().find("channel")
    items = []
    for it in ch.findall("item"):
        enc = it.find("enclosure")
        if enc is None:
            continue
        items.append({
            "title": it.findtext("title") or "",
            "pubDate": it.findtext("pubDate") or "",
            "description": re.sub(r"<[^>]+>", "", it.findtext("description") or "").strip(),
            "url": enc.get("url"),
            "bytes": int(enc.get("length", 0)),
            "duration": it.findtext(f"{ITUNES}duration") or "",
        })
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--download", type=int, default=None)
    args = ap.parse_args()

    items = load_items()
    if args.list or args.download is None:
        for i, it in enumerate(items[: args.limit]):
            print(f"{i:3d}  {it['bytes']/1e6:7.1f}MB  {it['duration']:>8}  {it['title']}")
        return

    it = items[args.download]
    slug = slugify(it["title"])
    d = EPISODES / slug
    d.mkdir(parents=True, exist_ok=True)
    meta = {**it, "slug": slug, "source": "https://www.acquired.fm/"}
    (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    out = d / "source.mp3"
    if not out.exists():
        print(f"downloading {it['bytes']/1e6:.1f} MB -> {out}")
        urllib.request.urlretrieve(it["url"], out)
    print(f"OK {d}")


if __name__ == "__main__":
    main()
