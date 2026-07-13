"""Tests for the Phase 8 fake Rogue native backend."""

from __future__ import annotations

import unittest

from runtime.actions import ActionStatus, RequestedAction, ValidationStatus
from runtime.determinism import DeterminismContext
from runtime.models import DomainAdapterError
from runtime.rogue import FakeRogueNativeBackend, RogueNativeConfig


def make_context() -> DeterminismContext:
    return DeterminismContext.from_config(
        world_seed=123,
        episode_seed=456,
        source_identity="Rogueforge Rogue 5.4.4",
        build_identity="fake-native-backend",
        compatibility_patch_identity="phase8-fake",
        config={"test": "fake_rogue_native_backend"},
    )


class FakeRogueNativeBackendTests(unittest.TestCase):
    def test_reset_observe_and_source_identity(self) -> None:
        backend = FakeRogueNativeBackend()
        backend.create(RogueNativeConfig())

        result = backend.reset(make_context())
        observation = backend.observe()

        self.assertTrue(backend.reset_called)
        self.assertEqual(["fake_rogue_reset"], result.domain_events)
        self.assertEqual({"y": 1, "x": 1}, observation.player_position.to_json_data())
        self.assertEqual("Rogueforge Rogue 5.4.4", backend.source_identity().upstream_identity)

    def test_move_and_wait_are_normalized_and_applied(self) -> None:
        backend = FakeRogueNativeBackend()
        backend.create(RogueNativeConfig())
        backend.reset(make_context())

        move = backend.validate_action(
            RequestedAction("MOVE", {"direction": "e"}, request_id="move")
        )
        wait = backend.validate_action(RequestedAction("WAIT", request_id="wait"))

        self.assertEqual(ValidationStatus.VALID, move.validation_status)
        self.assertEqual({"direction": "E"}, move.normalized_parameters)
        self.assertEqual(ValidationStatus.VALID, wait.validation_status)

        move_result = backend.apply_action(move, turn=0)
        wait_result = backend.apply_action(wait, turn=1)

        self.assertEqual(ActionStatus.SUCCESS, move_result.status)
        self.assertEqual(ActionStatus.SUCCESS, wait_result.status)
        self.assertEqual(("MOVE", "WAIT"), tuple(a.action_type for a in backend.applied_actions))

    def test_wall_move_is_executed_domain_failure(self) -> None:
        backend = FakeRogueNativeBackend()
        backend.create(RogueNativeConfig())
        backend.reset(make_context())

        action = backend.validate_action(
            RequestedAction("MOVE", {"direction": "W"}, request_id="blocked")
        )
        result = backend.apply_action(action, turn=0)

        self.assertEqual(ActionStatus.ATTEMPT_FAILED_IN_DOMAIN, result.status)
        self.assertEqual(1, backend.apply_count)
        self.assertEqual(["move_blocked"], result.domain_events)

    def test_hidden_cell_is_debug_only(self) -> None:
        backend = FakeRogueNativeBackend()
        backend.create(RogueNativeConfig())
        backend.reset(make_context())

        observation = backend.observe()
        debug = backend.privileged_debug_state()

        payload = observation.to_agent_payload()
        self.assertNotIn("hidden_cell", str(payload))
        self.assertNotIn("hidden_nonce", str(payload))
        self.assertIn("hidden_cell", debug.payload)
        self.assertIn("hidden_nonce", debug.payload)

    def test_close_is_idempotent_and_blocks_later_calls(self) -> None:
        backend = FakeRogueNativeBackend()
        backend.create(RogueNativeConfig())
        backend.close()
        backend.close()

        self.assertEqual(1, backend.close_count)
        with self.assertRaises(DomainAdapterError):
            backend.observe()


if __name__ == "__main__":
    unittest.main()
