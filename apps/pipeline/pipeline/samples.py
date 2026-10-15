#!/usr/bin/env python3
"""为每个说话人提取音色选择参考：拼接干净语音，默认 8s、16k 单声道 WAV。

Usage: samples.py <slug> [--seconds 60]
产物: episodes/<slug>/samples/SPEAKER_XX.wav
"""
import argparse, json, subprocess, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("--seconds", type=float, default=8)
    args = ap.parse_args()
    if args.seconds < 2:
        ap.error("--seconds must be at least 2")

    d = ROOT / "episodes" / args.slug
    segs = json.loads((d / "transcript_en.json").read_text())
    src = d / "source.mp3"
    out_dir = d / "samples"
    out_dir.mkdir(exist_ok=True)

    by_speaker = {}
    for s in segs:
        sp = s.get("speaker")
        if sp:
            by_speaker.setdefault(sp, []).append(s)

    for sp, ss in by_speaker.items():
        # 优先用较长的连续语音，参考总长不超过指定时长。
        ss = sorted(ss, key=lambda s: -(s["end"] - s["start"]))
        picked, total = [], 0.0
        for s in ss:
            dur = s["end"] - s["start"]
            if dur < 2.0:
                continue
            clip = {**s, "end": min(s["end"], s["start"] + args.seconds - total)}
            picked.append(clip)
            total += clip["end"] - clip["start"]
            if total >= args.seconds:
                break
        with tempfile.TemporaryDirectory() as td:
            parts = []
            for i, s in enumerate(picked):
                p = Path(td) / f"p{i}.wav"
                subprocess.run(["ffmpeg", "-y", "-ss", f"{s['start']:.3f}",
                                "-to", f"{s['end']:.3f}", "-i", str(src),
                                "-ac", "1", "-ar", "16000", str(p)],
                               check=True, capture_output=True)
                parts.append(p)
            lst = Path(td) / "list.txt"
            lst.write_text("".join(f"file '{p}'\n" for p in parts))
            out = out_dir / f"{sp}.wav"
            subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0",
                            "-i", str(lst), str(out)], check=True, capture_output=True)
        print(f"OK {sp}: {total:.0f}s from {len(picked)} segments -> {out}")


if __name__ == "__main__":
    main()
