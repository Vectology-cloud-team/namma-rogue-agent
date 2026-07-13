"""Runtime state and episode outcome definitions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .models import InvalidStateTransition


class RuntimeState(str, Enum):
    INIT = "INIT"
    READY = "READY"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    TERMINATED = "TERMINATED"
    FAULTED = "FAULTED"


class EpisodeOutcome(str, Enum):
    NO_OUTCOME = "NO_OUTCOME"
    SUCCESS = "SUCCESS"
    DOMAIN_LOSS = "DOMAIN_LOSS"
    USER_ABORT = "USER_ABORT"
    TIME_LIMIT = "TIME_LIMIT"
    REPLAY_COMPLETE = "REPLAY_COMPLETE"


ALLOWED_TRANSITIONS: dict[RuntimeState, set[RuntimeState]] = {
    RuntimeState.INIT: {RuntimeState.READY},
    RuntimeState.READY: {RuntimeState.RUNNING},
    RuntimeState.RUNNING: {
        RuntimeState.PAUSED,
        RuntimeState.TERMINATED,
        RuntimeState.FAULTED,
    },
    RuntimeState.PAUSED: {
        RuntimeState.RUNNING,
        RuntimeState.TERMINATED,
        RuntimeState.FAULTED,
    },
    RuntimeState.TERMINATED: set(),
    RuntimeState.FAULTED: set(),
}


@dataclass
class RuntimeStateMachine:
    state: RuntimeState = RuntimeState.INIT

    def transition(self, next_state: RuntimeState) -> None:
        allowed = ALLOWED_TRANSITIONS[self.state]
        if next_state not in allowed:
            raise InvalidStateTransition(
                f"invalid RuntimeState transition {self.state.value} -> {next_state.value}"
            )
        self.state = next_state

    @property
    def terminal(self) -> bool:
        return self.state in {RuntimeState.TERMINATED, RuntimeState.FAULTED}
