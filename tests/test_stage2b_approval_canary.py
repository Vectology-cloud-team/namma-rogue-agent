from __future__ import annotations

import unittest

from canary.stage2b_approval_canary import clamp


class Stage2BApprovalCanaryTests(unittest.TestCase):
    def test_clamp_preserves_in_range_value(self):
        self.assertEqual(5, clamp(5, 0, 10))


if __name__ == "__main__":
    unittest.main()
