from __future__ import annotations

import unittest

from canary.stage2c_clamp import clamp


class Stage2CCanaryTests(unittest.TestCase):
    def test_clamp_keeps_value_inside_range(self):
        self.assertEqual(5, clamp(5, 0, 10))


if __name__ == "__main__":
    unittest.main()
