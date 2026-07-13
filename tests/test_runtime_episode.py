import unittest

from runtime import (
    ActionStatus,
    DeterminismContext,
    DecisionResponse,
    DecisionStatus,
    DomainAdapterError,
    EpisodeOutcome,
    InvalidStateTransition,
    RequestedAction,
    RuntimeState,
    ValidatedAction,
    ValidationStatus,
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

    def test_runtime_schema_rejection_faults_without_execution(self):
        class InvalidActionProvider:
            def decide(self, request):  # noqa: ANN001
                return DecisionResponse(
                    request_id=request.request_id,
                    status=DecisionStatus.OK,
                    requested_action=RequestedAction(
                        action_type="NOT_AN_ACTION",
                        parameters={},
                        request_id=request.request_id,
                    ),
                )

        domain = FakeDomainAdapter()
        result = RuntimeOrchestrator(
            domain,
            InvalidActionProvider(),
            context(),
        ).run_episode("schema-rejection")

        self.assertEqual(result.runtime_state, RuntimeState.FAULTED)
        self.assertEqual(result.outcome, EpisodeOutcome.NO_OUTCOME)
        self.assertIsNotNone(result.runtime_error)
        self.assertEqual(domain.position, 0)
        self.assertEqual(domain.turn_count, 0)
        self.assertEqual(result.replay_episode.events, [])
        self.assertEqual(result.replay_episode.executed_actions, [])

    def test_runtime_observable_rejection_faults_without_execution(self):
        class ObservableRejectDomain(FakeDomainAdapter):
            action_was_applied = False

            def validate_action(self, action):  # noqa: ANN001
                if action.action_type == "WAIT":
                    return ValidatedAction(
                        requested_action=action,
                        normalized_parameters={},
                        validation_status=ValidationStatus.REJECTED_OBSERVABLE_RULE,
                        message="WAIT is not observable-legal in this test state",
                    )
                return super().validate_action(action)

            def apply_action(self, action, turn):  # noqa: ANN001
                self.action_was_applied = True
                return super().apply_action(action, turn)

        domain = ObservableRejectDomain()
        result = RuntimeOrchestrator(
            domain,
            RecordedDecisionProvider(["WAIT"]),
            context(),
        ).run_episode("observable-rejection")

        self.assertEqual(result.runtime_state, RuntimeState.FAULTED)
        self.assertEqual(result.outcome, EpisodeOutcome.NO_OUTCOME)
        self.assertIsNotNone(result.runtime_error)
        self.assertFalse(domain.action_was_applied)
        self.assertEqual(domain.position, 0)
        self.assertEqual(domain.turn_count, 0)
        self.assertEqual(result.replay_episode.executed_actions, [])

    def test_runtime_domain_failure_is_executed_and_can_continue(self):
        domain = FakeDomainAdapter()
        result = RuntimeOrchestrator(
            domain,
            RecordedDecisionProvider(["BUMP", "GO_RIGHT", "GO_RIGHT", "GO_RIGHT"]),
            context(),
        ).run_episode("domain-failure")

        self.assertEqual(result.runtime_state, RuntimeState.TERMINATED)
        self.assertEqual(result.outcome, EpisodeOutcome.SUCCESS)
        self.assertEqual(domain.turn_count, 4)
        self.assertEqual(
            result.replay_episode.events[0].action_result.status,
            ActionStatus.ATTEMPT_FAILED_IN_DOMAIN,
        )
        self.assertEqual(result.replay_episode.executed_actions[0].action_type, "BUMP")
        self.assertEqual(len(result.replay_episode.events), 4)

    def test_runtime_orchestrator_is_one_shot(self):
        orchestrator = RuntimeOrchestrator(
            FakeDomainAdapter(),
            RuleBasedDecisionProvider(),
            context(),
        )
        orchestrator.run_episode("first")

        with self.assertRaises(InvalidStateTransition) as raised:
            orchestrator.run_episode("second")

        self.assertIn("one-shot", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
