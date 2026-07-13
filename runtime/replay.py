"""Replay Level 1 event recording."""

from __future__ import annotations

from dataclasses import dataclass, field

from .actions import ActionResult, ExecutedAction
from .determinism import DeterminismContext
from .models import JsonValue, ReplayMismatchError, json_compatible
from .state import EpisodeOutcome


@dataclass(frozen=True)
class ReplayEvent:
    schema_version: str
    episode_id: str
    source_identity: str
    build_identity: str
    compatibility_patch_identity: str
    configuration_hash: str
    world_seed: int
    episode_seed: int
    turn: int
    executed_action: ExecutedAction
    action_result: ActionResult
    deterministic_checksum: str
    terminal_outcome: EpisodeOutcome = EpisodeOutcome.NO_OUTCOME

    @classmethod
    def from_turn(
        cls,
        *,
        schema_version: str,
        episode_id: str,
        context: DeterminismContext,
        turn: int,
        executed_action: ExecutedAction,
        action_result: ActionResult,
        deterministic_checksum: str,
        terminal_outcome: EpisodeOutcome = EpisodeOutcome.NO_OUTCOME,
    ) -> "ReplayEvent":
        return cls(
            schema_version=schema_version,
            episode_id=episode_id,
            source_identity=context.source_identity,
            build_identity=context.build_identity,
            compatibility_patch_identity=context.compatibility_patch_identity,
            configuration_hash=context.configuration_hash,
            world_seed=context.world_seed,
            episode_seed=context.episode_seed,
            turn=turn,
            executed_action=executed_action,
            action_result=action_result,
            deterministic_checksum=deterministic_checksum,
            terminal_outcome=terminal_outcome,
        )

    def to_json_data(self) -> dict[str, JsonValue]:
        return {
            "schema_version": self.schema_version,
            "episode_id": self.episode_id,
            "source_identity": self.source_identity,
            "build_identity": self.build_identity,
            "compatibility_patch_identity": self.compatibility_patch_identity,
            "configuration_hash": self.configuration_hash,
            "world_seed": self.world_seed,
            "episode_seed": self.episode_seed,
            "turn": self.turn,
            "executed_action": self.executed_action.to_json_data(),
            "action_result": self.action_result.to_json_data(),
            "deterministic_checksum": self.deterministic_checksum,
            "terminal_outcome": self.terminal_outcome.value,
        }


@dataclass
class ReplayEpisode:
    episode_id: str
    events: list[ReplayEvent] = field(default_factory=list)
    outcome: EpisodeOutcome = EpisodeOutcome.NO_OUTCOME

    @property
    def executed_actions(self) -> list[ExecutedAction]:
        return [event.executed_action for event in self.events]

    @property
    def action_results(self) -> list[ActionResult]:
        return [event.action_result for event in self.events]

    @property
    def checksums(self) -> list[str]:
        return [event.deterministic_checksum for event in self.events]


class ReplayRecorder:
    def __init__(self, episode_id: str) -> None:
        self.episode = ReplayEpisode(episode_id=episode_id)

    def record(self, event: ReplayEvent) -> None:
        self.episode.events.append(event)
        if event.terminal_outcome is not EpisodeOutcome.NO_OUTCOME:
            self.episode.outcome = event.terminal_outcome

    def finish(self, outcome: EpisodeOutcome) -> ReplayEpisode:
        self.episode.outcome = outcome
        return self.episode


class InMemoryReplayStore:
    def __init__(self) -> None:
        self._episodes: dict[str, ReplayEpisode] = {}

    def save(self, episode: ReplayEpisode) -> None:
        self._episodes[episode.episode_id] = episode

    def get(self, episode_id: str) -> ReplayEpisode:
        return self._episodes[episode_id]


def verify_replay_match(expected: ReplayEpisode, actual: ReplayEpisode) -> None:
    expected_data = [event.to_json_data() for event in expected.events]
    actual_data = [event.to_json_data() for event in actual.events]
    if expected_data != actual_data:
        raise ReplayMismatchError("replay event sequence mismatch")
    if expected.outcome != actual.outcome:
        raise ReplayMismatchError("replay outcome mismatch")
