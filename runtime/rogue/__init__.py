"""Rogue-specific runtime adapter boundary.

This package contains the Phase 8 adapter code and the Phase 9A ctypes native
ABI stub backend. It does not load a Rogue 5.4.4-linked shared library and
does not modify Rogue 5.4.4 game code.
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
from .native_backend import (
    CtypesRogueNativeBackend,
    RogueAbiVersionError,
    RogueActionError,
    RogueCloseError,
    RogueCreateError,
    RogueLibraryLoadError,
    RogueNativeBackendError,
    RogueObserveError,
    RogueResetError,
    RogueSourceIdentityError,
    RogueSymbolMissingError,
    RogueTerminalStatusError,
)

__all__ = [
    "CtypesRogueNativeBackend",
    "FakeRogueNativeBackend",
    "ROGUE_ACTION_TYPES",
    "ROGUE_DIRECTIONS",
    "RogueAbiVersionError",
    "RogueActionError",
    "RogueCloseError",
    "RogueCreateError",
    "RogueDomainAdapter",
    "RogueLibraryLoadError",
    "RogueNativeBackend",
    "RogueNativeBackendError",
    "RogueNativeConfig",
    "RogueNativeObservation",
    "RogueObserveError",
    "RoguePosition",
    "RogueResetError",
    "RogueResetResult",
    "RogueSourceIdentityError",
    "RogueSourceIdentity",
    "RogueSymbolMissingError",
    "RogueTerminalStatusError",
    "RogueVisibleCell",
]
