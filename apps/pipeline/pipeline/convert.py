#!/usr/bin/env python3
"""一站式转换入口：fetch（如需）→ transcribe → translate → tts → polish 文字版。

模式：
  convert.py --cycle       # 定时任务用（默认）：全部未处理单集（最新优先），
                           #   联合上限——仅当 总时长>8h 且 集数>5 时才截断
  convert.py --index N --show ID   # 指定节目 + 单集序号
  convert.py --url URL     # 任意视频/音频页面（yt-dlp 抽音轨）
  convert.py --slug SLUG   # 已下载好的单集目录

各阶段幂等：已存在的产物会跳过。完成后跑 build_feed.py 即可发布。
"""
import argparse, json, os, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
from fetch import download, get_show, load_items, load_shows, slugify  # noqa: E402

PY = sys.executable


def run(script, *args):
    print(f"\n=== {script} {' '.join(str(a) for a in args)} ===", flush=True)
    env = dict(os.environ)
    env.setdefault("OMP_NUM_THREADS", "2")   # 限制每个 CPU 重任务的线程数，控制总资源
    subprocess.run([PY, str(ROOT / "pipeline" / script), *[str(a) for a in args]],
                   check=True, env=env)


def is_done(slug: str) -> bool:
    from tts import is_current
    directory = ROOT / "episodes" / slug
    return is_current(directory) and (directory / "article_zh.md").exists()


CAP_HOURS, CAP_COUNT = 8, 5


def parse_duration(d) -> float:
    """itunes:duration -> 秒。兼容 秒数 / MM:SS / HH:MM:SS。"""
    d = str(d or "").strip()
    if not d:
        return 0.0
    try:
        return float(d)
    except ValueError:
        sec = 0.0
        for p in d.split(":"):
            sec = sec * 60 + float(p)
        return sec


def cycle_targets():
    """本周期批次：全部未处理单集（各节目最新优先），联合上限——
    仅当 总时长 > 8h 且 集数 > 5 时才拒收（即 ≤5 集时长不限，或 ≤8h 集数不限）。"""
    batch, total_h = [], 0.0
    for show in load_shows():
        try:
            items = load_items(show["rss"])
        except Exception as e:                      # 单个节目源故障不拖垮整个周期
            print(f"[{show['id']}] RSS 拉取失败，本周期跳过: {e}")
            continue
        added = 0
        for i, it in enumerate(items):
            if is_done(slugify(it["title"])):
                continue
            cand_h = total_h + parse_duration(it["duration"]) / 3600
            cand_n = len(batch) + 1
            if cand_h > CAP_HOURS and cand_n > CAP_COUNT:
                continue
            batch.append((show, i))
            total_h, added = cand_h, added + 1
        print(f"[{show['id']}] 本周期入选 {added} 集")
    print(f"批次合计 {len(batch)} 集 ≈ {total_h:.1f} 小时")
    return batch


def process(slug: str):
    d = ROOT / "episodes" / slug
    if not (d / "transcript_en.json").exists():
        run("transcribe.py", slug)
    else:
        print("skip transcribe (exists)")
    if not (d / "diarization.json").exists():
        run("diarize.py", slug)
    else:
        print("skip diarize (exists)")
    if not (d / "samples").is_dir() or not any((d / "samples").glob("*.wav")):
        run("samples.py", slug)
    else:
        print("skip samples (exists)")
    zh_p = d / "transcript_zh.json"
    zh_done = zh_p.exists() and all(
        s.get("text_zh") for s in json.loads(zh_p.read_text()))
    if not zh_done:
        if not os.environ.get("OPENAI_API_KEY"):
            sys.exit("需要 OPENAI_API_KEY 才能翻译（或手工提供 transcript_zh.json）")
        run("translate.py", slug)
    else:
        print("skip translate (exists)")
    run("tts.py", slug)  # Model/text/voice fingerprints decide whether audio can be reused.
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
    g.add_argument("--cycle", action="store_true")
    g.add_argument("--index", type=int)
    g.add_argument("--url")
    g.add_argument("--slug")
    ap.add_argument("--show", default=None)
    ap.add_argument("--workers", type=int,
                    default=int(os.environ.get("CONVERT_WORKERS", "1")),
                    help="并行处理的集数（每集内部转录再切片并行，注意总资源）")
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

    if len(slugs) > 1 and args.workers > 1:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        print(f"并行处理 {len(slugs)} 集（workers={args.workers}）")
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = {ex.submit(process, s): s for s in slugs}
            for f in as_completed(futs):
                f.result()          # 任一集失败立即抛出，终止本周期
                print(f"episode done: {futs[f]}", flush=True)
    else:
        for slug in slugs:
            process(slug)

    run("build_feed.py")
    print(f"\nDONE {len(slugs)} 集：{', '.join(slugs)}")
    print("发布：bash pipeline/publish.sh")

if __name__ == "__main__":
    main()
