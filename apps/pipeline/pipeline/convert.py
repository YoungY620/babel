#!/usr/bin/env python3
"""一站式转换入口：fetch（如需）→ transcribe → translate → tts。

模式：
  convert.py --next        # 定时任务用：取 RSS 里最新一集尚未处理的
  convert.py --index N     # 按 RSS 单集序号（fetch.py --list 里的编号）
  convert.py --url URL     # 任意视频/音频页面（yt-dlp 抽音轨）
  convert.py --slug SLUG   # 已下载好的单集目录

各阶段幂等：已存在的产物会跳过。完成后跑 build_feed.py 即可发布。
"""
import argparse, json, os, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
from fetch import load_items, slugify  # noqa: E402

PY = sys.executable


def run(script, *args):
    print(f"\n=== {script} {' '.join(str(a) for a in args)} ===", flush=True)
    subprocess.run([PY, str(ROOT / "pipeline" / script), *[str(a) for a in args]], check=True)


def resolve_slug(args) -> str:
    if args.slug:
        return args.slug
    if args.url:
        out = subprocess.run(
            [PY, str(ROOT / "pipeline" / "fetch_video.py"), args.url],
            check=True, capture_output=True, text=True).stdout
        return Path(out.strip().splitlines()[-1].split()[-1]).name
    items = load_items()
    if args.index is not None:
        run("fetch.py", "--download", args.index)
        return slugify(items[args.index]["title"])
    # --next：最新优先，找第一个还没有 zh.mp3 的
    for i, it in enumerate(items):
        slug = slugify(it["title"])
        if not (ROOT / "episodes" / slug / "zh.mp3").exists():
            print(f"next unprocessed: [{i}] {it['title']} ({it['duration']}s)")
            run("fetch.py", "--download", i)
            return slug
    print("所有单集都已处理完毕")
    sys.exit(0)


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--next", action="store_true")
    g.add_argument("--index", type=int)
    g.add_argument("--url")
    g.add_argument("--slug")
    args = ap.parse_args()
    if not any([args.next, args.index is not None, args.url, args.slug]):
        args.next = True

    slug = resolve_slug(args)
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

    run("build_feed.py")
    print(f"\nDONE {slug} -> {d / 'zh.mp3'}")
    print("发布：bash pipeline/publish.sh")


if __name__ == "__main__":
    main()
