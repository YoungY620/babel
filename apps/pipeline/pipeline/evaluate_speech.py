#!/usr/bin/env python3
"""Evaluate preset speech on original test text; never publish or change episodes."""
import argparse
import json
import os
import time
from pathlib import Path

from provider import json_request
from tts import AUDIO_MODEL, MODEL, PRESETS, render, save

TEXT = ("这家公司在二零二五年增长了百分之十二点五，但利润没有同步提高。为什么？"
        "关键不只在销量，还在现金流。请注意，银行的行长重新调整了预算。"
        "项目仍然需要一步一步地推进。接下来，我们先看事实，再讨论不同的选择。")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    key = os.environ["OPENAI_API_KEY"]
    vendor = next((name for prefix, name in [("sk-or-", "openrouter"), ("sk-proj-", "openai"),
                  ("sk-svcacct-", "openai"), ("nvapi-", "nvidia"), ("sk-kimi-", "kimi")]
                  if key.strip().startswith(prefix)), "unknown")
    report = {"credential_provider_hint": vendor, "credential_has_whitespace": key != key.strip(),
              "credential_has_bearer_prefix": key.strip().lower().startswith("bearer "), "voices": []}
    save(args.output / "evaluation.json", report)
    try:
        available = {m["id"] for m in json_request("models")["data"]}
    except RuntimeError as error:
        report["provider_error"] = str(error)
        save(args.output / "evaluation.json", report)
        print(json.dumps(report), flush=True)
        raise
    candidates = [MODEL, AUDIO_MODEL, "gpt-transcribe", "gpt-4o-transcribe-diarize", "gpt-6.1-sol", "gpt-6-sol", "gpt-5.5"]
    report["available_models"] = {m: m in available for m in candidates}
    save(args.output / "evaluation.json", report)
    for voice in PRESETS:
        directory = args.output / voice
        directory.mkdir(exist_ok=True)
        started = time.monotonic()
        result = {"voice": voice}
        try:
            rendered = render(directory, [{"speaker": "SPEAKER_00", "text_zh": TEXT}], voice)
            result.update(passed=True, output_seconds=rendered["duration_seconds"],
                          loudness_lufs=rendered["loudness_lufs"], true_peak_dbtp=rendered["true_peak_dbtp"])
        except (RuntimeError, ValueError, KeyError) as error:
            result.update(passed=False, error=str(error))
        result["wall_seconds"] = time.monotonic() - started
        report["voices"].append(result)
        save(args.output / "evaluation.json", report)
        print(json.dumps(result, ensure_ascii=False), flush=True)
    if not all(v["passed"] for v in report["voices"]):
        raise SystemExit("Every enabled preset must pass the speech evaluation")


if __name__ == "__main__":
    main()
