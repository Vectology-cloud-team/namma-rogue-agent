#!/usr/bin/env python3
"""Check Markdown files for physical-line formatting hazards."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


BIDI_RE = re.compile("[\u061c\u200e\u200f\u202a-\u202e\u2066-\u2069]")
HEADING_RE = re.compile(rb"^(#{1,6})\s+(.+)$")
BULLET_RE = re.compile(r"(^|\s)([-*+]|\d+\.)\s+\S")
DEFAULT_LIMIT = 200


def repo_markdown_files() -> list[Path]:
    paths = [Path("README.md"), Path("AGENTS.md")]
    docs = Path("docs")
    if docs.exists():
        paths.extend(sorted(docs.glob("*.md")))
    return [path for path in paths if path.exists()]


def git_markdown_files(ref: str) -> list[str]:
    proc = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", ref],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return [
        line
        for line in proc.stdout.decode("utf-8").splitlines()
        if line in {"README.md", "AGENTS.md"}
        or (line.startswith("docs/") and line.endswith(".md"))
    ]


def read_worktree(path: Path) -> bytes:
    return path.read_bytes()


def read_git_blob(ref: str, path: str) -> bytes:
    proc = subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return proc.stdout


def line_length(line: bytes) -> int:
    return len(line.decode("utf-8", errors="replace"))


def check_bytes(label: str, data: bytes, limit: int) -> list[str]:
    errors: list[str] = []
    if b"\r\n" in data:
        errors.append(f"{label}: CRLF line endings detected")

    if data:
        raw_lines = data.splitlines()
        if data.endswith((b"\n", b"\r")):
            physical_line_count = len(raw_lines)
        else:
            physical_line_count = len(raw_lines)
    else:
        raw_lines = []
        physical_line_count = 0

    max_length = 0
    max_line = 0
    for index, raw in enumerate(raw_lines, start=1):
        text = raw.decode("utf-8", errors="replace")
        length = line_length(raw)
        if length > max_length:
            max_length = length
            max_line = index
        if length > limit:
            errors.append(f"{label}:{index}: line length {length} exceeds {limit}")
        if BIDI_RE.search(text):
            errors.append(f"{label}:{index}: Unicode bidi control character detected")
        if HEADING_RE.match(raw):
            if re.search(rb"\s#{1,6}\s+\S", raw):
                errors.append(f"{label}:{index}: multiple headings appear on one line")
            if re.search(rb"\s[-*+]\s+\S", raw):
                errors.append(f"{label}:{index}: heading and bullet appear on one line")
        bullet_matches = list(BULLET_RE.finditer(text))
        if len(bullet_matches) > 1:
            errors.append(f"{label}:{index}: multiple bullet markers appear on one line")

    print(f"{label}: lines={physical_line_count} max_line_length={max_length} line={max_line}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--git-ref",
        help="check Markdown blobs from a git ref instead of the working tree",
    )
    parser.add_argument(
        "--max-line-length",
        type=int,
        default=DEFAULT_LIMIT,
        help=f"maximum allowed physical line length, default {DEFAULT_LIMIT}",
    )
    args = parser.parse_args()

    all_errors: list[str] = []
    if args.git_ref:
        for path in git_markdown_files(args.git_ref):
            all_errors.extend(
                check_bytes(
                    f"{args.git_ref}:{path}",
                    read_git_blob(args.git_ref, path),
                    args.max_line_length,
                )
            )
    else:
        for path in repo_markdown_files():
            all_errors.extend(
                check_bytes(str(path).replace("\\", "/"), read_worktree(path), args.max_line_length)
            )

    for error in all_errors:
        print(error, file=sys.stderr)
    return 1 if all_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
