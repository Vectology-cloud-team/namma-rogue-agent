"""Trusted source syntax checks that do not write bytecode."""

from __future__ import annotations

import unittest

from support_paths import iter_python_files, worktree_root


class CompileAllChecks(unittest.TestCase):
    def test_python_sources_compile(self) -> None:
        root = worktree_root()
        failures: list[str] = []
        for path in iter_python_files(root):
            relative = path.relative_to(root).as_posix()
            try:
                source = path.read_text(encoding="utf-8")
                compile(source, relative, "exec")
            except SyntaxError as exc:
                failures.append(f"{relative}: {exc.msg} at line {exc.lineno}")
        self.assertEqual([], failures)
