"""Rogue native backend Protocol.

The Protocol hides future native transport choices from RuntimeOrchestrator.
Committed blob line counts are guarded by scripts/check_text_files.py.
"""

from __future__ import annotations

from typing import Protocol

from ..actions import ActionResult, RequestedAction, ValidatedAction
from ..determinism import DeterminismContext
from ..domain import DomainTerminalStatus
from ..observations import PrivilegedDebugState
from .models import (
    RogueNativeConfig,
    RogueNativeObservation,
    RogueResetResult,
    RogueSourceIdentity,
)


class RogueNativeBackend(Protocol):
    """Protocol hiding how Rogue is connected to the Python runtime."""

    def create(self, config: RogueNativeConfig) -> None:
        ...

    def reset(self, context: DeterminismContext) -> RogueResetResult:
        ...

    def observe(self) -> RogueNativeObservation:
        ...

    def validate_action(self, action: RequestedAction) -> ValidatedAction:
        ...

    def apply_action(self, action: ValidatedAction, turn: int) -> ActionResult:
        ...

    def terminal_status(self) -> DomainTerminalStatus:
        ...

    def privileged_debug_state(self) -> PrivilegedDebugState:
        ...

    def source_identity(self) -> RogueSourceIdentity:
        ...

    def close(self) -> None:
        ...
