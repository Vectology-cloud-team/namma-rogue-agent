#!/usr/bin/env python3
"""Check source tree completeness against Makefile-style file lists."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


DEFAULT_VARIABLES = ("CFILES", "HDRS", "MISC", "AFILES", "DOCSRC")


def parse_makefile(path: Path, variable_names: set[str]) -> dict[str, list[str]]:
    variables: dict[str, list[str]] = {}
    current_name: str | None = None
    current_value: list[str] = []

    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.rstrip()
        if current_name is not None:
            more = line.endswith("\\")
            current_value.append(line[:-1] if more else line)
            if not more:
                variables[current_name] = " ".join(current_value).split()
                current_name = None
                current_value = []
            continue

        match = re.match(r"^([A-Za-z0-9_]+)\s*=\s*(.*)$", line)
        if not match:
            continue
        name, value = match.group(1), match.group(2)
        if name not in variable_names:
            continue
        more = value.endswith("\\")
        if more:
            current_name = name
            current_value = [value[:-1]]
        else:
            variables[name] = value.split()

    return variables


def check_tree(root: Path, makefile: Path, variables: set[str], required: list[str]) -> dict:
    root = root.resolve()
    makefile = makefile if makefile.is_absolute() else root / makefile
    parsed = parse_makefile(makefile, variables)
    expected = sorted({item for values in parsed.values() for item in values})
    present = sorted(
        item.relative_to(root).as_posix()
        for item in root.rglob("*")
        if item.is_file() and ".git" not in item.relative_to(root).parts
    )
    present_set = set(present)
    expected_set = set(expected)
    required_missing = sorted(item for item in required if item not in present_set)
    return {
        "root": str(root),
        "makefile": str(makefile),
        "variables": parsed,
        "expected_count": len(expected),
        "present_count": len(present),
        "missing_from_makefile": sorted(expected_set - present_set),
        "extra_not_in_makefile": sorted(present_set - expected_set),
        "required_files": required,
        "required_missing": required_missing,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_tree", type=Path)
    parser.add_argument("--makefile", type=Path, default=Path("Makefile.in"))
    parser.add_argument("--variable", action="append", default=list(DEFAULT_VARIABLES))
    parser.add_argument("--required", action="append", default=[])
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()

    report = check_tree(
        args.source_tree,
        args.makefile,
        set(args.variable),
        list(args.required),
    )
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"root={report['root']}")
    print(f"expected_count={report['expected_count']}")
    print(f"present_count={report['present_count']}")
    print(f"missing_from_makefile={len(report['missing_from_makefile'])}")
    print(f"extra_not_in_makefile={len(report['extra_not_in_makefile'])}")
    print(f"required_missing={len(report['required_missing'])}")
    for item in report["missing_from_makefile"]:
        print(f"missing {item}")
    for item in report["required_missing"]:
        print(f"required_missing {item}")

    return 1 if report["missing_from_makefile"] or report["required_missing"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
