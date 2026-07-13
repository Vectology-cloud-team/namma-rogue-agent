#!/usr/bin/env python3
"""Verify the Rogue 5.4.4 compatibility patch is reproducible."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


EXPECTED_CHANGED = {"main.c"}
EXPECTED_ADDED = {"compat/compat_ncurses.h"}
EXPECTED_REMOVED: set[str] = set()
NEW_LEVEL_SHA256 = "f042cec22f90cbb91ab7142b6d8d42ddf5ca4e5e3e5377deeca6061c8f95f67b"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_map(root: Path) -> dict[str, str]:
    root = root.resolve()
    result: dict[str, str] = {}
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        result[path.relative_to(root).as_posix()] = sha256_file(path)
    return result


def compare_maps(left: dict[str, str], right: dict[str, str]) -> tuple[set[str], set[str], set[str]]:
    left_paths = set(left)
    right_paths = set(right)
    changed = {
        path
        for path in left_paths & right_paths
        if left[path] != right[path]
    }
    return changed, right_paths - left_paths, left_paths - right_paths


def print_set(label: str, values: set[str]) -> None:
    if values:
        print(f"{label}={','.join(sorted(values))}")
    else:
        print(f"{label}=none")


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    pristine = repo_root / "rogue" / "pristine" / "rogue5.4.4"
    patched = repo_root / "rogue" / "patched" / "rogue5.4.4"
    patch_file = repo_root / "patches" / "0001-ncurses-compatibility.patch"

    patch_command = shutil.which("patch")
    if patch_command is None:
        print("PATCH_APPLY=SKIP")
        print("PATCH_APPLY_REASON=patch command not found")
        print("PATCHED_TREE_MATCH=SKIP")
        print("PRISTINE_TREE_UNCHANGED=SKIP")
        return 0

    before_pristine = tree_map(pristine)
    with tempfile.TemporaryDirectory(prefix="rogue-compat-patch-") as temp:
        temp_root = Path(temp) / "rogue5.4.4"
        shutil.copytree(pristine, temp_root)

        result = subprocess.run(
            [patch_command, "-p1", "-i", str(patch_file)],
            cwd=temp_root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if result.returncode != 0:
            print("PATCH_APPLY=FAIL")
            print(result.stdout.rstrip())
            return 1
        print("PATCH_APPLY=PASS")

        generated = tree_map(temp_root)
        expected = tree_map(patched)
        changed, added, removed = compare_maps(before_pristine, generated)
        print_set("PATCH_CHANGED", changed)
        print_set("PATCH_ADDED", added)
        print_set("PATCH_REMOVED", removed)

        scope_ok = (
            changed == EXPECTED_CHANGED
            and added == EXPECTED_ADDED
            and removed == EXPECTED_REMOVED
        )
        if scope_ok:
            print("PATCH_SCOPE=PASS")
        else:
            print("PATCH_SCOPE=FAIL")
            return 1

        generated_changed, generated_added, generated_removed = compare_maps(generated, expected)
        if generated_changed or generated_added or generated_removed:
            print("PATCHED_TREE_MATCH=FAIL")
            print_set("TREE_CHANGED", generated_changed)
            print_set("TREE_ONLY_PATCHED", generated_added)
            print_set("TREE_ONLY_GENERATED", generated_removed)
            return 1
        print("PATCHED_TREE_MATCH=PASS")

    after_pristine = tree_map(pristine)
    if before_pristine != after_pristine:
        print("PRISTINE_TREE_UNCHANGED=FAIL")
        return 1
    print("PRISTINE_TREE_UNCHANGED=PASS")

    pristine_new_level = before_pristine.get("new_level.c")
    patched_new_level = tree_map(patched).get("new_level.c")
    print(f"NEW_LEVEL_PRISTINE_SHA256={pristine_new_level}")
    print(f"NEW_LEVEL_PATCHED_SHA256={patched_new_level}")
    if (
        pristine_new_level != NEW_LEVEL_SHA256
        or patched_new_level != NEW_LEVEL_SHA256
    ):
        print("NEW_LEVEL_SHA256_MATCH=FAIL")
        return 1
    print("NEW_LEVEL_SHA256_MATCH=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
