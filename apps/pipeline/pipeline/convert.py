#!/usr/bin/env python3
"""Sequential conversion with one wall-clock deadline and resumable stage outputs."""
import argparse, json, math, os, subprocess, sys, tempfile, time
from pathlib import Path
from paths import data_root, episode_directory

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
from fetch import download, get_show, load_items, load_shows, slugify  # noqa: E402
from metrics import append_stage_record  # noqa: E402
from budget import BudgetExpired, remaining, run_command, work_deadline
from preflight import check_provider  # noqa: E402

PY = sys.executable


def record_stage(episode, stage, seconds, ok, **fields):
    try:
        append_stage_record(data_root(ROOT), {
            "episode": episode, "stage": stage,
            "seconds": round(seconds, 3), "ok": ok, **fields,
        })
    except Exception as error:   # metrics 只是观测手段，绝不影响转换主流程
        print(f"stage metrics warning: {error}", file=sys.stderr)


def run(script, *args):
    print(f"\n=== {script} ===", flush=True)
    env = dict(os.environ)
    env.setdefault("OMP_NUM_THREADS", "2")   # 限制每个 CPU 重任务的线程数，控制总资源
    start = time.monotonic()
    ok = False
    try:
        run_command([PY, str(ROOT / "pipeline" / script), *[str(a) for a in args]], env=env)
        ok = True
    finally:
        # process() 总是把 slug 作为第一个参数；build_feed.py 等无参脚本的 episode 记为 null
        record_stage(str(args[0]) if args else None, script, time.monotonic() - start, ok)


def is_done(slug: str) -> bool:
    from completion import is_current
    directory = episode_directory(data_root(ROOT), slug)
    return is_current(directory)


def cycle_targets():
    """Round-robin unfinished sources. No unmeasured audio-hour/episode quota."""
    feeds = []
    for show in load_shows():
        try:
            feeds.append((show, load_items(show["rss"])))
        except BudgetExpired:
            raise
        except Exception:
            print(f"[{show['id']}] Feed unavailable; retained for a later cycle")
    for index in range(max((len(items) for _, items in feeds), default=0)):
        for show, items in feeds:
            if index < len(items) and not is_done(slugify(items[index]["title"])):
                yield show, index


def process(slug: str):
    d = episode_directory(data_root(ROOT), slug)
    from transcribe import is_current as raw_current
    if not raw_current(d):
        run("transcribe.py", slug)
    else:
        print("skip transcribe (exists)")
    from diarize import is_current as speakers_current
    if not speakers_current(d):
        run("diarize.py", slug)
    else:
        print("skip diarize (exists)")
    from tts import voice_mode
    from samples import is_current as references_current
    if voice_mode(d) == "auto" and not references_current(d):
        run("samples.py", slug)
    else:
        print("skip samples (complete or explicit preset)")
    run("translate.py", slug)
    run("polish.py", slug)
    run("tts.py", slug)


def download_target(script, *args):
    root = data_root(ROOT)
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root, prefix='.fetch-') as temporary:
        result = Path(temporary) / 'result.json'
        run_command([PY, str(ROOT / 'pipeline' / script), *map(str, args), '--result', str(result)], capture=True)
        slug = json.loads(result.read_text())['slug']
        episode_directory(root, slug)
        return slug


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--cycle', action='store_true')
    modes.add_argument('--index', type=int)
    modes.add_argument('--url')
    modes.add_argument('--slug')
    parser.add_argument('--show')
    parser.add_argument('--deadline', type=float, default=None, help='Whole-cycle UTC epoch deadline, including publication')
    parser.add_argument('--publish-reserve-seconds', type=float, default=5400)
    args = parser.parse_args()
    deadline = args.deadline if args.deadline is not None else float(os.environ.get('BABEL_CYCLE_DEADLINE', time.time() + 20 * 3600))
    reserve = args.publish_reserve_seconds
    if not math.isfinite(reserve) or reserve < 0 or not math.isfinite(deadline) or deadline > time.time() + 20 * 3600 + 1:
        parser.error('Deadline must be within 20 hours and publication reserve must be finite/nonnegative')
    processing_deadline = deadline - reserve
    previous = os.environ.get('BABEL_PROCESS_DEADLINE')
    os.environ['BABEL_PROCESS_DEADLINE'] = str(processing_deadline)
    try:
        with work_deadline(processing_deadline):
            check_provider()
            if args.slug:
                targets = iter([('slug', args.slug)])
            elif args.url:
                targets = iter([('video', args.url)])
            elif args.index is not None:
                if not args.show:
                    parser.error('--index requires --show')
                targets = iter([('rss', (get_show(args.show), args.index))])
            else:
                targets = (('rss', target) for target in cycle_targets())
            for kind, target in targets:
                remaining(processing_deadline)
                started = time.monotonic()
                if kind == 'slug':
                    slug = target
                elif kind == 'video':
                    slug = download_target('fetch_video.py', target)
                else:
                    show, index = target
                    slug = download_target('fetch.py', '--show', show['id'], '--download', index)
                process(slug)
                from completion import is_current
                directory = episode_directory(data_root(ROOT), slug)
                if not is_current(directory):
                    raise RuntimeError('Processing ended without complete quality checks')
                speech = json.loads((directory / 'speech.json').read_text())
                record_stage(slug, 'processing-complete', time.monotonic() - started, True,
                             outputAudioSeconds=speech['duration_seconds'], episodeCount=1,
                             cpuThreads=int(os.environ.get('OMP_NUM_THREADS', '2')))
    except BudgetExpired:
        print('Processing budget reached; checkpoints retained and time reserved for publication')
    except subprocess.CalledProcessError as error:
        raise SystemExit(f'Pipeline stage failed (exit {error.returncode}); checkpoints retained') from None
    finally:
        if previous is None:
            os.environ.pop('BABEL_PROCESS_DEADLINE', None)
        else:
            os.environ['BABEL_PROCESS_DEADLINE'] = previous


if __name__ == '__main__':
    main()
