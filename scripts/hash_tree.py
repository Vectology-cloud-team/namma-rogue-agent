#!/usr/bin/env python3
"""Hash every file in a source tree without modifying it."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


DEFAULT_IGNORE_DIRS = {".git", "__pycache__"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def should_ignore(rel_path: Path, ignored_dirs: set[str]) -> bool:
    return any(part in ignored_dirs for part in rel_path.parts)


def hash_tree(root: Path, ignored_dirs: set[str]) -> dict:
    root = root.resolve()
    files = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        rel_path = path.relative_to(root)
        if should_ignore(rel_path, ignored_dirs):
            continue
        files.append(
            {
                "path": rel_path.as_posix(),
                "size": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )

    manifest = "\n".join(
        f"{item['sha256']}  {item['size']}  {item['path']}" for item in files
    )
    return {
        "root": str(root),
        "file_count": len(files),
        "tree_sha256": hashlib.sha256(manifest.encode("utf-8")).hexdigest(),
        "files": files,
    }


def write_csv(report: dict, path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["path", "size", "sha256"])
        writer.writeheader()
        writer.writerows(report["files"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_tree", type=Path)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--csv-output", type=Path)
    parser.add_argument(
        "--ignore-dir",
        action="append",
        default=[],
        help="Directory name to ignore. May be repeated.",
    )
    args = parser.parse_args()

    ignored_dirs = DEFAULT_IGNORE_DIRS | set(args.ignore_dir)
    report = hash_tree(args.source_tree, ignored_dirs)

    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if args.csv_output:
        args.csv_output.parent.mkdir(parents=True, exist_ok=True)
        write_csv(report, args.csv_output)

    print(f"root={report['root']}")
    print(f"file_count={report['file_count']}")
    print(f"tree_sha256={report['tree_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
