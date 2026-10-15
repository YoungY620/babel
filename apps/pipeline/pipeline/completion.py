#!/usr/bin/env python3
"""Single publication gate: source-grounded text, reviewed metadata and audio."""
from paths import data_root, episode_directory
import argparse
from pathlib import Path
from polish import is_current as metadata_current
from tts import is_current as speech_current


def is_current(directory):
    return metadata_current(directory) and speech_current(directory)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slug")
    args = parser.parse_args()
    directory = episode_directory(data_root(Path(__file__).resolve().parent.parent), args.slug)
    raise SystemExit(0 if is_current(directory) else 1)
