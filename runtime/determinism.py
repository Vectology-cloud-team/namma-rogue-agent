"""Determinism context and canonical hashing helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json

from .models import JsonValue, json_compatible


def canonical_json(value: JsonValue) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def sha256_json(value: JsonValue) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class DeterminismContext:
    world_seed: int
    episode_seed: int
    source_identity: str
    build_identity: str
    compatibility_patch_identity: str
    configuration_hash: str
    action_order: tuple[str, ...] = ()
    rng_stream_ids: tuple[str, ...] = ()
    replay_identity: str = ""

    @classmethod
    def from_config(
        cls,
        *,
        world_seed: int,
        episode_seed: int,
        source_identity: str,
        build_identity: str,
        compatibility_patch_identity: str,
        config: dict[str, JsonValue],
        action_order: list[str] | tuple[str, ...] = (),
        rng_stream_ids: list[str] | tuple[str, ...] = (),
        replay_identity: str = "",
    ) -> "DeterminismContext":
        return cls(
            world_seed=world_seed,
            episode_seed=episode_seed,
            source_identity=source_identity,
            build_identity=build_identity,
            compatibility_patch_identity=compatibility_patch_identity,
            configuration_hash=sha256_json(json_compatible(config)),
            action_order=tuple(action_order),
            rng_stream_ids=tuple(rng_stream_ids),
            replay_identity=replay_identity,
        )

    def to_json_data(self) -> dict[str, JsonValue]:
        return {
            "world_seed": self.world_seed,
            "episode_seed": self.episode_seed,
            "source_identity": self.source_identity,
            "build_identity": self.build_identity,
            "compatibility_patch_identity": self.compatibility_patch_identity,
            "configuration_hash": self.configuration_hash,
            "action_order": list(self.action_order),
            "rng_stream_ids": list(self.rng_stream_ids),
            "replay_identity": self.replay_identity,
        }

    def with_action(self, action_id: str) -> "DeterminismContext":
        return DeterminismContext(
            world_seed=self.world_seed,
            episode_seed=self.episode_seed,
            source_identity=self.source_identity,
            build_identity=self.build_identity,
            compatibility_patch_identity=self.compatibility_patch_identity,
            configuration_hash=self.configuration_hash,
            action_order=(*self.action_order, action_id),
            rng_stream_ids=self.rng_stream_ids,
            replay_identity=self.replay_identity,
        )


@dataclass
class ChecksumChain:
    values: list[str] = field(default_factory=list)

    def append(self, public_state: dict[str, JsonValue]) -> str:
        checksum = sha256_json(json_compatible(public_state))
        self.values.append(checksum)
        return checksum
