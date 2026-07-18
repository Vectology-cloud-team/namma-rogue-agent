"""Trusted Stage 2C-focused unittest discovery wrapper."""

from __future__ import annotations

import unittest

from support_paths import worktree_root


def load_tests(
    loader: unittest.TestLoader,
    tests: unittest.TestSuite,
    pattern: str,
) -> unittest.TestSuite:
    del tests, pattern
    return loader.discover(
        start_dir=str(worktree_root() / "tests"),
        pattern="test_stage2c*.py",
    )
