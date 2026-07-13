import unittest

from runtime import (
    ActionStatus,
    DeterminismContext,
    DomainAdapterError,
    EpisodeOutcome,
    RequestedAction,
    RuntimeState,
)
from runtime.fake import FakeDomainAdapter, RecordedDecisionProvider, RuleBasedDecisionProvider
from runtime.orchestrator import RuntimeOrchestrator


def context():
    return DeterminismContext.from_config(
        world_seed=1,
        episode_seed=2,
        source_identity="fake-source",
        build_identity="fake-build",
        compatibility_patch_identity="none",
        config={"domain": "fake"},
    )


class RuntimeEpisodeTests(unittest.TestCase):
    def test_rule_based_provider_reaches_success(self):
        result = RuntimeOrchestrator(
            FakeDomainAdapter(),
            RuleBasedDecisionProvider(),
            context(),
        ).run_episode("success")
        self.assertEqual(result.runtime_state, RuntimeState.TERMINATED)
        self.assertEqual(result.outcome, EpisodeOutcome.SUCCESS)
        self.assertEqual(len(result.replay_episode.events), 3)

    def test_recorded_left_actions_reach_domain_loss(self):
        result = RuntimeOrchestrator(
            FakeDomainAdapter(),
            RecordedDecisionProvider(["GO_LEFT", "GO_LEFT"]),
            context(),
        ).run_episode("loss")
        self.assertEqual(result.outcome, EpisodeOutcome.DOMAIN_LOSS)
        self.assertEqual(result.runtime_state, RuntimeState.TERMINATED)

    def test_turn_limit_reaches_time_limit(self):
        result = RuntimeOrchestrator(
            FakeDomainAdapter(max_turns=2),
            RecordedDecisionProvider(["WAIT", "WAIT"]),
            context(),
        ).run_episode("time")
        self.assertEqual(result.outcome, EpisodeOutcome.TIME_LIMIT)

    def test_schema_invalid_action_is_rejected(self):
        domain = FakeDomainAdapter()
        domain.reset(context())
        validated = domain.validate_action(
            RequestedAction(action_type="NOT_AN_ACTION", parameters={}, request_id="bad")
        )
        self.assertFalse(validated.accepted)
        result = domain.apply_action(validated, 0)
        self.assertEqual(result.status, ActionStatus.REJECTED_SCHEMA)

    def test_domain_action_failure_is_distinct_from_schema_rejection(self):
        domain = FakeDomainAdapter()
        domain.reset(context())
        validated = domain.validate_action(
            RequestedAction(action_type="BUMP", parameters={}, request_id="bump")
        )
        self.assertTrue(validated.accepted)
        result = domain.apply_action(validated, 0)
        self.assertEqual(result.status, ActionStatus.ATTEMPT_FAILED_IN_DOMAIN)

    def test_runtime_exception_sets_faulted(self):
        class FaultyDomain(FakeDomainAdapter):
            def reset(self, context):  # noqa: ANN001
                raise DomainAdapterError("fake reset fault")

        result = RuntimeOrchestrator(
            FaultyDomain(),
            RuleBasedDecisionProvider(),
            context(),
        ).run_episode("fault")
        self.assertEqual(result.runtime_state, RuntimeState.FAULTED)
        self.assertEqual(result.outcome, EpisodeOutcome.NO_OUTCOME)
        self.assertIsNotNone(result.runtime_error)


if __name__ == "__main__":
    unittest.main()
