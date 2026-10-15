#!/usr/bin/env python3
"""Transcribe episodes/<slug>/source.mp3 with faster-whisper -> transcript_en.json/.srt

长音频自动切片并行转录（默认 >15 分钟启用，--jobs 控制并行进程数，
也可用环境变量 TRANSCRIBE_JOBS）。

Usage: transcribe.py <slug> [--model large-v3-turbo] [--jobs N]
"""
import argparse, json, math, os, subprocess, tempfile, shutil
from tts import digest, file_hash, save
from paths import episode_directory
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHUNK_LEN = int(os.environ.get("TRANSCRIBE_CHUNK_LEN", "1800"))  # 单片秒数

_model = None


def source_plan(directory, model=None):
    return {"version": 1, "audio": file_hash(directory / "source.mp3"),
            "model": model or os.environ.get("RAW_ASR_MODEL", "large-v3-turbo"),
            "chunk_seconds": CHUNK_LEN, "language": "en", "vad": True, "beam_size": 5}


def raw_digest(segments):
    return digest([{key: row[key] for key in ["start", "end", "text"]} for row in segments])


def is_current(directory, model=None):
    try:
        report = json.loads((directory / "transcribe.json").read_text())
        return (isinstance(report, dict) and report.get("plan") == source_plan(directory, model)
                and report.get("rawSha256") == raw_digest(json.loads((directory / "transcript_en.json").read_text())))
    except (OSError, ValueError, KeyError, TypeError):
        return False


def _init_model(name):
    global _model
    from faster_whisper import WhisperModel
    _model = WhisperModel(name, device="cpu", compute_type="int8",
                          cpu_threads=int(os.environ.get("OMP_NUM_THREADS", "2")))


def _worker(arg):
    path, offset = arg
    segs, _ = _model.transcribe(path, language="en", vad_filter=True, beam_size=5)
    out = []
    for s in segs:
        out.append({"start": s.start + offset, "end": s.end + offset,
                    "text": s.text.strip()})
    print(f"part done: {Path(path).name} ({len(out)} segs)", flush=True)
    return out


def fmt_ts(t: float) -> str:
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02d}:{int(m):02d}:{s:06.3f}".replace(".", ",")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("--model", default=os.environ.get("RAW_ASR_MODEL", "large-v3-turbo"))
    ap.add_argument("--jobs", type=int,
                    default=int(os.environ.get("TRANSCRIBE_JOBS", "1")))
    args = ap.parse_args()

    d = episode_directory(ROOT, args.slug)
    src = d / "source.mp3"
    assert src.exists(), f"missing {src}"

    if is_current(d, args.model):
        print("Verified raw ASR unchanged")
        return
    spec = source_plan(d, args.model)
    (d / "transcribe.json").unlink(missing_ok=True)
    (d / "diarization.json").unlink(missing_ok=True)
    shutil.rmtree(d / "samples", ignore_errors=True)
    parts_root = d / ".transcribe_parts"
    if parts_root.exists():
        try:
            same = json.loads((parts_root / "plan.json").read_text()) == spec
        except (OSError, ValueError):
            same = False
        if not same:
            shutil.rmtree(parts_root)

    import mutagen
    dur = mutagen.File(src).info.length
    jobs = args.jobs if dur > 900 else 1
    jobs = max(1, min(jobs, math.ceil(dur / 600)))  # 每片至少 10 分钟才有意义

    if dur <= 900:
        _init_model(args.model)
        segs = _worker((str(src), 0.0))
    else:
        from concurrent.futures import ProcessPoolExecutor
        parts_dir = d / ".transcribe_parts"      # 逐片落盘，中断可续跑
        if not parts_dir.exists():
            # Expose the chunk set only after FFmpeg has finished every file.
            with tempfile.TemporaryDirectory(prefix=".transcribe_split-", dir=d) as td:
                subprocess.run(["ffmpeg", "-y", "-i", str(src), "-f", "segment",
                                "-segment_time", str(CHUNK_LEN), "-c", "copy",
                                str(Path(td) / "part%03d.mp3")],
                               check=True, capture_output=True)
                save(Path(td) / "plan.json", spec)
                Path(td).rename(parts_dir)
        parts = sorted(parts_dir.glob("part*.mp3"))
        offsets, t = [], 0.0
        for p in parts:                    # 用各片真实时长算偏移，避免关键帧漂移
            offsets.append(t)
            t += mutagen.File(str(p)).info.length
        todo = [(str(p), o) for p, o in zip(parts, offsets)
                if not (parts_dir / (p.stem + ".json")).exists()]
        print(f"{dur/3600:.1f}h -> {len(parts)} parts x {jobs} workers "
              f"(续跑，剩 {len(todo)} 片)")
        if todo:
            with ProcessPoolExecutor(max_workers=jobs, initializer=_init_model,
                                     initargs=(args.model,)) as ex:
                for (p, _), segs_p in zip(todo, ex.map(_worker, todo)):
                    checkpoint = parts_dir / (Path(p).stem + ".json")
                    pending = checkpoint.with_suffix(".json.tmp")
                    pending.write_text(json.dumps(segs_p, ensure_ascii=False))
                    pending.replace(checkpoint)
        segs = [s for p in parts
                for s in json.loads((parts_dir / (p.stem + ".json")).read_text())]

    segs.sort(key=lambda s: s["start"])
    save(d / "transcript_en.json", segs)
    srt = "\n".join(f"{i+1}\n{fmt_ts(s['start'])} --> {fmt_ts(s['end'])}\n{s['text']}\n"
                    for i, s in enumerate(segs))
    (d / "transcript_en.srt").write_text(srt)
    save(d / "transcribe.json", {"plan": spec, "rawSha256": raw_digest(segs)})
    shutil.rmtree(d / ".transcribe_parts", ignore_errors=True)   # 全部完成后清理临时片
    print(f"OK {len(segs)} segments -> {d}")


if __name__ == "__main__":
    main()
