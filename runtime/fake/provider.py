"""Fake deterministic DecisionProvider implementations."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from ..actions import ExecutedAction, RequestedAction
from ..provider import (
    DecisionProvider,
    DecisionRequest,
    DecisionResponse,
    DecisionStatus,
)


@dataclass
class RuleBasedDecisionProvider:
    """Move toward the fake success position deterministically."""

    def decide(self, request: DecisionRequest) -> DecisionResponse:
        position = int(request.observation.payload.get("position", 0))
        success_position = int(request.observation.payload.get("success_position", 0))
        if position < success_position:
            action_type = "GO_RIGHT"
        elif position > success_position:
            action_type = "GO_LEFT"
        else:
            action_type = "WAIT"
        return DecisionResponse(
            request_id=request.request_id,
            status=DecisionStatus.OK,
            requested_action=RequestedAction(
                action_type=action_type,
                parameters={},
                request_id=request.request_id,
            ),
        )


@dataclass
class RecordedDecisionProvider:
    """Return a saved action sequence as a DecisionProvider."""

    actions: Iterable[RequestedAction | ExecutedAction | str]
    _requested_actions: list[RequestedAction] = field(init=False)
    _index: int = 0

    def __post_init__(self) -> None:
        self._requested_actions = [self._coerce_action(action) for action in self.actions]

    def decide(self, request: DecisionRequest) -> DecisionResponse:
        if self._index >= len(self._requested_actions):
            return DecisionResponse(
                request_id=request.request_id,
                status=DecisionStatus.NO_ACTION,
                error="recorded action sequence exhausted",
            )
        recorded = self._requested_actions[self._index]
        self._index += 1
        return DecisionResponse(
            request_id=request.request_id,
            status=DecisionStatus.OK,
            requested_action=RequestedAction(
                action_type=recorded.action_type,
                parameters=dict(recorded.parameters),
                request_id=request.request_id,
            ),
        )

    @staticmethod
    def _coerce_action(action: RequestedAction | ExecutedAction | str) -> RequestedAction:
        if isinstance(action, RequestedAction):
            return action
        if isinstance(action, ExecutedAction):
            return RequestedAction(
                action_type=action.action_type,
                parameters=dict(action.parameters),
                request_id=action.action_id,
            )
        return RequestedAction(action_type=str(action), parameters={}, request_id="")
