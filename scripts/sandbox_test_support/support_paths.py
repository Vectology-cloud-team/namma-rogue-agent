"""Trusted helpers for sandbox test support modules."""

from __future__ import annotations

import os
from pathlib import Path


def support_dir() -> Path:
    return Path(__file__).resolve().parent


def worktree_root() -> Path:
    entries = [
        Path(item).resolve()
        for item in os.environ.get("PYTHONPATH", "").split(os.pathsep)
        if item
    ]
    support = support_dir()
    for entry in entries:
        if entry != support and (entry / "tests").is_dir():
            return entry
    raise RuntimeError("sandbox worktree root was not provided on PYTHONPATH")


def iter_python_files(root: Path) -> list[Path]:
    ignored_dirs = {".git", "__pycache__"}
    files: list[Path] = []
    for path in root.rglob("*.py"):
        if any(part in ignored_dirs for part in path.relative_to(root).parts):
            continue
        files.append(path)
    return sorted(files)
