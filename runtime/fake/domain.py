"""A tiny deterministic DomainAdapter used only for runtime tests."""

from __future__ import annotations

from dataclasses import dataclass

from ..actions import (
    ActionResult,
    ActionStatus,
    RequestedAction,
    ValidatedAction,
    ValidationStatus,
)
from ..determinism import DeterminismContext
from ..domain import DomainResetResult, DomainTerminalStatus
from ..observations import AgentObservation, DomainState, PrivilegedDebugState
from ..state import EpisodeOutcome


FAKE_ACTIONS = ("GO_RIGHT", "GO_LEFT", "WAIT", "BUMP")


@dataclass
class FakeDomainAdapter:
    success_position: int = 3
    loss_position: int = -2
    max_turns: int = 10

    position: int = 0
    turn_count: int = 0
    hidden_nonce: int = 0

    def reset(self, context: DeterminismContext) -> DomainResetResult:
        self.position = 0
        self.turn_count = 0
        self.hidden_nonce = (context.world_seed * 31 + context.episode_seed * 17) % 997
        return DomainResetResult(
            domain_state=self._domain_state(),
            domain_events=["fake_domain_reset"],
        )

    def observe(self, episode_id: str, turn: int) -> AgentObservation:
        return AgentObservation(
            schema_version="runtime.observation.v1",
            episode_id=episode_id,
            turn=turn,
            task="reach_success_position",
            payload={
                "position": self.position,
                "success_position": self.success_position,
                "loss_position": self.loss_position,
                "turn_count": self.turn_count,
                "max_turns": self.max_turns,
            },
            available_action_types=list(FAKE_ACTIONS),
        )

    def validate_action(self, action: RequestedAction) -> ValidatedAction:
        if not isinstance(action.action_type, str) or not action.action_type:
            return ValidatedAction(
                requested_action=action,
                normalized_parameters={},
                validation_status=ValidationStatus.REJECTED_SCHEMA,
                message="action_type is required",
            )
        if action.action_type not in FAKE_ACTIONS:
            return ValidatedAction(
                requested_action=action,
                normalized_parameters={},
                validation_status=ValidationStatus.REJECTED_SCHEMA,
                message=f"unsupported fake action {action.action_type}",
            )
        return ValidatedAction(
            requested_action=action,
            normalized_parameters={},
            validation_status=ValidationStatus.VALID,
        )

    def apply_action(self, action: ValidatedAction, turn: int) -> ActionResult:
        action_id = f"turn-{turn}"
        if not action.accepted:
            status = (
                ActionStatus.REJECTED_OBSERVABLE_RULE
                if action.validation_status is ValidationStatus.REJECTED_OBSERVABLE_RULE
                else ActionStatus.REJECTED_SCHEMA
            )
            return ActionResult(
                action_id=action_id,
                status=status,
                message=action.message,
                domain_events=["action_rejected"],
            )

        action_type = action.requested_action.action_type
        events: list[str] = []
        status = ActionStatus.SUCCESS
        message = "ok"

        if action_type == "GO_RIGHT":
            self.position += 1
            events.append("moved_right")
        elif action_type == "GO_LEFT":
            self.position -= 1
            events.append("moved_left")
        elif action_type == "WAIT":
            events.append("waited")
        elif action_type == "BUMP":
            status = ActionStatus.ATTEMPT_FAILED_IN_DOMAIN
            message = "bump failed inside domain"
            events.append("bump_failed")

        self.turn_count = turn + 1
        terminal = self.terminal_status()
        if terminal.terminal:
            status = ActionStatus.DOMAIN_TERMINAL
            message = terminal.reason
            events.append(terminal.outcome.value)

        return ActionResult(
            action_id=action_id,
            status=status,
            message=message,
            domain_events=events,
            terminal=terminal.terminal,
        )

    def terminal_status(self) -> DomainTerminalStatus:
        if self.position >= self.success_position:
            return DomainTerminalStatus(
                terminal=True,
                outcome=EpisodeOutcome.SUCCESS,
                reason="success position reached",
            )
        if self.position <= self.loss_position:
            return DomainTerminalStatus(
                terminal=True,
                outcome=EpisodeOutcome.DOMAIN_LOSS,
                reason="loss position reached",
            )
        if self.turn_count >= self.max_turns:
            return DomainTerminalStatus(
                terminal=True,
                outcome=EpisodeOutcome.TIME_LIMIT,
                reason="turn limit reached",
            )
        return DomainTerminalStatus(terminal=False)

    def privileged_debug_state(self) -> PrivilegedDebugState:
        return PrivilegedDebugState(
            domain_name="fake",
            payload={
                "position": self.position,
                "turn_count": self.turn_count,
                "hidden_nonce": self.hidden_nonce,
                "success_position": self.success_position,
                "loss_position": self.loss_position,
                "max_turns": self.max_turns,
                "replay_verification_state": self.replay_verification_state(),
            },
        )

    def replay_verification_state(self) -> dict[str, int]:
        return {
            "position": self.position,
            "turn_count": self.turn_count,
            "hidden_nonce": self.hidden_nonce,
        }

    def _domain_state(self) -> DomainState:
        return DomainState(
            domain_name="fake",
            payload={
                "position": self.position,
                "turn_count": self.turn_count,
                "hidden_nonce": self.hidden_nonce,
            },
        )
