#!/usr/bin/env python3
"""Inventory a Rogue source tree without modifying it."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_makefile_sources(path: Path) -> dict[str, list[str]]:
    if not path.exists():
        return {}
    variables: dict[str, list[str]] = {}
    current_name: str | None = None
    current_value: list[str] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.rstrip()
        if current_name is not None:
            more = line.endswith("\\")
            current_value.append(line[:-1] if more else line)
            if not more:
                variables[current_name] = " ".join(current_value).split()
                current_name = None
                current_value = []
            continue
        m = re.match(r"^([A-Z0-9_]+)\s*=\s*(.*)$", line)
        if not m:
            continue
        name, value = m.group(1), m.group(2)
        more = value.endswith("\\")
        if more:
            current_name = name
            current_value = [value[:-1]]
        else:
            variables[name] = value.split()
    return {k: v for k, v in variables.items() if k in {"CFILES", "HDRS", "MISC", "AFILES", "DOCSRC"}}


def inventory(root: Path) -> dict:
    root = root.resolve()
    files = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix()
        if rel.startswith(".git/"):
            continue
        files.append(
            {
                "path": rel,
                "size": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    makefile_vars = parse_makefile_sources(root / "Makefile.in")
    expected = sorted(set(sum(makefile_vars.values(), [])))
    present = {item["path"] for item in files}
    missing = sorted(name for name in expected if name not in present)
    extra = sorted(path for path in present if path not in set(expected))
    return {
        "root": str(root),
        "file_count": len(files),
        "files": files,
        "makefile_variables": makefile_vars,
        "expected_from_makefile": expected,
        "missing_from_makefile": missing,
        "extra_not_in_makefile": extra,
    }


def write_csv(report: dict, path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["path", "size", "sha256"])
        writer.writeheader()
        writer.writerows(report["files"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_tree", type=Path)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--csv-output", type=Path)
    args = parser.parse_args()

    report = inventory(args.source_tree)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if args.csv_output:
        args.csv_output.parent.mkdir(parents=True, exist_ok=True)
        write_csv(report, args.csv_output)

    print(f"root={report['root']}")
    print(f"file_count={report['file_count']}")
    print(f"expected_from_makefile={len(report['expected_from_makefile'])}")
    print(f"missing_from_makefile={len(report['missing_from_makefile'])}")
    print(f"extra_not_in_makefile={len(report['extra_not_in_makefile'])}")
    if report["missing_from_makefile"]:
        print("missing:")
        for item in report["missing_from_makefile"]:
            print(f"  {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
