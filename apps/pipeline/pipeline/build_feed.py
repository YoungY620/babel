#!/usr/bin/env python3
"""Build docs/feed.xml (podcast RSS) + docs/index.html (web player)
+ docs/episodes/<slug>.html (中文文字版) from episodes/*.

Reads config.env (apps/pipeline/config.env):
  GITHUB_USER / GITHUB_REPO / SHOW_TITLE / SHOW_AUTHOR / SHOW_EMAIL

Audio URLs point at GitHub Releases assets (rolling tag: audio).

Usage: build_feed.py
"""
import json, html
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

STYLE = """
body{max-width:760px;margin:0 auto;padding:24px;font-family:-apple-system,"PingFang SC",sans-serif;background:#0f1115;color:#e6e6e6;line-height:1.7}
h1{font-size:1.6rem} a{color:#7ab8ff}
.ep{border-top:1px solid #2a2e37;padding:16px 0}
.ep h2{font-size:1.1rem;margin:0 0 4px}
.date{color:#8a8f9a;font-size:.85rem;margin:0 0 8px}
audio{width:100%}
.feed{background:#1a1e26;border-radius:8px;padding:10px 14px;font-size:.9rem;word-break:break-all}
article h1{font-size:1.5rem} article h2{font-size:1.15rem;margin-top:1.8em}
article p{margin:.9em 0}
.back{font-size:.9rem}
"""


def load_config():
    cfg = {}
    p = ROOT / "config.env"
    for line in p.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            cfg[k.strip()] = v.strip().strip('"').strip("'")
    return cfg


def md_to_html(md: str) -> str:
    blocks = []
    for para in md.split("\n\n"):
        para = para.strip()
        if not para:
            continue
        if para.startswith("## "):
            blocks.append(f"<h2>{html.escape(para[3:])}</h2>")
        elif para.startswith("# "):
            blocks.append(f"<h1>{html.escape(para[2:])}</h1>")
        elif para == "---":
            blocks.append("<hr>")
        else:
            blocks.append("<p>" + html.escape(para).replace("\n", "<br>") + "</p>")
    return "\n".join(blocks)


def page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="zh-CN"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<style>{STYLE}</style></head><body>
{body}
</body></html>"""


def main():
    cfg = load_config()
    user, repo = cfg["GITHUB_USER"], cfg["GITHUB_REPO"]
    show_title = cfg.get("SHOW_TITLE", "巴别塔 Babel")
    pages_base = f"https://{user}.github.io/{repo}"
    audio_base = f"https://github.com/{user}/{repo}/releases/download/audio"
    feed_url = f"{pages_base}/feed.xml"

    eps = []
    for d in sorted((ROOT / "episodes").iterdir()):
        meta_p, mp3 = d / "meta.json", d / "zh.mp3"
        if not (meta_p.exists() and mp3.exists()):
            continue
        meta = json.loads(meta_p.read_text())
        meta["zh_bytes"] = mp3.stat().st_size
        meta["article"] = (d / "article_zh.md").read_text() if (d / "article_zh.md").exists() else None
        eps.append(meta)
    eps.sort(key=lambda m: m["pubDate"], reverse=True)

    items_xml = []
    for m in eps:
        title = escape(f"{m['title']}（中文精译）")
        desc = escape(m.get("description", "")[:500])
        url = f"{audio_base}/{m['slug']}-zh.mp3"
        items_xml.append(f"""  <item>
    <title>{title}</title>
    <description>{desc}</description>
    <pubDate>{m['pubDate']}</pubDate>
    <guid isPermaLink="false">{m['slug']}-zh</guid>
    <enclosure url="{url}" length="{m['zh_bytes']}" type="audio/mpeg"/>
    <itunes:author>{escape(cfg.get('SHOW_AUTHOR',''))}</itunes:author>
    <itunes:summary>{desc}</itunes:summary>
  </item>""")

    feed = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"
     xmlns:atom="http://www.w3.org/2005/Atom">
<channel>
  <title>{escape(show_title)}</title>
  <link>{pages_base}</link>
  <atom:link href="{feed_url}" rel="self" type="application/rss+xml"/>
  <language>zh-cn</language>
  <description>{escape(show_title)} — 英文访谈/播客的中文精译音频与文字版</description>
  <itunes:author>{escape(cfg.get('SHOW_AUTHOR', show_title))}</itunes:author>
  <itunes:explicit>false</itunes:explicit>
  <itunes:owner><itunes:email>{escape(cfg.get('SHOW_EMAIL',''))}</itunes:email></itunes:owner>
{chr(10).join(items_xml)}
</channel>
</rss>
"""
    DOCS.mkdir(exist_ok=True)
    (DOCS / "feed.xml").write_text(feed)

    # 文字版页面
    art_dir = DOCS / "episodes"
    for m in eps:
        if not m["article"]:
            continue
        art_dir.mkdir(exist_ok=True)
        body = (f'<p class="back"><a href="../index.html">← 全部单集</a></p>\n'
                f"<article>{md_to_html(m['article'])}</article>")
        (art_dir / f"{m['slug']}.html").write_text(page(f"{m['title']} · 文字版", body))

    rows = []
    for m in eps:
        url = f"{audio_base}/{m['slug']}-zh.mp3"
        art = (f' · <a href="episodes/{m["slug"]}.html">文字版</a>'
               if m["article"] else "")
        rows.append(f"""<div class="ep">
  <h2>{html.escape(m['title'])}</h2>
  <p class="date">{html.escape(m['pubDate'])} · 原片 {m.get('duration','')}{art}</p>
  <audio controls preload="none" src="{url}"></audio>
  <p>{html.escape(m.get('description','')[:200])}</p>
</div>""")
    index_body = f"""<h1>{html.escape(show_title)}</h1>
<p>英文访谈/播客的中文精译：音频 + 文字版。用任意播客客户端（小宇宙 / Apple Podcasts / Overcast…）订阅 RSS：</p>
<p class="feed">{feed_url}</p>
{''.join(rows)}"""
    (DOCS / "index.html").write_text(page(show_title, index_body))
    print(f"OK {len(eps)} episodes ({sum(1 for m in eps if m['article'])} with articles) -> {DOCS}")


if __name__ == "__main__":
    main()
