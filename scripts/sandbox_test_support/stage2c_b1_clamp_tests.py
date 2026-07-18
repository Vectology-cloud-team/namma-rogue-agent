"""Trusted Stage 2C-B2 canary checks for PR #32.

This module lives in the trusted control plane. It is imported through a fixed
PYTHONPATH by the sandbox test workflow and exercises only the canary module
present in the sandbox checkout.
"""

from __future__ import annotations

import unittest

from canary.stage2c_b1_clamp import clamp


class Stage2CB1ClampTests(unittest.TestCase):
    def test_clamps_upper_bound(self) -> None:
        self.assertEqual(clamp(5, 1, 3), 3)

    def test_clamps_lower_bound(self) -> None:
        self.assertEqual(clamp(0, 1, 3), 1)

    def test_keeps_value_inside_range(self) -> None:
        self.assertEqual(clamp(2, 1, 3), 2)


if __name__ == "__main__":
    unittest.main()
