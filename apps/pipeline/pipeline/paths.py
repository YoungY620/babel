"""Keep private runtime inputs outside disposable source checkouts."""
import os
import re
from pathlib import Path


def data_root(app_root):
    value = os.environ.get("BABEL_DATA_DIR")
    path = Path(value) if value else app_root / ".data"
    if not path.is_absolute():
        raise ValueError("BABEL_DATA_DIR must be an absolute path")
    return path.resolve()


def episode_directory(root, slug):
    if not isinstance(slug, str) or len(slug) > 160 or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
        raise ValueError("Invalid episode ID")
    episodes = (root / "episodes").resolve()
    if not episodes.is_relative_to(root.resolve()):
        raise ValueError("Episode storage escapes the private data directory")
    directory = (episodes / slug).resolve()
    if not directory.is_relative_to(episodes):
        raise ValueError("Invalid episode path")
    return directory
