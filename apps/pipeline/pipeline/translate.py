#!/usr/bin/env python3
"""Translate transcript_en.json -> transcript_zh.json/.srt via an OpenAI-compatible API.

Env:
  OPENAI_API_KEY   (required)
  OPENAI_BASE_URL  (default https://api.openai.com/v1)
  TRANSLATE_MODEL  (default gpt-4o-mini)

Usage: translate.py <slug>
"""
import argparse, json, os, sys, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHUNK_CHARS = 1500


def fmt_ts(t: float) -> str:
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02d}:{int(m):02d}:{s:06.3f}".replace(".", ",")


def chat(messages):
    base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    key = os.environ["OPENAI_API_KEY"]
    model = os.environ.get("TRANSLATE_MODEL", "gpt-4o-mini")
    body = json.dumps({"model": model, "messages": messages,
                       "temperature": 0.2, "response_format": {"type": "json_object"}}).encode()
    req = urllib.request.Request(f"{base}/chat/completions", data=body, headers={
        "content-type": "application/json", "authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.load(r)["choices"][0]["message"]["content"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    args = ap.parse_args()
    d = ROOT / "episodes" / args.slug
    segs = json.loads((d / "transcript_en.json").read_text())

    zh = [None] * len(segs)
    i = 0
    while i < len(segs):
        chunk, j = [], i
        n = 0
        while j < len(segs) and n + len(segs[j]["text"]) < CHUNK_CHARS:
            chunk.append(segs[j]["text"])
            n += len(segs[j]["text"])
            j += 1
        prompt = ("Translate each English podcast transcript line into natural spoken "
                  "Simplified Chinese, preserving meaning and tone. Keep names/brands in "
                  "original form where common. Return JSON {\"lines\": [...]} with exactly "
                  f"{len(chunk)} entries, aligned 1:1 with the input lines.\n\n"
                  + json.dumps(chunk, ensure_ascii=False))
        out = json.loads(chat([{"role": "user", "content": prompt}]))["lines"]
        assert len(out) == len(chunk), f"alignment mismatch at seg {i}"
        for k, t in enumerate(out):
            zh[i + k] = t
        print(f"\rtranslated {j}/{len(segs)}", end="", flush=True)
        i = j
    print()

    out_segs = [{**s, "text_zh": z} for s, z in zip(segs, zh)]
    (d / "transcript_zh.json").write_text(json.dumps(out_segs, ensure_ascii=False, indent=1))
    srt = "\n".join(f"{i+1}\n{fmt_ts(s['start'])} --> {fmt_ts(s['end'])}\n{s['text_zh']}\n"
                    for i, s in enumerate(out_segs))
    (d / "transcript_zh.srt").write_text(srt)
    print(f"OK -> {d}")


if __name__ == "__main__":
    main()
