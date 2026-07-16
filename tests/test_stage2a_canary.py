"""Intentional Stage 2A canary failure for fix proposal E2E verification."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


CANARY_PATH = Path(__file__).resolve().parents[1] / "canary" / "stage2a_clamp.py"


def load_canary_module():
    spec = importlib.util.spec_from_file_location("stage2a_clamp_canary", CANARY_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load the Stage 2A canary module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Stage2ACanaryClampTests(unittest.TestCase):
    def test_clamp_keeps_value_inside_range(self) -> None:
        canary = load_canary_module()

        self.assertEqual(5, canary.clamp(5, 1, 10))


if __name__ == "__main__":
    unittest.main()
