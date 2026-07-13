"""Rogue-specific runtime adapter boundary."""

from .adapter import RogueDomainAdapter
from .backend import RogueNativeBackend
from .fake_backend import FakeRogueNativeBackend
from .models import (
    ROGUE_ACTION_TYPES,
    ROGUE_DIRECTIONS,
    RogueNativeConfig,
    RogueNativeObservation,
    RoguePosition,
    RogueResetResult,
    RogueSourceIdentity,
    RogueVisibleCell,
)

__all__ = [
    "FakeRogueNativeBackend",
    "ROGUE_ACTION_TYPES",
    "ROGUE_DIRECTIONS",
    "RogueDomainAdapter",
    "RogueNativeBackend",
    "RogueNativeConfig",
    "RogueNativeObservation",
    "RoguePosition",
    "RogueResetResult",
    "RogueSourceIdentity",
    "RogueVisibleCell",
]
