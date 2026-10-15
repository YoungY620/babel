#!/usr/bin/env python3
"""Transcribe episodes/<slug>/source.mp3 with faster-whisper -> transcript_en.json/.srt

Usage: transcribe.py <slug> [--model large-v3-turbo]
"""
import argparse, json
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


def fmt_ts(t: float) -> str:
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02d}:{int(m):02d}:{s:06.3f}".replace(".", ",")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("--model", default="large-v3-turbo")
    args = ap.parse_args()

    d = ROOT / "episodes" / args.slug
    src = d / "source.mp3"
    assert src.exists(), f"missing {src}"

    from faster_whisper import WhisperModel
    model = WhisperModel(args.model, device="cpu", compute_type="int8")
    segments, info = model.transcribe(str(src), language="en", vad_filter=True)

    segs = []
    for s in segments:
        segs.append({"start": s.start, "end": s.end, "text": s.text.strip()})
        print(f"\r{len(segs)} segments, t={s.end:.0f}s", end="", flush=True)
    print()

    (d / "transcript_en.json").write_text(json.dumps(segs, ensure_ascii=False, indent=1))
    srt = "\n".join(f"{i+1}\n{fmt_ts(s['start'])} --> {fmt_ts(s['end'])}\n{s['text']}\n"
                    for i, s in enumerate(segs))
    (d / "transcript_en.srt").write_text(srt)
    print(f"OK {len(segs)} segments -> {d}")


if __name__ == "__main__":
    main()
