import unittest

from runtime import DeterminismContext, EpisodeOutcome, ReplayMismatchError
from runtime.fake import FakeDomainAdapter, RecordedDecisionProvider, RuleBasedDecisionProvider
from runtime.orchestrator import RuntimeOrchestrator
from runtime.replay import verify_replay_match


def context(world_seed=1):
    return DeterminismContext.from_config(
        world_seed=world_seed,
        episode_seed=2,
        source_identity="fake-source",
        build_identity="fake-build",
        compatibility_patch_identity="none",
        config={"domain": "fake"},
    )


class RuntimeReplayTests(unittest.TestCase):
    def test_recorded_provider_replays_level1_episode(self):
        expected = RuntimeOrchestrator(
            FakeDomainAdapter(),
            RuleBasedDecisionProvider(),
            context(),
        ).run_episode("replay")
        replayed = RuntimeOrchestrator(
            FakeDomainAdapter(),
            RecordedDecisionProvider(expected.replay_episode.executed_actions),
            context(),
        ).run_episode("replay")

        self.assertEqual(expected.outcome, EpisodeOutcome.SUCCESS)
        self.assertEqual(
            expected.replay_episode.executed_actions,
            replayed.replay_episode.executed_actions,
        )
        self.assertEqual(
            expected.replay_episode.action_results,
            replayed.replay_episode.action_results,
        )
        self.assertEqual(expected.replay_episode.checksums, replayed.replay_episode.checksums)
        verify_replay_match(expected.replay_episode, replayed.replay_episode)

    def test_replay_mismatch_is_detected_for_seed_change(self):
        expected = RuntimeOrchestrator(
            FakeDomainAdapter(),
            RuleBasedDecisionProvider(),
            context(world_seed=1),
        ).run_episode("mismatch")
        actual = RuntimeOrchestrator(
            FakeDomainAdapter(),
            RecordedDecisionProvider(expected.replay_episode.executed_actions),
            context(world_seed=99),
        ).run_episode("mismatch")

        with self.assertRaises(ReplayMismatchError):
            verify_replay_match(expected.replay_episode, actual.replay_episode)


if __name__ == "__main__":
    unittest.main()
