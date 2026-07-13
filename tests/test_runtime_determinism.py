import unittest

from runtime import DeterminismContext, sha256_json
from runtime.fake import RuleBasedDecisionProvider, FakeDomainAdapter
from runtime.orchestrator import RuntimeOrchestrator


def context(world_seed=1, episode_seed=2, config=None):
    return DeterminismContext.from_config(
        world_seed=world_seed,
        episode_seed=episode_seed,
        source_identity="fake-source",
        build_identity="fake-build",
        compatibility_patch_identity="none",
        config=config or {"a": 1, "b": 2},
    )


class RuntimeDeterminismTests(unittest.TestCase):
    def test_configuration_hash_uses_canonical_json(self):
        left = context(config={"a": 1, "b": 2})
        right = context(config={"b": 2, "a": 1})
        self.assertEqual(left.configuration_hash, right.configuration_hash)
        self.assertEqual(left.configuration_hash, sha256_json({"a": 1, "b": 2}))

    def test_same_seed_and_actions_produce_same_checksums(self):
        first = RuntimeOrchestrator(
            FakeDomainAdapter(),
            RuleBasedDecisionProvider(),
            context(),
        ).run_episode("episode")
        second = RuntimeOrchestrator(
            FakeDomainAdapter(),
            RuleBasedDecisionProvider(),
            context(),
        ).run_episode("episode")
        self.assertEqual(first.replay_episode.checksums, second.replay_episode.checksums)
        self.assertEqual(first.outcome, second.outcome)

    def test_different_seed_changes_checksum(self):
        first = RuntimeOrchestrator(
            FakeDomainAdapter(),
            RuleBasedDecisionProvider(),
            context(world_seed=1),
        ).run_episode("episode")
        second = RuntimeOrchestrator(
            FakeDomainAdapter(),
            RuleBasedDecisionProvider(),
            context(world_seed=99),
        ).run_episode("episode")
        self.assertNotEqual(first.replay_episode.checksums, second.replay_episode.checksums)


if __name__ == "__main__":
    unittest.main()
