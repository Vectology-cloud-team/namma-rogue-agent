from __future__ import annotations


def clamp(value: int, minimum: int, maximum: int) -> int:
    """Return value limited to the inclusive minimum and maximum bounds."""
    if minimum > maximum:
        raise ValueError("minimum must be less than or equal to maximum")
    return min(minimum, max(value, maximum))
