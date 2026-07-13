import unittest

from runtime import (
    DecisionRequest,
    DecisionResponse,
    DecisionStatus,
    DeterminismContext,
    EpisodeMemory,
    RequestedAction,
)
from runtime.fake import FakeDomainAdapter


def context(seed=1):
    return DeterminismContext.from_config(
        world_seed=seed,
        episode_seed=2,
        source_identity="fake-source",
        build_identity="fake-build",
        compatibility_patch_identity="none",
        config={"domain": "fake"},
    )


class RuntimeModelTests(unittest.TestCase):
    def test_observation_does_not_include_privileged_debug_state(self):
        domain = FakeDomainAdapter()
        domain.reset(context())
        observation = domain.observe("episode", 0)
        debug = domain.privileged_debug_state()

        request = DecisionRequest(
            request_id="req",
            schema_version="runtime.decision.v1",
            episode_id="episode",
            turn=0,
            task=observation.task,
            observation=observation,
            allowed_action_schema={"action_types": observation.available_action_types},
            timeout_budget_ms=1000,
        )
        request_data = request.to_json_data()
        self.assertNotIn("hidden_nonce", str(request_data))
        self.assertIn("hidden_nonce", str(debug.to_json_data()))

    def test_episode_memory_is_observation_derived(self):
        domain = FakeDomainAdapter()
        domain.reset(context())
        observation = domain.observe("episode", 0)
        memory = EpisodeMemory()
        memory.update_from_observation(observation)
        self.assertIn("last_observation_payload", memory.summary())
        self.assertNotIn("hidden_nonce", str(memory.summary()))

    def test_decision_response_can_represent_timeout(self):
        response = DecisionResponse(
            request_id="req",
            status=DecisionStatus.TIMEOUT,
            requested_action=None,
            error="timeout",
        )
        self.assertEqual(response.status, DecisionStatus.TIMEOUT)
        self.assertIsNone(response.requested_action)

    def test_requested_action_is_json_compatible(self):
        action = RequestedAction(
            action_type="GO_RIGHT",
            parameters={"count": 1},
            request_id="req",
        )
        self.assertEqual(action.to_json_data()["parameters"], {"count": 1})


if __name__ == "__main__":
    unittest.main()
