"""Text-level checks for the Phase 8 native ABI specification header.
"""

from __future__ import annotations

from dataclasses import fields
from pathlib import Path
import unittest

from runtime.actions import ValidationStatus
from runtime.rogue.backend import RogueNativeBackend
from runtime.rogue.models import (
    PHASE8_SUPPORTED_ACTION_TYPES,
    ROGUE_ACTION_TYPES,
    ROGUE_DIRECTIONS,
    RogueNativeObservation,
    RogueResetResult,
)


HEADER = (
    Path(__file__).resolve().parents[1]
    / "adapter/native/include/namma_rogue_api.h"
)


class NativeAbiHeaderTests(unittest.TestCase):
    def header_text(self) -> str:
        return HEADER.read_text(encoding="utf-8")

    def test_terminal_kind_does_not_include_runtime_error(self) -> None:
        text = self.header_text()

        self.assertIn("NAMMA_ROGUE_TERMINAL_SAVED", text)
        self.assertNotIn("NAMMA_ROGUE_TERMINAL_RUNTIME_ERROR", text)

    def test_protocol_methods_have_c_abi_counterparts(self) -> None:
        text = self.header_text()
        method_to_symbol = {
            "create": "namma_rogue_create",
            "reset": "namma_rogue_reset",
            "observe": "namma_rogue_observe",
            "validate_action": "namma_rogue_validate_action",
            "apply_action": "namma_rogue_apply_action",
            "terminal_status": "namma_rogue_terminal_status",
            "privileged_debug_state": "namma_rogue_debug_state",
            "source_identity": "namma_rogue_source_identity",
            "close": "namma_rogue_destroy",
        }

        for method_name, c_symbol in method_to_symbol.items():
            self.assertIn(method_name, RogueNativeBackend.__dict__)
            self.assertIn(c_symbol, text)

    def test_reset_contract_excludes_observation_and_events(self) -> None:
        text = self.header_text()
        reset_fields = [field.name for field in fields(RogueResetResult)]

        self.assertEqual(["schema_version", "status", "message"], reset_fields)
        self.assertNotIn("observation", reset_fields)
        self.assertNotIn("domain_events", reset_fields)
        self.assertIn("namma_rogue_reset_result", text)
        self.assertNotIn("domain_event_count", text)

    def test_observation_contract_uses_single_recent_message(self) -> None:
        text = self.header_text()
        observation_fields = [field.name for field in fields(RogueNativeObservation)]

        self.assertIn("recent_message", observation_fields)
        self.assertNotIn("recent_messages", observation_fields)
        self.assertNotIn("available_action_types", observation_fields)
        self.assertIn("const char *recent_message;", text)
        self.assertNotIn("recent_messages", text)
        self.assertNotIn("available_action_types", text)
        self.assertEqual(("MOVE", "WAIT", "QUIT"), PHASE8_SUPPORTED_ACTION_TYPES)

    def test_validation_status_has_dedicated_c_type(self) -> None:
        text = self.header_text()

        self.assertIn("typedef uint32_t namma_rogue_validation_status_t;", text)
        self.assertIn("NAMMA_ROGUE_VALIDATION_VALID", text)
        self.assertIn("NAMMA_ROGUE_VALIDATION_REJECTED_SCHEMA", text)
        self.assertIn("NAMMA_ROGUE_VALIDATION_REJECTED_OBSERVABLE_RULE", text)
        self.assertIn(
            "namma_rogue_validation_status_t validation_status;",
            text,
        )
        self.assertEqual(
            ["VALID", "REJECTED_SCHEMA", "REJECTED_OBSERVABLE_RULE"],
            [status.value for status in ValidationStatus],
        )

    def test_action_direction_terminal_values_are_explicit(self) -> None:
        text = self.header_text()

        for index, action_type in enumerate(("NONE",) + ROGUE_ACTION_TYPES):
            expected = f"NAMMA_ROGUE_ACTION_{action_type} "
            self.assertIn(expected, text)
            self.assertIn(f"((namma_rogue_action_type_t){index}u)", text)

        abi_direction_order = ("NONE",) + tuple(
            direction for direction in ROGUE_DIRECTIONS if direction != "NONE"
        )
        for index, direction in enumerate(abi_direction_order):
            expected = f"NAMMA_ROGUE_DIRECTION_{direction} "
            self.assertIn(expected, text)
            self.assertIn(f"((namma_rogue_direction_t){index}u)", text)

        for terminal_name, value in {
            "NONE": 0,
            "SUCCESS": 1,
            "LOSS": 2,
            "USER_ABORT": 3,
            "SAVED": 4,
        }.items():
            self.assertIn(f"NAMMA_ROGUE_TERMINAL_{terminal_name} ", text)
            self.assertIn(f"((namma_rogue_terminal_kind_t){value}u)", text)

    def test_native_abi_is_not_transport_abi(self) -> None:
        text = self.header_text()

        self.assertIn("in-process host native ABI", text)
        self.assertIn("not an Ethernet", text)
        self.assertIn("NaMMA", text)


if __name__ == "__main__":
    unittest.main()
