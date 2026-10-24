"""Find importable files only inside a directory the operator selected."""

import os
from pathlib import Path

from app.text_parser import SUPPORTED_TEXT_SUFFIXES


class DirectoryScanError(ValueError):
    """The chosen directory cannot be scanned safely."""


def scan_text_documents(directory: Path) -> list[tuple[str, Path]]:
    """Return (relative POSIX path, absolute path) pairs in a stable order.

    A relative path is the document's identity within this import source. A
    later partial import must never interpret absent files as deletions.
    """
    if directory.is_symlink():
        raise DirectoryScanError("The selected directory must not be a symlink")
    if not directory.is_dir():
        raise DirectoryScanError(f"Not a directory: {directory}")

    root = directory.resolve()
    found: list[tuple[str, Path]] = []

    for current, subdirectories, filenames in os.walk(root, followlinks=False):
        current_path = Path(current)
        for name in subdirectories:
            if (current_path / name).is_symlink():
                raise DirectoryScanError(f"Symlink directory is not allowed: {name}")

        for name in filenames:
            candidate = current_path / name
            if candidate.suffix.lower() not in SUPPORTED_TEXT_SUFFIXES:
                continue
            if candidate.is_symlink():
                raise DirectoryScanError(f"Symlink file is not allowed: {name}")
            resolved = candidate.resolve()
            if not resolved.is_relative_to(root):
                raise DirectoryScanError(f"File escapes the selected directory: {name}")
            relative_path = candidate.relative_to(root).as_posix()
            found.append((relative_path, resolved))

    return sorted(found, key=lambda item: item[0])
