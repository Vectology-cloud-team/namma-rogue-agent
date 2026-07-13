"""Action lifecycle dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .models import JsonValue, json_compatible


class ValidationStatus(str, Enum):
    VALID = "VALID"
    REJECTED_SCHEMA = "REJECTED_SCHEMA"
    REJECTED_OBSERVABLE_RULE = "REJECTED_OBSERVABLE_RULE"


class ActionStatus(str, Enum):
    SUCCESS = "SUCCESS"
    REJECTED_SCHEMA = "REJECTED_SCHEMA"
    REJECTED_OBSERVABLE_RULE = "REJECTED_OBSERVABLE_RULE"
    ATTEMPT_FAILED_IN_DOMAIN = "ATTEMPT_FAILED_IN_DOMAIN"
    DOMAIN_TERMINAL = "DOMAIN_TERMINAL"
    INTERNAL_ERROR = "INTERNAL_ERROR"


@dataclass(frozen=True)
class RequestedAction:
    action_type: str
    parameters: dict[str, JsonValue] = field(default_factory=dict)
    request_id: str = ""

    def to_json_data(self) -> dict[str, JsonValue]:
        return {
            "action_type": self.action_type,
            "parameters": json_compatible(self.parameters),
            "request_id": self.request_id,
        }


@dataclass(frozen=True)
class ValidatedAction:
    requested_action: RequestedAction
    normalized_parameters: dict[str, JsonValue]
    validation_status: ValidationStatus
    message: str = ""

    @property
    def accepted(self) -> bool:
        return self.validation_status is ValidationStatus.VALID

    def to_json_data(self) -> dict[str, JsonValue]:
        return {
            "requested_action": self.requested_action.to_json_data(),
            "normalized_parameters": json_compatible(self.normalized_parameters),
            "validation_status": self.validation_status.value,
            "message": self.message,
        }


@dataclass(frozen=True)
class ExecutedAction:
    action_id: str
    action_type: str
    parameters: dict[str, JsonValue]
    turn: int

    def to_json_data(self) -> dict[str, JsonValue]:
        return {
            "action_id": self.action_id,
            "action_type": self.action_type,
            "parameters": json_compatible(self.parameters),
            "turn": self.turn,
        }


@dataclass(frozen=True)
class ActionResult:
    action_id: str
    status: ActionStatus
    message: str = ""
    domain_events: list[str] = field(default_factory=list)
    terminal: bool = False

    def to_json_data(self) -> dict[str, JsonValue]:
        return {
            "action_id": self.action_id,
            "status": self.status.value,
            "message": self.message,
            "domain_events": list(self.domain_events),
            "terminal": self.terminal,
        }
