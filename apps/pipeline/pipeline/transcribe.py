#!/usr/bin/env python3
"""Transcribe episodes/<slug>/source.mp3 with faster-whisper -> transcript_en.json/.srt

Usage: transcribe.py <slug> [--model large-v3-turbo]
"""
import argparse, json
from pathlib import Path

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
