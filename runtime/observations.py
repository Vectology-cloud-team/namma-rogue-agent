"""Observation boundary dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import JsonValue, json_compatible


@dataclass(frozen=True)
class DomainState:
    domain_name: str
    payload: dict[str, JsonValue]

    def to_json_data(self) -> dict[str, JsonValue]:
        return {
            "domain_name": self.domain_name,
            "payload": json_compatible(self.payload),
        }


@dataclass(frozen=True)
class AgentObservation:
    schema_version: str
    episode_id: str
    turn: int
    task: str
    payload: dict[str, JsonValue]
    available_action_types: list[str]

    def to_json_data(self) -> dict[str, JsonValue]:
        return {
            "schema_version": self.schema_version,
            "episode_id": self.episode_id,
            "turn": self.turn,
            "task": self.task,
            "payload": json_compatible(self.payload),
            "available_action_types": list(self.available_action_types),
        }


@dataclass(frozen=True)
class PrivilegedDebugState:
    domain_name: str
    payload: dict[str, JsonValue]

    def to_json_data(self) -> dict[str, JsonValue]:
        return {
            "domain_name": self.domain_name,
            "payload": json_compatible(self.payload),
        }


@dataclass
class EpisodeMemory:
    facts: dict[str, JsonValue] = field(default_factory=dict)

    def update_from_observation(self, observation: AgentObservation) -> None:
        self.facts["last_turn"] = observation.turn
        self.facts["last_task"] = observation.task
        self.facts["last_observation_payload"] = json_compatible(observation.payload)

    def summary(self) -> dict[str, JsonValue]:
        return json_compatible(self.facts)  # type: ignore[return-value]
