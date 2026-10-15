#!/usr/bin/env python3
"""Source-bound speaker assignment with resumable CPU embeddings."""
import argparse
import json
import math
import tempfile
from collections import defaultdict
from pathlib import Path

from fetch import get_show
from paths import data_root, episode_directory
from transcribe import is_current as raw_current, raw_digest
from tts import digest, file_hash, save, ffmpeg

ROOT = Path(__file__).resolve().parent.parent
MODEL = "resemblyzer-0.1.4"
POLICY = "ward-cut-tree/longest-speaker-first/short-context/v1"


def read_object(path):
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def speaker_count(directory):
    settings = directory / "speaker-input.json"
    if settings.exists():
        value = json.loads(settings.read_text())
        count = value.get("speakers") if isinstance(value, dict) else None
    else:
        meta = json.loads((directory / "meta.json").read_text())
        try:
            count = get_show(meta.get("show", "")).get("expected_speakers", 2)
        except SystemExit:
            count = 2
    if type(count) is not int or count < 1:
        raise ValueError("Speaker count must be a positive integer")
    return count


def plan(directory):
    if not raw_current(directory):
        raise ValueError("Current source-bound raw ASR is required before diarization")
    rows = json.loads((directory / "transcript_en.json").read_text())
    if not rows or any(not (math.isfinite(float(row["start"])) and math.isfinite(float(row["end"]))
                           and 0 <= row["start"] < row["end"]) for row in rows):
        raise ValueError("Invalid source speech timeline")
    return {"version": 1, "source": file_hash(directory / "source.mp3"), "raw": raw_digest(rows),
            "speakers": speaker_count(directory), "model": MODEL, "policy": POLICY}


def is_current(directory):
    try:
        report = read_object(directory / "diarization.json")
        return (report.get("fingerprint") == digest(plan(directory))
                and report.get("transcriptSha256") == file_hash(directory / "transcript_en.json"))
    except (OSError, ValueError, TypeError, KeyError):
        return False


def cluster_labels(embeddings, count):
    if len(embeddings) < 2 or count == 1:
        return [0] * len(embeddings)
    import numpy as np
    from scipy.cluster.hierarchy import cut_tree, linkage
    return [int(label) for label in cut_tree(linkage(np.stack(embeddings), method="ward"),
                                             n_clusters=min(count, len(embeddings))).ravel()]


def assign_speakers(rows, embeddings, count):
    if not rows or len(rows) != len(embeddings) or count < 1:
        raise ValueError("Speaker evidence does not match the source segments")
    valid = [index for index, vector in enumerate(embeddings) if vector is not None]
    labels = cluster_labels([embeddings[index] for index in valid], count)
    known = dict(zip(valid, labels))
    last = labels[0] if labels else 0
    assigned, seconds = [], defaultdict(float)
    for index, row in enumerate(rows):
        last = known.get(index, last)
        assigned.append(last)
        seconds[last] += row["end"] - row["start"]
    names = {label: f"SPEAKER_{index:02d}" for index, label in enumerate(sorted(seconds, key=lambda label: (-seconds[label], label)))}
    return ([{**row, "speaker": names[label]} for row, label in zip(rows, assigned)],
            {names[label]: round(duration, 3) for label, duration in seconds.items()})


def extract_embeddings(directory, rows, spec):
    cache = directory / ".speaker_parts"
    cache.mkdir(exist_ok=True)
    vectors, encoder = [], None
    for index, row in enumerate(rows):
        if row["end"] - row["start"] < .8:
            vectors.append(None)
            continue
        key = digest({"source": spec["source"], "model": MODEL, "start": row["start"], "end": row["end"],
                      "format": "16k-mono/preprocess-v1"})
        path = cache / f"{key}.json"
        record = read_object(path)
        vector = record.get("vector")
        valid = (vector is None or isinstance(vector, list) and len(vector) == 256
                 and all(type(value) in (int, float) and math.isfinite(value) for value in vector))
        if not ("vector" in record and valid and record.get("sha256") == digest(vector)):
            from resemblyzer import VoiceEncoder, preprocess_wav
            with tempfile.TemporaryDirectory(dir=cache, prefix=".embed-") as tmp:
                audio = Path(tmp) / "speech.wav"
                ffmpeg("-ss", row["start"], "-i", directory / "source.mp3", "-t", row["end"] - row["start"],
                       "-ac", "1", "-ar", "16000", audio)
                wav = preprocess_wav(audio)
                vector = None
                if len(wav) >= 4000:
                    if encoder is None:
                        encoder = VoiceEncoder(device="cpu")
                    vector = encoder.embed_utterance(wav).tolist()
            save(path, {"vector": vector, "sha256": digest(vector)})
        vectors.append(vector)
        print(f"Speaker evidence {index + 1}/{len(rows)}", flush=True)
    return vectors


def prepare(directory):
    if is_current(directory):
        print("Verified speaker assignment unchanged")
        return
    spec = plan(directory)
    rows = json.loads((directory / "transcript_en.json").read_text())
    embeddings = extract_embeddings(directory, rows, spec)
    reliable = sum(vector is not None for vector in embeddings)
    assigned, seconds = assign_speakers(rows, embeddings, spec["speakers"])
    save(directory / "transcript_en.json", assigned)
    save(directory / "diarization.json", {"fingerprint": digest(spec), "model": MODEL,
         "transcriptSha256": file_hash(directory / "transcript_en.json"), "speakerSeconds": seconds, "reliableSegments": reliable})
    print(f"Prepared {len(seconds)} speaker groups from {reliable} reliable segments")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slug")
    parser.add_argument("--speakers", help="Positive count override, retained until --speakers auto")
    args = parser.parse_args()
    directory = episode_directory(data_root(ROOT), args.slug)
    if args.speakers == "auto":
        (directory / "speaker-input.json").unlink(missing_ok=True)
    elif args.speakers is not None:
        try:
            count = int(args.speakers)
            if count < 1: raise ValueError()
        except ValueError:
            parser.error("--speakers must be a positive integer or auto")
        save(directory / "speaker-input.json", {"speakers": count})
    prepare(directory)


if __name__ == "__main__":
    main()
