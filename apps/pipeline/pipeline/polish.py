#!/usr/bin/env python3
"""生成单集的中文文字版（article_zh.md）。

polish.py <slug> [--raw]
  默认：分段合并后经 LLM 润色（需 OPENAI_API_KEY；规则见 skills/babel-humanize）
  --raw：只做结构整理不润色（无 API key 时的兜底）
agent 也可以不按本脚本，直接依据 skills/babel-humanize 手工写出 article_zh.md。
"""
import argparse, json, os, sys, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HUMANIZE_RULES = (ROOT.parent.parent / "skills" / "babel-humanize" / "SKILL.md").read_text()


def merge_paragraphs(segs, target=500):
    paras, cur, n = [], [], 0
    for s in segs:
        t = (s.get("text_zh") or s["text"]).strip()
        cur.append(t)
        n += len(t)
        if n >= target and t.endswith(("。", "！", "？")):
            paras.append("".join(cur)); cur, n = [], 0
    if cur:
        paras.append("".join(cur))
    return paras


def llm_polish(title, paras):
    base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    key = os.environ["OPENAI_API_KEY"]
    model = os.environ.get("POLISH_MODEL") or os.environ.get("TRANSLATE_MODEL", "gpt-4o-mini")
    prompt = (
        "下面是一期播客的中文译文（机器直译的分段文本），节目名：《" + title + "》。\n"
        "请依据以下润色标准，整理成一篇可发布的中文文章（markdown，含 # 标题和 ## 小节）：\n\n"
        + HUMANIZE_RULES
        + "\n\n=== 译文原文 ===\n" + "\n\n".join(paras)
    )
    body = json.dumps({"model": model, "temperature": 0.4,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(f"{base}/chat/completions", data=body, headers={
        "content-type": "application/json", "authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.load(r)["choices"][0]["message"]["content"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("--raw", action="store_true")
    args = ap.parse_args()

    d = ROOT / "episodes" / args.slug
    segs = json.loads((d / "transcript_zh.json").read_text())
    meta = json.loads((d / "meta.json").read_text())
    paras = merge_paragraphs(segs)

    if args.raw or not os.environ.get("OPENAI_API_KEY"):
        md = f"# {meta['title']}（中文文字版）\n\n" + "\n\n".join(paras)
    else:
        md = llm_polish(meta["title"], paras)

    md += f"\n\n---\n原始出处：{meta.get('source') or meta.get('url')}\n"
    (d / "article_zh.md").write_text(md)
    print(f"OK -> {d / 'article_zh.md'}")


if __name__ == "__main__":
    main()
