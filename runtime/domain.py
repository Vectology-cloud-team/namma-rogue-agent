"""DomainAdapter Protocol and domain result dataclasses."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .actions import ActionResult, RequestedAction, ValidatedAction
from .determinism import DeterminismContext
from .observations import AgentObservation, DomainState, PrivilegedDebugState
from .state import EpisodeOutcome


@dataclass(frozen=True)
class DomainResetResult:
    domain_state: DomainState
    domain_events: list[str]


@dataclass(frozen=True)
class DomainTerminalStatus:
    terminal: bool
    outcome: EpisodeOutcome = EpisodeOutcome.NO_OUTCOME
    reason: str = ""


class DomainAdapter(Protocol):
    def reset(self, context: DeterminismContext) -> DomainResetResult:
        ...

    def observe(self, episode_id: str, turn: int) -> AgentObservation:
        ...

    def validate_action(self, action: RequestedAction) -> ValidatedAction:
        ...

    def apply_action(self, action: ValidatedAction, turn: int) -> ActionResult:
        ...

    def terminal_status(self) -> DomainTerminalStatus:
        ...

    def privileged_debug_state(self) -> PrivilegedDebugState:
        ...
