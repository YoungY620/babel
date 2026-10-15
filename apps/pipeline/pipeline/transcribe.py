#!/usr/bin/env python3
"""Transcribe episodes/<slug>/source.mp3 with faster-whisper -> transcript_en.json/.srt

长音频自动切片并行转录（默认 >15 分钟启用，--jobs 控制并行进程数，
也可用环境变量 TRANSCRIBE_JOBS）。

Usage: transcribe.py <slug> [--model large-v3-turbo] [--jobs N]
"""
import argparse, json, math, os, subprocess, tempfile
from pathlib import Path

# 兼容垫片：faster-whisper 1.2.1 给 av.open 传了 av>=15 已删除的
# metadata_errors 参数，这里剥掉它（语义不变，本就只是抑制元数据告警）
import av as _av
_av_open = _av.open
def _open_strip_metadata_errors(*a, **kw):
    kw.pop("metadata_errors", None)
    return _av_open(*a, **kw)
_av.open = _open_strip_metadata_errors

ROOT = Path(__file__).resolve().parent.parent
CHUNK_LEN = int(os.environ.get("TRANSCRIBE_CHUNK_LEN", "1800"))  # 单片秒数

_model = None


def _init_model(name):
    global _model
    from faster_whisper import WhisperModel
    _model = WhisperModel(name, device="cpu", compute_type="int8")


def _worker(arg):
    path, offset = arg
    segs, _ = _model.transcribe(path, language="en", vad_filter=True)
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
    ap.add_argument("--model", default="large-v3-turbo")
    ap.add_argument("--jobs", type=int,
                    default=int(os.environ.get("TRANSCRIBE_JOBS", "2")))
    args = ap.parse_args()

    d = ROOT / "episodes" / args.slug
    src = d / "source.mp3"
    assert src.exists(), f"missing {src}"

    import mutagen
    dur = mutagen.File(src).info.length
    jobs = args.jobs if dur > 900 else 1
    jobs = max(1, min(jobs, math.ceil(dur / 600)))  # 每片至少 10 分钟才有意义

    if jobs <= 1:
        _init_model(args.model)
        segs = _worker((str(src), 0.0))
    else:
        from concurrent.futures import ProcessPoolExecutor
        with tempfile.TemporaryDirectory() as td:
            subprocess.run(["ffmpeg", "-y", "-i", str(src), "-f", "segment",
                            "-segment_time", str(CHUNK_LEN), "-c", "copy",
                            str(Path(td) / "part%03d.mp3")],
                           check=True, capture_output=True)
            parts = sorted(Path(td).glob("part*.mp3"))
            offsets, t = [], 0.0
            for p in parts:                    # 用各片真实时长算偏移，避免关键帧漂移
                offsets.append(t)
                t += mutagen.File(str(p)).info.length
            print(f"{dur/3600:.1f}h -> {len(parts)} parts x {jobs} workers")
            with ProcessPoolExecutor(max_workers=jobs, initializer=_init_model,
                                     initargs=(args.model,)) as ex:
                results = list(ex.map(_worker,
                                      [(str(p), o) for p, o in zip(parts, offsets)]))
            segs = [s for part in results for s in part]

    segs.sort(key=lambda s: s["start"])
    (d / "transcript_en.json").write_text(json.dumps(segs, ensure_ascii=False, indent=1))
    srt = "\n".join(f"{i+1}\n{fmt_ts(s['start'])} --> {fmt_ts(s['end'])}\n{s['text']}\n"
                    for i, s in enumerate(segs))
    (d / "transcript_en.srt").write_text(srt)
    print(f"OK {len(segs)} segments -> {d}")


if __name__ == "__main__":
    main()
