"""Canary tests for the Stage 2C-B2 E2E workflow."""

from __future__ import annotations

import unittest

from canary.stage2c_b1_clamp import clamp


class Stage2CB2CanaryTests(unittest.TestCase):
    def test_clamps_upper_bound(self) -> None:
        self.assertEqual(clamp(5, 1, 3), 3)

    def test_clamps_lower_bound(self) -> None:
        self.assertEqual(clamp(0, 1, 3), 1)

    def test_keeps_value_inside_range(self) -> None:
        self.assertEqual(clamp(2, 1, 3), 2)


if __name__ == "__main__":
    unittest.main()
