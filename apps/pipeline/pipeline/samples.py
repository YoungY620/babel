#!/usr/bin/env python3
"""Build source-bound stock-voice references; explicit overrides stay separate."""
import argparse
import json
import math
import re
import tempfile
import wave
from pathlib import Path

from diarize import is_current as speakers_current, read_object
from paths import data_root, episode_directory
from tts import digest, file_hash, save, ffmpeg

ROOT = Path(__file__).resolve().parent.parent


def plan(directory, seconds=None):
    if not speakers_current(directory):
        raise ValueError("Current speaker assignment is required before voice references")
    if seconds is None:
        seconds = read_object(directory / "samples.json").get("seconds", 8)
        if type(seconds) not in (int, float) or not math.isfinite(seconds) or not 2 <= seconds <= 60:
            seconds = 8
    seconds = float(seconds)
    if not math.isfinite(seconds) or not 2 <= seconds <= 60:
        raise ValueError("Reference duration must be finite and between two and sixty seconds")
    rows = json.loads((directory / "transcript_en.json").read_text())
    speakers = sorted({row["speaker"] for row in rows})
    if not speakers or any(not re.fullmatch(r"SPEAKER_\d+", speaker) for speaker in speakers):
        raise ValueError("Invalid speaker identifier")
    return {"version": 1, "source": file_hash(directory / "source.mp3"),
            "transcript": file_hash(directory / "transcript_en.json"), "seconds": seconds,
            "policy": "longest-first/include-short/16k-mono-pcm16/v1", "speakers": speakers,
            "overrides": {speaker: file_hash(directory / "voice-references" / f"{speaker}.wav")
                          for speaker in speakers if (directory / "voice-references" / f"{speaker}.wav").is_file()}}


def valid_wav(path):
    try:
        with wave.open(str(path)) as audio:
            return audio.getnchannels() == 1 and audio.getsampwidth() == 2 and audio.getframerate() == 16000 and audio.getnframes() > 0
    except (OSError, ValueError, wave.Error, EOFError):
        return False


def is_current(directory, seconds=None):
    try:
        report = read_object(directory / "samples.json")
        spec = plan(directory, seconds)
        return (report.get("fingerprint") == digest(spec)
                and all(valid_wav(directory / "samples" / f"{speaker}.wav") and
                        report["files"][speaker] == file_hash(directory / "samples" / f"{speaker}.wav")
                        for speaker in spec["speakers"]))
    except (OSError, ValueError, TypeError, KeyError):
        return False


def prepare(directory, seconds=None):
    if is_current(directory, seconds):
        print("Verified voice references unchanged")
        return
    spec = plan(directory, seconds)
    seconds = spec["seconds"]
    rows = json.loads((directory / "transcript_en.json").read_text())
    output = directory / "samples"
    output.mkdir(exist_ok=True)
    files = {}
    for speaker in spec["speakers"]:
        target = output / f"{speaker}.wav"
        with tempfile.TemporaryDirectory(dir=output, prefix=".sample-") as tmp:
            pending = Path(tmp) / "sample.wav"
            if speaker in spec["overrides"]:
                ffmpeg("-i", directory / "voice-references" / f"{speaker}.wav", "-t", seconds,
                       "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", pending)
            else:
                selected = sorted((row for row in rows if row["speaker"] == speaker),
                                  key=lambda row: -(row["end"] - row["start"]))
                parts, remaining = [], seconds
                for index, row in enumerate(selected):
                    length = min(row["end"] - row["start"], remaining)
                    if length <= 0: break
                    part = Path(tmp) / f"p{index}.wav"
                    ffmpeg("-ss", row["start"], "-i", directory / "source.mp3", "-t", length,
                           "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", part)
                    parts.append(part)
                    remaining -= length
                    if remaining <= 0: break
                # Relative generated names also work when the private data path contains an apostrophe.
                listing = Path(tmp) / "list.txt"
                listing.write_text("".join(f"file '{part.name}'\n" for part in parts))
                ffmpeg("-f", "concat", "-safe", "1", "-i", listing, "-c", "copy", pending)
            if not valid_wav(pending):
                raise ValueError("Voice reference contains no usable speech audio")
            pending.replace(target)
        files[speaker] = file_hash(target)
    save(directory / "samples.json", {"fingerprint": digest(spec), "files": files, "seconds": seconds})
    for old in output.glob("SPEAKER_*.wav"):
        if old.stem not in files:
            old.unlink()
    print(f"Verified {len(files)} voice references")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slug")
    parser.add_argument("--seconds", type=float, help="2–60 seconds; retains a previous explicit value, otherwise 8")
    args = parser.parse_args()
    prepare(episode_directory(data_root(ROOT), args.slug), args.seconds)


if __name__ == "__main__":
    main()
