"""Fake Rogue native backend used to test the Rogue adapter boundary.

This backend is deliberately Rogue-shaped but is not a replacement for the
Phase 7 generic fake domain or a connection to Rogue 5.4.4 C code.
"""

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
from ..domain import DomainTerminalStatus
from ..models import DomainAdapterError
from ..observations import PrivilegedDebugState
from ..state import EpisodeOutcome
from .models import (
    PHASE8_SUPPORTED_ACTION_TYPES,
    ROGUE_DIRECTIONS,
    RogueNativeConfig,
    RogueNativeObservation,
    RoguePosition,
    RogueResetResult,
    RogueSourceIdentity,
    RogueVisibleCell,
)


@dataclass(frozen=True)
class RogueNativeActionRecord:
    action_type: str
    direction: str
    turn: int


class FakeRogueNativeBackend:
    """Small deterministic Rogue-shaped backend for adapter tests."""

    width = 5
    height = 5

    def __init__(self) -> None:
        self.created = False
        self.reset_called = False
        self.closed = False
        self.close_count = 0
        self.apply_count = 0
        self.call_log: list[str] = []
        self.applied_actions: list[RogueNativeActionRecord] = []
        self._config = RogueNativeConfig()
        self._context: DeterminismContext | None = None
        self._player = RoguePosition(1, 1)
        self._hp = 12
        self._hp_max = 12
        self._dungeon_level = 1
        self._messages: list[str] = []
        self._terminal = DomainTerminalStatus(False)
        self._turn_count = 0
        self._hidden_cell = RoguePosition(2, 2)
        self._hidden_nonce = 0

    def create(self, config: RogueNativeConfig) -> None:
        self.call_log.append("create")
        self._ensure_open()
        if self.created:
            raise DomainAdapterError("fake Rogue backend was already created")
        self._config = config
        self.created = True

    def reset(self, context: DeterminismContext) -> RogueResetResult:
        self.call_log.append("reset")
        self._ensure_ready()
        self._context = context
        self.reset_called = True
        self.apply_count = 0
        self.applied_actions.clear()
        self._player = RoguePosition(1, 1)
        self._hp = 12
        self._hp_max = 12
        self._dungeon_level = 1
        self._messages = ["You enter a fake Rogue test room."]
        self._terminal = DomainTerminalStatus(False)
        self._turn_count = 0
        self._hidden_nonce = (
            context.world_seed * 31
            + context.episode_seed * 17
        ) % 997
        return RogueResetResult(
            schema_version=self._config.native_schema_version,
        )

    def observe(self) -> RogueNativeObservation:
        self.call_log.append("observe")
        self._ensure_ready()
        visible_cells = tuple(self._visible_cells())
        return RogueNativeObservation(
            schema_version=self._config.native_schema_version,
            dungeon_level=self._dungeon_level,
            player_position=self._player,
            hp=self._hp,
            hp_max=self._hp_max,
            visible_cells=visible_cells,
            recent_message=self._messages[-1] if self._messages else "",
            turn=self._turn_count,
            terminal=self._terminal.terminal,
            terminal_reason=self._terminal.reason,
        )

    def validate_action(self, action: RequestedAction) -> ValidatedAction:
        self.call_log.append("validate_action")
        self._ensure_ready()
        action_type = action.action_type.upper()
        if action_type not in PHASE8_SUPPORTED_ACTION_TYPES:
            return ValidatedAction(
                requested_action=action,
                normalized_parameters={},
                validation_status=ValidationStatus.REJECTED_SCHEMA,
                message=f"unsupported fake Rogue action {action.action_type!r}",
            )
        if self._terminal.terminal:
            return ValidatedAction(
                requested_action=action,
                normalized_parameters={},
                validation_status=ValidationStatus.REJECTED_OBSERVABLE_RULE,
                message="fake Rogue episode is terminal",
            )
        if action_type == "MOVE":
            direction = str(action.parameters.get("direction", "")).upper()
            if direction not in ROGUE_DIRECTIONS or direction == "NONE":
                return ValidatedAction(
                    requested_action=action,
                    normalized_parameters={},
                    validation_status=ValidationStatus.REJECTED_SCHEMA,
                    message="MOVE requires a compass direction",
                )
            return ValidatedAction(
                requested_action=action,
                normalized_parameters={"direction": direction},
                validation_status=ValidationStatus.VALID,
            )
        return ValidatedAction(
            requested_action=action,
            normalized_parameters={},
            validation_status=ValidationStatus.VALID,
        )

    def apply_action(self, action: ValidatedAction, turn: int) -> ActionResult:
        self.call_log.append("apply_action")
        self._ensure_ready()
        if not action.accepted:
            raise DomainAdapterError("fake backend cannot apply rejected action")
        if self._terminal.terminal:
            return ActionResult(
                action_id=f"turn-{turn}",
                status=ActionStatus.DOMAIN_TERMINAL,
                message="fake Rogue episode is already terminal",
                terminal=True,
            )

        action_type = action.requested_action.action_type.upper()
        direction = str(action.normalized_parameters.get("direction", "NONE"))
        self.apply_count += 1
        self.applied_actions.append(
            RogueNativeActionRecord(
                action_type=action_type,
                direction=direction,
                turn=turn,
            )
        )

        if action_type == "WAIT":
            return self._finish_nonterminal_action(
                turn,
                ActionStatus.SUCCESS,
                "You wait.",
                "wait",
            )
        if action_type == "QUIT":
            self._terminal = DomainTerminalStatus(
                terminal=True,
                outcome=EpisodeOutcome.USER_ABORT,
                reason="quit requested",
            )
            self._messages.append("You quit the fake Rogue episode.")
            return ActionResult(
                action_id=f"turn-{turn}",
                status=ActionStatus.DOMAIN_TERMINAL,
                message="quit requested",
                domain_events=["quit"],
                terminal=True,
            )
        if action_type == "MOVE":
            return self._apply_move(direction, turn)

        raise DomainAdapterError(f"unexpected accepted action {action_type!r}")

    def terminal_status(self) -> DomainTerminalStatus:
        self.call_log.append("terminal_status")
        self._ensure_ready()
        return self._terminal

    def privileged_debug_state(self) -> PrivilegedDebugState:
        self.call_log.append("privileged_debug_state")
        self._ensure_ready()
        return PrivilegedDebugState(
            domain_name="rogue",
            payload={
                "hidden_cell": self._hidden_cell.to_json_data(),
                "hidden_nonce": self._hidden_nonce,
                "replay_verification_state": {
                    "player_position": self._player.to_json_data(),
                    "hp": self._hp,
                    "dungeon_level": self._dungeon_level,
                    "terminal": self._terminal.terminal,
                    "outcome": self._terminal.outcome.value,
                    "reason": self._terminal.reason,
                    "turn_count": self._turn_count,
                    "hidden_nonce": self._hidden_nonce,
                },
            },
        )

    def source_identity(self) -> RogueSourceIdentity:
        self.call_log.append("source_identity")
        self._ensure_ready()
        return self._config.source_identity

    def close(self) -> None:
        self.call_log.append("close")
        if self.closed:
            return
        self.close_count += 1
        self.closed = True

    def _apply_move(self, direction: str, turn: int) -> ActionResult:
        target = self._player.moved(direction)
        if self._is_wall(target):
            return self._finish_nonterminal_action(
                turn,
                ActionStatus.ATTEMPT_FAILED_IN_DOMAIN,
                "A wall blocks the way.",
                "move_blocked",
            )

        self._player = target
        if target == RoguePosition(3, 1):
            self._terminal = DomainTerminalStatus(
                terminal=True,
                outcome=EpisodeOutcome.SUCCESS,
                reason="fake exit reached",
            )
            self._messages.append("You find the fake exit.")
            self._turn_count += 1
            return ActionResult(
                action_id=f"turn-{turn}",
                status=ActionStatus.DOMAIN_TERMINAL,
                message="fake exit reached",
                domain_events=["move", "fake_exit"],
                terminal=True,
            )
        if target == RoguePosition(1, 3):
            self._terminal = DomainTerminalStatus(
                terminal=True,
                outcome=EpisodeOutcome.DOMAIN_LOSS,
                reason="fake trap triggered",
            )
            self._messages.append("A fake trap is triggered.")
            self._turn_count += 1
            return ActionResult(
                action_id=f"turn-{turn}",
                status=ActionStatus.DOMAIN_TERMINAL,
                message="fake trap triggered",
                domain_events=["move", "fake_trap"],
                terminal=True,
            )
        return self._finish_nonterminal_action(
            turn,
            ActionStatus.SUCCESS,
            f"You move {direction}.",
            "move",
        )

    def _finish_nonterminal_action(
        self,
        turn: int,
        status: ActionStatus,
        message: str,
        event: str,
    ) -> ActionResult:
        self._messages.append(message)
        self._turn_count += 1
        return ActionResult(
            action_id=f"turn-{turn}",
            status=status,
            message=message,
            domain_events=[event],
            terminal=False,
        )

    def _visible_cells(self) -> list[RogueVisibleCell]:
        cells: list[RogueVisibleCell] = []
        for y in range(self.height):
            for x in range(self.width):
                position = RoguePosition(y, x)
                if position == self._hidden_cell:
                    continue
                if max(abs(position.y - self._player.y), abs(position.x - self._player.x)) > 1:
                    continue
                wall = self._is_wall(position)
                glyph = "@" if position == self._player else ("#" if wall else ".")
                cells.append(
                    RogueVisibleCell(
                        position=position,
                        glyph=glyph,
                        terrain="wall" if wall else "floor",
                        walkable=not wall,
                    )
                )
        return cells

    def _is_wall(self, position: RoguePosition) -> bool:
        return (
            position.y < 0
            or position.x < 0
            or position.y >= self.height
            or position.x >= self.width
            or position.y == 0
            or position.x == 0
            or position.y == self.height - 1
            or position.x == self.width - 1
        )

    def _ensure_ready(self) -> None:
        self._ensure_open()
        if not self.created:
            raise DomainAdapterError("fake Rogue backend has not been created")

    def _ensure_open(self) -> None:
        if self.closed:
            raise DomainAdapterError("fake Rogue backend is closed")
