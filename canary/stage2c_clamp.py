"""Stage 2C-A E2E canary helpers.

This module intentionally contains one small correctness bug for the
AI review and fix-proposal E2E canary. The canary PR is closed without
merge after validation.
"""

from __future__ import annotations


def clamp(value: int, minimum: int, maximum: int) -> int:
    """Return value limited to the inclusive range [minimum, maximum]."""
    return min(minimum, max(value, maximum))
