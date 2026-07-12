#!/usr/bin/env python3
"""Compare two Rogue source trees by path and SHA-256."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


IGNORED_DIRS = {".git", "__pycache__"}
IGNORED_SUFFIXES = {".o", ".obj", ".exe"}
IGNORED_NAMES = {"rogue", "rogue_log.txt", "config.log", "config.status", "Makefile"}


def should_ignore(path: Path) -> bool:
    if any(part in IGNORED_DIRS for part in path.parts):
        return True
    if path.name in IGNORED_NAMES:
        return True
    if path.suffix in IGNORED_SUFFIXES:
        return True
    return False


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def normalized_text_sha256(path: Path) -> str | None:
    data = path.read_bytes()
    if b"\x00" in data:
        return None
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = data.decode("latin-1")
        except UnicodeDecodeError:
            return None
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def tree_map(root: Path) -> dict[str, dict]:
    root = root.resolve()
    result: dict[str, dict] = {}
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel_path = path.relative_to(root)
        if should_ignore(rel_path):
            continue
        rel = rel_path.as_posix()
        result[rel] = {
            "size": path.stat().st_size,
            "sha256": sha256_file(path),
            "normalized_text_sha256": normalized_text_sha256(path),
        }
    return result


def compare(left_root: Path, right_root: Path) -> dict:
    left = tree_map(left_root)
    right = tree_map(right_root)
    left_paths = set(left)
    right_paths = set(right)
    only_left = sorted(left_paths - right_paths)
    only_right = sorted(right_paths - left_paths)
    same = []
    same_normalized_text = []
    changed = []
    for path in sorted(left_paths & right_paths):
        if left[path]["sha256"] == right[path]["sha256"]:
            same.append(path)
        elif (
            left[path]["normalized_text_sha256"] is not None
            and left[path]["normalized_text_sha256"] == right[path]["normalized_text_sha256"]
        ):
            same_normalized_text.append(path)
        else:
            changed.append(
                {
                    "path": path,
                    "left_size": left[path]["size"],
                    "right_size": right[path]["size"],
                    "left_sha256": left[path]["sha256"],
                    "right_sha256": right[path]["sha256"],
                    "left_normalized_text_sha256": left[path]["normalized_text_sha256"],
                    "right_normalized_text_sha256": right[path]["normalized_text_sha256"],
                }
            )
    return {
        "left_root": str(left_root.resolve()),
        "right_root": str(right_root.resolve()),
        "same_count": len(same),
        "same_normalized_text_count": len(same_normalized_text),
        "changed_count": len(changed),
        "only_left_count": len(only_left),
        "only_right_count": len(only_right),
        "same": same,
        "same_normalized_text": same_normalized_text,
        "changed": changed,
        "only_left": only_left,
        "only_right": only_right,
    }


def write_changed_csv(report: dict, path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "path",
                "left_size",
                "right_size",
                "left_sha256",
                "right_sha256",
                "left_normalized_text_sha256",
                "right_normalized_text_sha256",
            ],
        )
        writer.writeheader()
        writer.writerows(report["changed"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("left_tree", type=Path)
    parser.add_argument("right_tree", type=Path)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--changed-csv-output", type=Path)
    args = parser.parse_args()

    report = compare(args.left_tree, args.right_tree)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if args.changed_csv_output:
        args.changed_csv_output.parent.mkdir(parents=True, exist_ok=True)
        write_changed_csv(report, args.changed_csv_output)

    print(f"left={report['left_root']}")
    print(f"right={report['right_root']}")
    print(f"same={report['same_count']}")
    print(f"same_normalized_text={report['same_normalized_text_count']}")
    print(f"changed={report['changed_count']}")
    print(f"only_left={report['only_left_count']}")
    print(f"only_right={report['only_right_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
