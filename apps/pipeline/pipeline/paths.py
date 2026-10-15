"""Validate episode paths before reading or removing local artifacts."""

def episode_directory(root, slug):
    directory = (root / "episodes" / slug).resolve()
    if not directory.is_relative_to((root / "episodes").resolve()) or directory == (root / "episodes").resolve():
        raise ValueError("Invalid episode path")
    return directory
