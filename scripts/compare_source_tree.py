#!/usr/bin/env python3
"""Compare two source trees by path and SHA-256."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


DEFAULT_IGNORE_DIRS = {".git", "__pycache__"}
DEFAULT_IGNORE_NAMES = {"config.log", "config.status"}
DEFAULT_IGNORE_SUFFIXES = {".o", ".obj", ".exe"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalized_text_sha256(path: Path) -> str | None:
    data = path.read_bytes()
    if b"\x00" in data:
        return None
    for encoding in ("utf-8", "latin-1"):
        try:
            text = data.decode(encoding)
            normalized = text.replace("\r\n", "\n").replace("\r", "\n")
            return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        except UnicodeDecodeError:
            continue
    return None


def should_ignore(
    rel_path: Path,
    ignored_dirs: set[str],
    ignored_names: set[str],
    ignored_suffixes: set[str],
) -> bool:
    if any(part in ignored_dirs for part in rel_path.parts):
        return True
    if rel_path.name in ignored_names:
        return True
    return rel_path.suffix in ignored_suffixes


def tree_map(root: Path, ignored_dirs: set[str], ignored_names: set[str], ignored_suffixes: set[str]) -> dict[str, dict]:
    root = root.resolve()
    result: dict[str, dict] = {}
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        rel_path = path.relative_to(root)
        if should_ignore(rel_path, ignored_dirs, ignored_names, ignored_suffixes):
            continue
        rel = rel_path.as_posix()
        result[rel] = {
            "size": path.stat().st_size,
            "sha256": sha256_file(path),
            "normalized_text_sha256": normalized_text_sha256(path),
        }
    return result


def compare(left_root: Path, right_root: Path, ignored_dirs: set[str], ignored_names: set[str], ignored_suffixes: set[str]) -> dict:
    left = tree_map(left_root, ignored_dirs, ignored_names, ignored_suffixes)
    right = tree_map(right_root, ignored_dirs, ignored_names, ignored_suffixes)
    left_paths = set(left)
    right_paths = set(right)
    changed = []
    same = []
    same_normalized_text = []

    for path in sorted(left_paths & right_paths):
        if left[path]["sha256"] == right[path]["sha256"]:
            same.append(path)
        elif left[path]["normalized_text_sha256"] == right[path]["normalized_text_sha256"]:
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
        "only_left_count": len(left_paths - right_paths),
        "only_right_count": len(right_paths - left_paths),
        "same": same,
        "same_normalized_text": same_normalized_text,
        "changed": changed,
        "only_left": sorted(left_paths - right_paths),
        "only_right": sorted(right_paths - left_paths),
    }


def write_changed_csv(report: dict, path: Path) -> None:
    fields = [
        "path",
        "left_size",
        "right_size",
        "left_sha256",
        "right_sha256",
        "left_normalized_text_sha256",
        "right_normalized_text_sha256",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(report["changed"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("left_tree", type=Path)
    parser.add_argument("right_tree", type=Path)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--changed-csv-output", type=Path)
    parser.add_argument("--ignore-dir", action="append", default=[])
    parser.add_argument("--ignore-name", action="append", default=[])
    parser.add_argument("--ignore-suffix", action="append", default=[])
    args = parser.parse_args()

    report = compare(
        args.left_tree,
        args.right_tree,
        DEFAULT_IGNORE_DIRS | set(args.ignore_dir),
        DEFAULT_IGNORE_NAMES | set(args.ignore_name),
        DEFAULT_IGNORE_SUFFIXES | set(args.ignore_suffix),
    )
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
