"""Text-level checks for the Phase 8 native ABI specification header.
"""

from __future__ import annotations

from pathlib import Path
import unittest


HEADER = (
    Path(__file__).resolve().parents[1]
    / "adapter/native/include/namma_rogue_api.h"
)


class NativeAbiHeaderTests(unittest.TestCase):
    def test_terminal_kind_does_not_include_runtime_error(self) -> None:
        text = HEADER.read_text(encoding="utf-8")

        self.assertIn("NAMMA_ROGUE_TERMINAL_SAVED", text)
        self.assertNotIn("NAMMA_ROGUE_TERMINAL_RUNTIME_ERROR", text)


if __name__ == "__main__":
    unittest.main()
