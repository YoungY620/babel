#!/usr/bin/env python3
"""Build docs/feed.xml (podcast RSS) + docs/index.html (按系列切换的播放器)
+ docs/episodes/<slug>.html (中文文字版) + docs/covers/* (封面) from episodes/*.

Reads BABEL_DATA_DIR/config.env and source-controlled shows.json.

Usage: build_feed.py
"""
import json, html, os, urllib.request
from pathlib import Path
from completion import is_current
from paths import data_root
from urllib.parse import urlsplit
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}

STYLE = """
body{max-width:860px;margin:0 auto;padding:24px;font-family:-apple-system,"PingFang SC",sans-serif;background:#0f1115;color:#e6e6e6;line-height:1.7}
h1{font-size:1.6rem} a{color:#7ab8ff}
.tabs{display:flex;gap:8px;flex-wrap:wrap;margin:18px 0}
.tab{padding:8px 18px;border-radius:999px;border:1px solid #2a2e37;background:#161a21;color:#c9ced8;cursor:pointer;font-size:.95rem}
.tab.active{background:#2d4a75;border-color:#2d4a75;color:#fff}
.showhead{display:flex;gap:18px;align-items:flex-start;margin:6px 0 10px}
.cover{width:140px;height:140px;border-radius:12px;object-fit:cover;background:linear-gradient(135deg,#22314b,#161a21);flex:none}
.showhead .desc{color:#aab0bc;font-size:.92rem;margin:.2em 0 0}
.showhead h2{margin:0;font-size:1.25rem}
.ep{border-top:1px solid #2a2e37;padding:16px 0;display:flex;gap:14px}
.ep .thumb{width:72px;height:72px;border-radius:8px;object-fit:cover;background:linear-gradient(135deg,#22314b,#161a21);flex:none}
.ep .body{flex:1;min-width:0}
.ep h3{font-size:1.05rem;margin:0 0 4px}
.date{color:#8a8f9a;font-size:.85rem;margin:0 0 8px}
audio{width:100%}
.feed{background:#1a1e26;border-radius:8px;padding:10px 14px;font-size:.9rem;word-break:break-all}
.support{background:#1a1e26;border-radius:8px;padding:12px 16px;margin:14px 0;font-size:.92rem}
.support a{margin-right:14px}
.support code{display:block;margin-top:8px;font-size:.8rem;color:#c9ced8;word-break:break-all;user-select:all}
article h1{font-size:1.5rem} article h2{font-size:1.15rem;margin-top:1.8em}
article p{margin:.9em 0}
.back{font-size:.9rem}
"""


def load_config():
    cfg = {}
    p = data_root(ROOT) / "config.env"
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


def page(title: str, body: str, prefix: str = "") -> str:
    return f"""<!doctype html>
<html lang="zh-CN"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<link rel="icon" href="{prefix}favicon.svg" type="image/svg+xml">
<link rel="icon" href="{prefix}favicon-32.png" sizes="32x32" type="image/png">
<link rel="apple-touch-icon" href="{prefix}apple-touch-icon.png">
<style>{STYLE}</style></head><body>
{body}
</body></html>"""


def support_html(cfg) -> str:
    """支持位：SUPPORT_LINKS="名称=URL|名称=URL"；
    SUPPORT_SOLANA_PAY=solana:<addr>?...&message=...（附言随 memo program 上链）；
    SUPPORT_CRYPTO="标签:地址"（纯地址展示，EVM 转账无法附言）。"""
    links = cfg.get("SUPPORT_LINKS", "")
    solpay = cfg.get("SUPPORT_SOLANA_PAY", "")
    crypto = cfg.get("SUPPORT_CRYPTO", "")
    if not (links or solpay or crypto):
        return ""
    out = ['<div class="support">☕ 支持这个站点：']
    for part in links.split("|"):
        if "=" in part:
            name, url = part.split("=", 1)
            out.append(f'<a href="{html.escape(url.strip())}">{html.escape(name.strip())}</a>')
    if solpay:
        out.append(f'<a href="{html.escape(solpay.strip())}">加密捐赠（Solana Pay，附言自动上链）</a>')
    if crypto:
        label, _, addr = crypto.partition(":")
        out.append(f"<code>{html.escape(label.strip())}: {html.escape(addr.strip())}</code>")
    out.append("</div>")
    return "".join(out)


def fetch_cover(url: str, base: str):
    """下载封面到 docs/covers/，返回相对路径；失败返回 None。"""
    if not url:
        return None
    ext = os.path.splitext(urlsplit(url).path)[1].lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp"):
        ext = ".jpg"
    dest = DOCS / "covers" / f"{base}{ext}"
    try:
        if not dest.exists():
            dest.parent.mkdir(exist_ok=True)
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as f:
                f.write(r.read())
        return f"covers/{dest.name}"
    except Exception as e:
        print(f"cover fetch failed {url}: {e}")
        return None


def main():
    cfg = load_config()
    user, repo = cfg["GITHUB_USER"], cfg["GITHUB_REPO"]
    show_title = cfg.get("SHOW_TITLE", "巴别塔 Babel")
    pages_base = f"https://{user}.github.io/{repo}"
    audio_base = f"https://github.com/{user}/{repo}/releases/download/audio"
    feed_url = f"{pages_base}/feed.xml"
    shows = json.loads((ROOT / "shows.json").read_text())["shows"]
    show_desc = {s["id"]: s.get("description", "") for s in shows}
    show_names = {s["id"]: s["name"] for s in shows}

    eps = []
    for d in sorted((data_root(ROOT) / "episodes").glob("*")):
        meta_p, mp3 = d / "meta.json", d / "zh.mp3"
        if not (meta_p.exists() and mp3.exists() and is_current(d)):
            continue
        meta = json.loads(meta_p.read_text())
        reviewed = json.loads((d / "web.json").read_text())
        meta["title"] = reviewed["title"]["zh-CN"]
        meta["description"] = reviewed["summary"]["zh-CN"]
        meta["zh_bytes"] = mp3.stat().st_size
        # 内容哈希进文件名：重渲染必换 URL，客户端/CDN 不会拿到旧音频
        speech = json.loads((d / "speech.json").read_text())
        meta["zh_hash"] = speech["audio_sha256"][:12]
        art = d / "article_zh.md"
        meta["article"] = art.read_text() if art.exists() else None
        eps.append(meta)
    eps.sort(key=lambda m: m["pubDate"], reverse=True)

    # 封面：单集图优先，其次系列图；同时保证每个 show 有一张兜底图
    show_cover = {}
    for m in eps:
        sid = m.get("show", "other")
        if m.get("image"):
            m["cover"] = fetch_cover(m["image"], f"{m['slug']}")
        if not m.get("cover"):
            if sid not in show_cover:
                show_cover[sid] = fetch_cover(m.get("show_image", ""), f"show-{sid}")
            m["cover"] = show_cover[sid]

    items_xml = []
    for m in eps:
        title = escape(f"{m['title']}（中文精译）")
        desc = escape("本音频由 AI 合成配音，非原说话人录音。 " + m.get("description", "")[:500])
        url = f"{audio_base}/{m['slug']}-zh-{m['zh_hash']}.mp3"
        items_xml.append(f"""  <item>
    <title>{title}</title>
    <description>{desc}</description>
    <pubDate>{m['pubDate']}</pubDate>
    <guid isPermaLink="false">{m['slug']}-zh</guid>
    <enclosure url="{url}" length="{m['zh_bytes']}" type="audio/mpeg"/>
    <itunes:author>{escape(cfg.get('SHOW_AUTHOR',''))}</itunes:author>
    <itunes:summary>{desc}</itunes:summary>
  </item>""")

    from email.utils import format_datetime
    from datetime import datetime, timezone
    build_date = format_datetime(datetime.now(timezone.utc))
    feed = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"
     xmlns:atom="http://www.w3.org/2005/Atom">
<channel>
  <title>{escape(show_title)}</title>
  <link>{pages_base}</link>
  <atom:link href="{feed_url}" rel="self" type="application/rss+xml"/>
  <language>zh-cn</language>
  <lastBuildDate>{build_date}</lastBuildDate>
  <description>{escape(show_title)} — AI 合成配音的中文音频与文字版</description>
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
    approved_articles = {f"{m['slug']}.html" for m in eps if m["article"]}
    for old in art_dir.glob("*.html"):
        if old.name not in approved_articles:
            old.unlink()
    for m in eps:
        if not m["article"]:
            continue
        art_dir.mkdir(exist_ok=True)
        body = (f'<p class="back"><a href="../index.html">← 全部单集</a></p>\n'
                f"<article>{md_to_html(m['article'])}</article>")
        (art_dir / f"{m['slug']}.html").write_text(
            page(f"{m['title']} · 文字版", body, prefix="../"))

    # 按系列分组（shows.json 顺序优先，其余归 other）
    by_show = {}
    for m in eps:
        by_show.setdefault(m.get("show", "other"), []).append(m)
    order = [s["id"] for s in shows if s["id"] in by_show] + \
            [k for k in by_show if k not in {s["id"] for s in shows}]

    tabs, sections = [], []
    for idx, sid in enumerate(order):
        name = show_names.get(sid) or (by_show[sid][0].get("show_name") or sid)
        active = " active" if idx == 0 else ""
        tabs.append(f'<button class="tab{active}" data-show="{sid}">{html.escape(name)}'
                    f'（{len(by_show[sid])}）</button>')
        ms = by_show[sid]
        head_img = (f'<img class="cover" src="{ms[0]["cover"]}" alt="{html.escape(name)} 封面">'
                    if ms[0].get("cover") else '<div class="cover"></div>')
        desc = show_desc.get(sid) or (ms[0].get("show_description") or "")[:300]
        rows = []
        for m in ms:
            url = f"{audio_base}/{m['slug']}-zh-{m['zh_hash']}.mp3"
            art = (f' · <a href="episodes/{m["slug"]}.html">文字版</a>' if m["article"] else "")
            thumb = (f'<img class="thumb" src="{m["cover"]}" alt="" loading="lazy">'
                     if m.get("cover") else '<div class="thumb"></div>')
            rows.append(f"""<div class="ep">
  {thumb}
  <div class="body">
    <h3>{html.escape(m['title'])}</h3>
    <p class="date">{html.escape(m['pubDate'])} · 原片 {m.get('duration','')}{art}</p>
    <audio controls preload="metadata" src="{url}"></audio>
  </div>
</div>""")
        style = "" if idx == 0 else ' style="display:none"'
        sections.append(f"""<section id="show-{sid}"{style}>
  <div class="showhead">{head_img}<div><h2>{html.escape(name)}</h2>
  <p class="desc">{html.escape(desc)}</p></div></div>
  {''.join(rows)}
</section>""")

    index_body = f"""<h1>{html.escape(show_title)}</h1>
<p>本音频由 AI 合成配音，非原说话人录音。</p>
<p>英文访谈/播客的中文精译：音频 + 文字版。用任意播客客户端（小宇宙 / Apple Podcasts / Overcast…）订阅 RSS：</p>
<p class="feed">{feed_url}</p>
{support_html(cfg)}
<div class="tabs">{''.join(tabs)}</div>
{''.join(sections)}
<p class="date" style="margin-top:24px">内容构建于 {build_date} · 共 {len(eps)} 集 · 每次转换周期结束后自动更新</p>
<script>
document.querySelectorAll('.tab').forEach(b => b.addEventListener('click', () => {{
  document.querySelectorAll('.tab').forEach(x => x.classList.toggle('active', x === b));
  document.querySelectorAll('section[id^="show-"]').forEach(s =>
    s.style.display = s.id === 'show-' + b.dataset.show ? '' : 'none');
}}));
</script>"""
    (DOCS / "index.html").write_text(page(show_title, index_body))
    n_art = sum(1 for m in eps if m["article"])
    print(f"OK {len(eps)} episodes ({n_art} with articles, {len(order)} shows) -> {DOCS}")


if __name__ == "__main__":
    main()
