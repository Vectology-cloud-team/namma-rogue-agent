"""Tests for the Runtime -> RogueDomainAdapter -> fake backend path.
"""

from __future__ import annotations

import json
import unittest

from runtime.actions import (
    ActionStatus,
    RequestedAction,
)
from runtime.determinism import DeterminismContext
from runtime.models import DomainAdapterError, ReplayMismatchError
from runtime.provider import (
    DecisionRequest,
    DecisionResponse,
    DecisionStatus,
)
from runtime.replay import verify_replay_match
from runtime.rogue import FakeRogueNativeBackend, RogueDomainAdapter
from runtime.state import EpisodeOutcome, RuntimeState
from runtime.orchestrator import RuntimeOrchestrator


def make_context() -> DeterminismContext:
    return DeterminismContext.from_config(
        world_seed=777,
        episode_seed=888,
        source_identity="Rogueforge Rogue 5.4.4",
        build_identity="phase8-fake-native-backend",
        compatibility_patch_identity="phase8-no-rogue-code-change",
        config={"profile": "phase8-rogue-adapter-test"},
    )


class SequenceProvider:
    def __init__(self, actions: list[RequestedAction]) -> None:
        self._actions = list(actions)
        self.requests: list[DecisionRequest] = []

    def decide(self, request: DecisionRequest) -> DecisionResponse:
        self.requests.append(request)
        if not self._actions:
            return DecisionResponse(
                request_id=request.request_id,
                status=DecisionStatus.NO_ACTION,
            )
        return DecisionResponse(
            request_id=request.request_id,
            status=DecisionStatus.OK,
            requested_action=self._actions.pop(0),
        )


def run_with_actions(
    actions: list[RequestedAction],
    episode_id: str = "rogue-adapter-episode",
):
    backend = FakeRogueNativeBackend()
    adapter = RogueDomainAdapter(backend)
    provider = SequenceProvider(actions)
    runtime = RuntimeOrchestrator(
        domain=adapter,
        decision_provider=provider,
        context=make_context(),
        max_runtime_turns=10,
    )
    result = runtime.run_episode(episode_id=episode_id)
    return result, backend, provider


class RogueDomainAdapterTests(unittest.TestCase):
    def test_adapter_runs_success_episode_and_replay_matches(self) -> None:
        actions = [
            RequestedAction("MOVE", {"direction": "S"}, request_id="south-1"),
            RequestedAction("MOVE", {"direction": "S"}, request_id="south-2"),
        ]

        expected, backend, _provider = run_with_actions(list(actions))
        actual, _backend2, _provider2 = run_with_actions(list(actions))

        self.assertTrue(backend.reset_called)
        self.assertEqual(
            RuntimeState.TERMINATED,
            expected.runtime_state,
        )
        self.assertEqual(
            EpisodeOutcome.SUCCESS,
            expected.outcome,
        )
        verify_replay_match(expected.replay_episode, actual.replay_episode)

    def test_different_action_sequence_detects_replay_mismatch(self) -> None:
        expected, _backend, _provider = run_with_actions(
            [RequestedAction("WAIT"), RequestedAction("QUIT")]
        )
        actual, _backend2, _provider2 = run_with_actions(
            [
                RequestedAction("MOVE", {"direction": "E"}),
                RequestedAction("QUIT"),
            ]
        )

        with self.assertRaises(ReplayMismatchError):
            verify_replay_match(expected.replay_episode, actual.replay_episode)

    def test_agent_observation_and_decision_request_do_not_get_debug_state(self) -> None:
        result, _backend, provider = run_with_actions(
            [RequestedAction("WAIT"), RequestedAction("QUIT")]
        )

        self.assertEqual(EpisodeOutcome.USER_ABORT, result.outcome)
        self.assertGreaterEqual(len(provider.requests), 1)
        request_data = provider.requests[0].to_json_data()
        encoded = json.dumps(request_data, sort_keys=True)
        self.assertNotIn("hidden_cell", encoded)
        self.assertNotIn("hidden_nonce", encoded)
        self.assertNotIn("PrivilegedDebugState", encoded)

    def test_invalid_action_faults_before_backend_apply(self) -> None:
        result, backend, _provider = run_with_actions(
            [RequestedAction("DANCE", request_id="invalid")]
        )

        self.assertEqual(RuntimeState.FAULTED, result.runtime_state)
        self.assertEqual(EpisodeOutcome.NO_OUTCOME, result.outcome)
        self.assertEqual(0, backend.apply_count)
        self.assertEqual(0, len(result.replay_episode.events))

    def test_domain_move_failure_is_recorded_as_executed_action(self) -> None:
        result, backend, _provider = run_with_actions(
            [
                RequestedAction("MOVE", {"direction": "W"}, request_id="blocked"),
                RequestedAction("QUIT", request_id="quit"),
            ]
        )

        self.assertEqual(EpisodeOutcome.USER_ABORT, result.outcome)
        self.assertEqual(2, backend.apply_count)
        self.assertEqual(2, len(result.replay_episode.events))
        self.assertEqual(
            ActionStatus.ATTEMPT_FAILED_IN_DOMAIN,
            result.replay_episode.events[0].action_result.status,
        )

    def test_terminal_loss_and_abort_are_mapped(self) -> None:
        loss, _backend, _provider = run_with_actions(
            [
                RequestedAction("MOVE", {"direction": "E"}),
                RequestedAction("MOVE", {"direction": "E"}),
            ],
            episode_id="loss",
        )
        abort, _backend2, _provider2 = run_with_actions(
            [RequestedAction("QUIT")],
            episode_id="abort",
        )

        self.assertEqual(EpisodeOutcome.DOMAIN_LOSS, loss.outcome)
        self.assertEqual(EpisodeOutcome.USER_ABORT, abort.outcome)

    def test_close_is_idempotent_and_close_after_use_rejects_calls(self) -> None:
        backend = FakeRogueNativeBackend()
        adapter = RogueDomainAdapter(backend)
        adapter.reset(make_context())
        adapter.close()
        adapter.close()

        self.assertEqual(1, backend.close_count)
        with self.assertRaises(DomainAdapterError):
            adapter.observe("closed", 0)

    def test_backend_exception_is_wrapped_as_domain_adapter_error(self) -> None:
        class ExplodingBackend(FakeRogueNativeBackend):
            explode_observe = False

            def observe(self):
                if not self.explode_observe:
                    return super().observe()
                raise RuntimeError("native observe exploded")

        backend = ExplodingBackend()
        adapter = RogueDomainAdapter(backend)
        adapter.reset(make_context())
        backend.explode_observe = True

        with self.assertRaises(DomainAdapterError) as caught:
            adapter.observe("explosion", 0)
        self.assertIn("observe failed", str(caught.exception))

    def test_backend_exception_faults_runtime_without_episode_outcome(self) -> None:
        class ExplodingApplyBackend(FakeRogueNativeBackend):
            def apply_action(self, action, turn: int):
                raise RuntimeError("native apply exploded")

        backend = ExplodingApplyBackend()
        adapter = RogueDomainAdapter(backend)
        provider = SequenceProvider([RequestedAction("WAIT")])
        runtime = RuntimeOrchestrator(
            domain=adapter,
            decision_provider=provider,
            context=make_context(),
            max_runtime_turns=1,
        )

        result = runtime.run_episode(episode_id="runtime-fault")

        self.assertEqual(RuntimeState.FAULTED, result.runtime_state)
        self.assertEqual(EpisodeOutcome.NO_OUTCOME, result.outcome)
        self.assertIsNotNone(result.runtime_error)
        self.assertEqual(0, len(result.replay_episode.events))


if __name__ == "__main__":
    unittest.main()
