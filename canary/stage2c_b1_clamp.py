"""Stage 2C-B1 E2E canary with one intentional correctness bug.

Expected behavior:
- clamp(5, 1, 3) returns 3.
- clamp(0, 1, 3) returns 1.
- clamp(2, 1, 3) returns 2.
"""


def clamp(value: int, minimum: int, maximum: int) -> int:
    """Return value constrained to the inclusive [minimum, maximum] range."""
    return min(minimum, max(value, maximum))
