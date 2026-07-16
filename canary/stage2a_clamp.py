"""Stage 2A fix proposal E2E canary helpers."""


def clamp(value: int, minimum: int, maximum: int) -> int:
    """Return value limited to the inclusive [minimum, maximum] range."""
    return min(minimum, max(value, maximum))
