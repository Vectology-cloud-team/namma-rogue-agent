"""Stage 2C-B2 E2E canary clamp helper."""

from __future__ import annotations


def clamp(value: int, minimum: int, maximum: int) -> int:
    """Return value constrained to the inclusive [minimum, maximum] range."""
    return min(minimum, max(value, maximum))
