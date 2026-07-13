"""Shared runtime errors and JSON helpers."""

from __future__ import annotations

from dataclasses import is_dataclass, asdict
from enum import Enum
from typing import Any


JsonValue = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]


class RuntimeContractError(Exception):
    """Base class for runtime contract failures."""


class InvalidStateTransition(RuntimeContractError):
    """Raised when a RuntimeState transition is not allowed."""


class DomainAdapterError(RuntimeContractError):
    """Raised when a DomainAdapter fails outside normal domain outcome."""


class DecisionProviderError(RuntimeContractError):
    """Raised when a DecisionProvider cannot produce a valid decision."""


class ReplayMismatchError(RuntimeContractError):
    """Raised when replay verification diverges."""


class DeterminismError(RuntimeContractError):
    """Raised when deterministic identity or checksum generation fails."""


def json_compatible(value: Any) -> JsonValue:
    """Convert supported runtime values into JSON-compatible data."""

    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return json_compatible(asdict(value))
    if isinstance(value, dict):
        return {str(key): json_compatible(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_compatible(item) for item in value]
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise TypeError(f"{type(value).__name__} is not JSON-compatible")
