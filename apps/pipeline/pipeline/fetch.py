#!/usr/bin/env python3
"""List or download episodes from the show RSS feeds in shows.json.

Usage:
  fetch.py --list [--show ID] [--limit N]
  fetch.py --download <index> --show ID     # index from --list
"""
import argparse, json, re, urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EPISODES = ROOT / "episodes"
ITUNES = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}


def load_shows():
    return json.loads((ROOT / "shows.json").read_text())["shows"]


def get_show(show_id):
    for s in load_shows():
        if s["id"] == show_id:
            return s
    raise SystemExit(f"unknown show: {show_id}（见 shows.json）")


def slugify(title: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", title.lower()).strip("-")
    return s[:60]


def load_feed(rss_url: str):
    """返回 (channel_info, items)。channel_info 含 description/image。"""
    with urllib.request.urlopen(urllib.request.Request(rss_url, headers=UA)) as r:
        ch = ET.parse(r).getroot().find("channel")
    ch_img = ch.find(f"{ITUNES}image")
    if ch_img is None:
        ch_img = ch.find("image/url")
        ch_image = ch_img.text if ch_img is not None else ""
    else:
        ch_image = ch_img.get("href", "")
    channel = {
        "title": ch.findtext("title") or "",
        "description": re.sub(r"<[^>]+>", "", ch.findtext("description") or "").strip(),
        "image": ch_image,
    }
    items = []
    for it in ch.findall("item"):
        enc = it.find("enclosure")
        if enc is None:
            continue
        it_img = it.find(f"{ITUNES}image")
        items.append({
            "title": it.findtext("title") or "",
            "pubDate": it.findtext("pubDate") or "",
            "description": re.sub(r"<[^>]+>", "", it.findtext("description") or "").strip(),
            "url": enc.get("url"),
            "bytes": int(enc.get("length", 0)),
            "duration": it.findtext(f"{ITUNES}duration") or "",
            "image": it_img.get("href", "") if it_img is not None else "",
        })
    return channel, items


def load_items(rss_url: str):
    return load_feed(rss_url)[1]


def download(show, index: int) -> str:
    channel, items = load_feed(show["rss"])
    it = items[index]
    slug = slugify(it["title"])
    d = EPISODES / slug
    d.mkdir(parents=True, exist_ok=True)
    meta = {**it, "slug": slug, "show": show["id"], "source": show["rss"],
            "show_name": channel["title"], "show_description": channel["description"],
            "show_image": channel["image"]}
    (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    out = d / "source.mp3"
    if not out.exists():
        print(f"downloading {it['bytes']/1e6:.1f} MB -> {out}", flush=True)
        req = urllib.request.Request(it["url"], headers=UA)
        with urllib.request.urlopen(req) as r, open(out, "wb") as f:
            while chunk := r.read(1 << 20):
                f.write(chunk)
    print(f"OK {d}")
    return slug


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--show", default=None)
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--download", type=int, default=None)
    args = ap.parse_args()

    if args.download is not None:
        if not args.show:
            raise SystemExit("--download 需要 --show <id>")
        download(get_show(args.show), args.download)
        return

    shows = [get_show(args.show)] if args.show else load_shows()
    for s in shows:
        print(f"\n## {s['name']} ({s['id']})")
        for i, it in enumerate(load_items(s["rss"])[: args.limit]):
            print(f"{i:3d}  {it['bytes']/1e6:7.1f}MB  {it['duration']:>8}  {it['title']}")


if __name__ == "__main__":
    main()
