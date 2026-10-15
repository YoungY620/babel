#!/usr/bin/env python3
"""Prepare an audio-grounded, reviewed bilingual script from timed raw English ASR."""
from paths import data_root, episode_directory
import argparse
from pathlib import Path
from text_quality import prepare

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slug")
    args = parser.parse_args()
    prepare(episode_directory(data_root(ROOT), args.slug))


if __name__ == "__main__":
    main()
