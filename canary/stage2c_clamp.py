"""Stage 2C-A stale-head canary helper."""


def clamp(value: int, minimum: int, maximum: int) -> int:
    return min(minimum, max(value, maximum))
