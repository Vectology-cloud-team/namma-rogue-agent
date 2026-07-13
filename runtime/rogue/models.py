"""Rogue-specific adapter models.

These models are Python-side boundary models. They do not expose Rogue C
internals, curses types, or Python objects through the future C ABI.

The default source identity is scoped to Phase 8 fake-backend tests. Real
native backends must report source identity from build metadata.
Committed blob line counts are guarded by scripts/check_text_files.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models import JsonValue, json_compatible


ROGUE_ACTION_TYPES: tuple[str, ...] = (
    "MOVE",
    "WAIT",
    "SEARCH",
    "OPEN",
    "CLOSE",
    "PICKUP",
    "DROP",
    "EAT",
    "DRINK",
    "READ",
    "WIELD",
    "WEAR",
    "REMOVE",
    "THROW",
    "DESCEND",
    "ASCEND",
    "QUIT",
)

PHASE8_SUPPORTED_ACTION_TYPES: tuple[str, ...] = ("MOVE", "WAIT", "QUIT")

ROGUE_DIRECTIONS: tuple[str, ...] = (
    "N",
    "NE",
    "E",
    "SE",
    "S",
    "SW",
    "W",
    "NW",
    "NONE",
)


@dataclass(frozen=True)
class RogueSourceIdentity:
    identity_scope: str = "phase8_fake_backend"
    upstream_identity: str = "Rogueforge Rogue 5.4.4"
    upstream_archive_sha256: str = "see docs/rogue-544-golden-source.md"
    compatibility_patch_identity: str = "phase8-fake; future real backend reports patch hash"
    source_commit: str = "not-connected"
    build_identity: str = "phase8-fake-native-backend"
    compiler_identity: str = "not-applicable"
    abi_version: str = "0.1"

    def to_json_data(self) -> dict[str, JsonValue]:
        return json_compatible(
            {
                "identity_scope": self.identity_scope,
                "upstream_identity": self.upstream_identity,
                "upstream_archive_sha256": self.upstream_archive_sha256,
                "compatibility_patch_identity": self.compatibility_patch_identity,
                "source_commit": self.source_commit,
                "build_identity": self.build_identity,
                "compiler_identity": self.compiler_identity,
                "abi_version": self.abi_version,
            }
        )  # type: ignore[return-value]


@dataclass(frozen=True)
class RogueNativeConfig:
    source_identity: RogueSourceIdentity = field(default_factory=RogueSourceIdentity)
    observation_schema_version: str = "rogue.agent_observation.v1"
    native_schema_version: str = "rogue.native.v1"
    allow_privileged_debug_state: bool = True

    def to_json_data(self) -> dict[str, JsonValue]:
        return json_compatible(
            {
                "source_identity": self.source_identity.to_json_data(),
                "observation_schema_version": self.observation_schema_version,
                "native_schema_version": self.native_schema_version,
                "allow_privileged_debug_state": self.allow_privileged_debug_state,
            }
        )  # type: ignore[return-value]


@dataclass(frozen=True, order=True)
class RoguePosition:
    y: int
    x: int

    def moved(self, direction: str) -> "RoguePosition":
        dy, dx = {
            "N": (-1, 0),
            "NE": (-1, 1),
            "E": (0, 1),
            "SE": (1, 1),
            "S": (1, 0),
            "SW": (1, -1),
            "W": (0, -1),
            "NW": (-1, -1),
            "NONE": (0, 0),
        }[direction]
        return RoguePosition(self.y + dy, self.x + dx)

    def to_json_data(self) -> dict[str, JsonValue]:
        return {"y": self.y, "x": self.x}


@dataclass(frozen=True)
class RogueVisibleCell:
    position: RoguePosition
    glyph: str
    terrain: str
    walkable: bool

    def to_json_data(self) -> dict[str, JsonValue]:
        return {
            "position": self.position.to_json_data(),
            "glyph": self.glyph,
            "terrain": self.terrain,
            "walkable": self.walkable,
        }


@dataclass(frozen=True)
class RogueNativeObservation:
    schema_version: str
    dungeon_level: int
    player_position: RoguePosition
    hp: int
    hp_max: int
    visible_cells: tuple[RogueVisibleCell, ...]
    recent_messages: tuple[str, ...]
    terminal: bool = False
    terminal_reason: str = ""
    status_effects: tuple[str, ...] = ()
    available_action_types: tuple[str, ...] = PHASE8_SUPPORTED_ACTION_TYPES

    def to_agent_payload(self) -> dict[str, JsonValue]:
        return json_compatible(
            {
                "schema_version": self.schema_version,
                "dungeon_level": self.dungeon_level,
                "player_position": self.player_position.to_json_data(),
                "hp": self.hp,
                "hp_max": self.hp_max,
                "visible_cells": [
                    cell.to_json_data()
                    for cell in sorted(
                        self.visible_cells,
                        key=lambda cell: (cell.position.y, cell.position.x),
                    )
                ],
                "recent_messages": list(self.recent_messages),
                "terminal": self.terminal,
                "terminal_reason": self.terminal_reason,
                "status_effects": list(self.status_effects),
            }
        )  # type: ignore[return-value]


@dataclass(frozen=True)
class RogueResetResult:
    observation: RogueNativeObservation
    domain_events: list[str] = field(default_factory=list)

    def to_json_data(self) -> dict[str, JsonValue]:
        return {
            "observation": self.observation.to_agent_payload(),
            "domain_events": list(self.domain_events),
        }
