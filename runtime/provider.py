"""DecisionProvider Protocol and dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

from .actions import RequestedAction
from .models import JsonValue, json_compatible
from .observations import AgentObservation


class DecisionStatus(str, Enum):
    OK = "OK"
    NO_ACTION = "NO_ACTION"
    INVALID_REQUEST = "INVALID_REQUEST"
    TIMEOUT = "TIMEOUT"
    UNAVAILABLE = "UNAVAILABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


@dataclass(frozen=True)
class DecisionRequest:
    request_id: str
    schema_version: str
    episode_id: str
    turn: int
    task: str
    observation: AgentObservation
    allowed_action_schema: dict[str, JsonValue]
    timeout_budget_ms: int
    memory_summary: dict[str, JsonValue] = field(default_factory=dict)
    plan_context: dict[str, JsonValue] = field(default_factory=dict)
    replay_correlation_id: str = ""
    diagnostics_requested: bool = False

    def to_json_data(self) -> dict[str, JsonValue]:
        return {
            "request_id": self.request_id,
            "schema_version": self.schema_version,
            "episode_id": self.episode_id,
            "turn": self.turn,
            "task": self.task,
            "observation": self.observation.to_json_data(),
            "allowed_action_schema": json_compatible(self.allowed_action_schema),
            "timeout_budget_ms": self.timeout_budget_ms,
            "memory_summary": json_compatible(self.memory_summary),
            "plan_context": json_compatible(self.plan_context),
            "replay_correlation_id": self.replay_correlation_id,
            "diagnostics_requested": self.diagnostics_requested,
        }


@dataclass(frozen=True)
class DecisionResponse:
    request_id: str
    status: DecisionStatus
    requested_action: RequestedAction | None = None
    plan: dict[str, JsonValue] | None = None
    diagnostics: dict[str, JsonValue] = field(default_factory=dict)
    latency_ms: int = 0
    error: str = ""

    def to_json_data(self) -> dict[str, JsonValue]:
        return {
            "request_id": self.request_id,
            "status": self.status.value,
            "requested_action": (
                self.requested_action.to_json_data()
                if self.requested_action is not None
                else None
            ),
            "plan": json_compatible(self.plan) if self.plan is not None else None,
            "diagnostics": json_compatible(self.diagnostics),
            "latency_ms": self.latency_ms,
            "error": self.error,
        }


class DecisionProvider(Protocol):
    def decide(self, request: DecisionRequest) -> DecisionResponse:
        ...
