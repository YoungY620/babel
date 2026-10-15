#!/usr/bin/env python3
"""Chinese TTS for transcript_zh.json -> zh.mp3 using edge-tts (free).

Usage: tts.py <slug> [--voice zh-CN-YunjianNeural] [--rate +10%]
Voices worth trying: zh-CN-YunjianNeural (男), zh-CN-XiaoxiaoNeural (女),
                     zh-CN-YunxiNeural (男, 年轻)
"""
import argparse, asyncio, json, subprocess, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHUNK_CHARS = 1800


async def synth(text: str, voice: str, rate: str, out: Path):
    import edge_tts
    c = edge_tts.Communicate(text, voice, rate=rate)
    with open(out, "wb") as f:
        async for chunk in c.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("--voice", default="zh-CN-YunjianNeural")
    ap.add_argument("--rate", default="+0%")
    args = ap.parse_args()

    d = ROOT / "episodes" / args.slug
    segs = json.loads((d / "transcript_zh.json").read_text())
    texts = [s.get("text_zh") or s["text"] for s in segs]

    chunks, cur, n = [], [], 0
    for t in texts:
        if n + len(t) > CHUNK_CHARS and cur:
            chunks.append("。".join(cur)); cur, n = [], 0
        cur.append(t.rstrip("。.!！")); n += len(t)
    if cur:
        chunks.append("。".join(cur))

    with tempfile.TemporaryDirectory() as td:
        parts = []
        for i, ctext in enumerate(chunks):
            p = Path(td) / f"part{i:04d}.mp3"
            asyncio.run(synth(ctext, args.voice, args.rate, p))
            parts.append(p)
            print(f"\rtts {i+1}/{len(chunks)}", end="", flush=True)
        print()
        lst = Path(td) / "list.txt"
        lst.write_text("".join(f"file '{p}'\n" for p in parts))
        subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                        "-c", "copy", str(d / "zh.mp3")], check=True, capture_output=True)
    print(f"OK -> {d / 'zh.mp3'}")


if __name__ == "__main__":
    main()
