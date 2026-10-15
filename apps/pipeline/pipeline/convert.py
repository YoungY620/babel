#!/usr/bin/env python3
"""一站式转换入口：fetch（如需）→ transcribe → translate → tts → polish 文字版。

模式：
  convert.py --cycle       # 定时任务用（默认）：按 shows.json 策略选集
                           #   backlog 模式：该节目最新一集未处理的 ×1
                           #   recent  模式：该节目 recent_days 窗口内全部未处理新集
  convert.py --index N --show ID   # 指定节目 + 单集序号
  convert.py --url URL     # 任意视频/音频页面（yt-dlp 抽音轨）
  convert.py --slug SLUG   # 已下载好的单集目录

各阶段幂等：已存在的产物会跳过。完成后跑 build_feed.py 即可发布。
"""
import argparse, json, os, subprocess, sys
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
from fetch import download, get_show, load_items, load_shows, slugify  # noqa: E402

PY = sys.executable


def run(script, *args):
    print(f"\n=== {script} {' '.join(str(a) for a in args)} ===", flush=True)
    subprocess.run([PY, str(ROOT / "pipeline" / script), *[str(a) for a in args]], check=True)


def is_done(slug: str) -> bool:
    return (ROOT / "episodes" / slug / "zh.mp3").exists()


def cycle_targets():
    """按 shows.json 策略返回 [(show, index), ...]"""
    targets = []
    now = datetime.now(timezone.utc)
    for show in load_shows():
        items = load_items(show["rss"])
        mode = show.get("mode", "backlog")
        if mode == "recent":
            cutoff = now - timedelta(days=show.get("recent_days", 8))
            for i, it in enumerate(items):
                try:
                    pub = parsedate_to_datetime(it["pubDate"])
                except (TypeError, ValueError):
                    continue
                if pub >= cutoff and not is_done(slugify(it["title"])):
                    targets.append((show, i))
            print(f"[{show['id']}] recent 窗口内未处理: "
                  f"{sum(1 for s, _ in targets if s['id'] == show['id'])} 集")
        else:  # backlog：最新一集未处理的
            for i, it in enumerate(items):
                if not is_done(slugify(it["title"])):
                    targets.append((show, i))
                    print(f"[{show['id']}] backlog 下一集: [{i}] {it['title']}")
                    break
            else:
                print(f"[{show['id']}] 全部处理完毕")
    return targets


def process(slug: str):
    d = ROOT / "episodes" / slug
    if not (d / "transcript_en.json").exists():
        run("transcribe.py", slug)
    else:
        print("skip transcribe (exists)")
    if not (d / "transcript_zh.json").exists():
        if not os.environ.get("OPENAI_API_KEY"):
            sys.exit("需要 OPENAI_API_KEY 才能翻译（或手工提供 transcript_zh.json）")
        run("translate.py", slug)
    else:
        print("skip translate (exists)")
    if not (d / "zh.mp3").exists():
        run("tts.py", slug)
    else:
        print("skip tts (exists)")
    if not (d / "article_zh.md").exists():
        if os.environ.get("OPENAI_API_KEY"):
            run("polish.py", slug)
        else:
            print("skip polish (no OPENAI_API_KEY，可后续手工按 skills/babel-humanize 补)")
    else:
        print("skip polish (exists)")


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--cycle", "--next", action="store_true")
    g.add_argument("--index", type=int)
    g.add_argument("--url")
    g.add_argument("--slug")
    ap.add_argument("--show", default=None)
    args = ap.parse_args()

    if args.slug:
        slugs = [args.slug]
    elif args.url:
        out = subprocess.run(
            [PY, str(ROOT / "pipeline" / "fetch_video.py"), args.url],
            check=True, capture_output=True, text=True).stdout
        slugs = [Path(out.strip().splitlines()[-1].split()[-1]).name]
    elif args.index is not None:
        if not args.show:
            raise SystemExit("--index 需要 --show <id>")
        slugs = [download(get_show(args.show), args.index)]
    else:  # --cycle / 默认
        targets = cycle_targets()
        if not targets:
            print("本周期没有需要处理的单集")
            sys.exit(0)
        print(f"\n本周期共 {len(targets)} 集待处理")
        slugs = [download(show, i) for show, i in targets]

    for slug in slugs:
        process(slug)

    run("build_feed.py")
    print(f"\nDONE {len(slugs)} 集：{', '.join(slugs)}")
    print("发布：bash pipeline/publish.sh")


if __name__ == "__main__":
    main()
