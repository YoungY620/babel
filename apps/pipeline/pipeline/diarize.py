#!/usr/bin/env python3
"""说话人分离：给 transcript_en.json 的每段打上 speaker 标签。

用 resemblyzer 提取各段声纹嵌入，凝聚聚类成 N 类（默认取 shows.json 里
该节目的 expected_speakers，缺省 2）。结果直接写回 transcript_en.json
（每段加 "speaker": "SPEAKER_00" ...），并输出 diarization.json 摘要。

Usage: diarize.py <slug> [--speakers N]
"""
import argparse, json, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
from fetch import get_show  # noqa: E402


def expected_speakers(slug: str) -> int:
    meta = json.loads((ROOT / "episodes" / slug / "meta.json").read_text())
    try:
        show = get_show(meta.get("show", ""))
        return int(show.get("expected_speakers", 2))
    except SystemExit:
        return 2


def slice_wav(src: Path, start: float, end: float, out: Path):
    subprocess.run(["ffmpeg", "-y", "-ss", f"{start:.3f}", "-to", f"{end:.3f}",
                    "-i", str(src), "-ac", "1", "-ar", "16000", str(out)],
                   check=True, capture_output=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("--speakers", type=int, default=None)
    args = ap.parse_args()

    d = ROOT / "episodes" / args.slug
    segs = json.loads((d / "transcript_en.json").read_text())
    src = d / "source.mp3"
    k = args.speakers or expected_speakers(args.slug)

    import numpy as np
    from resemblyzer import VoiceEncoder, preprocess_wav

    enc = VoiceEncoder()
    embeds = []
    with tempfile.TemporaryDirectory() as td:
        for i, s in enumerate(segs):
            if s["end"] - s["start"] < 0.8:      # 太短的段声纹不稳，跳过
                embeds.append(None)
                continue
            w = Path(td) / f"s{i}.wav"
            slice_wav(src, s["start"], s["end"], w)
            wav = preprocess_wav(w)
            if len(wav) < 4000:
                embeds.append(None)
                continue
            embeds.append(enc.embed_utterance(wav))
            print(f"\rembed {i+1}/{len(segs)}", end="", flush=True)
    print()

    from scipy.cluster.hierarchy import fcluster, linkage
    valid = [i for i, e in enumerate(embeds) if e is not None]
    X = np.stack([embeds[i] for i in valid])
    labels = fcluster(linkage(X, method="ward"), t=k, criterion="maxclust")
    # 按各簇总时长排序，时长最大的叫 SPEAKER_00，依次类推
    from collections import defaultdict
    dur = defaultdict(float)
    for i, lab in zip(valid, labels):
        dur[lab] += segs[i]["end"] - segs[i]["start"]
    order = {lab: n for n, (lab, _) in enumerate(
        sorted(dur.items(), key=lambda kv: -kv[1]))}
    name_of = {lab: f"SPEAKER_{order[lab]:02d}" for lab in dur}

    last = "SPEAKER_00"
    for i, s in enumerate(segs):
        if embeds[i] is not None:
            s["speaker"] = name_of[labels[valid.index(i)]]
            last = s["speaker"]
        else:
            s["speaker"] = last   # 短段归入上一段的说话人

    (d / "transcript_en.json").write_text(json.dumps(segs, ensure_ascii=False, indent=1))
    summary = {name_of[lab]: round(dur[lab] / 60, 1) for lab in dur}
    (d / "diarization.json").write_text(json.dumps(summary, indent=1))
    print(f"OK speakers: {summary} -> {d}")


if __name__ == "__main__":
    main()
