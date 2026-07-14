"""Rogue-specific runtime adapter boundary.

This package contains Phase 8 Python-only adapter code. It does not load a
real Rogue shared library and does not modify Rogue 5.4.4 game code.
"""

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
