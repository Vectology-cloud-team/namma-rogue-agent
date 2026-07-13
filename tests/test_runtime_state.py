import unittest

from runtime import (
    EpisodeOutcome,
    InvalidStateTransition,
    RuntimeState,
    RuntimeStateMachine,
)


class RuntimeStateTests(unittest.TestCase):
    def test_valid_runtime_transitions(self):
        machine = RuntimeStateMachine()
        machine.transition(RuntimeState.READY)
        machine.transition(RuntimeState.RUNNING)
        machine.transition(RuntimeState.PAUSED)
        machine.transition(RuntimeState.RUNNING)
        machine.transition(RuntimeState.TERMINATED)
        self.assertTrue(machine.terminal)

    def test_invalid_runtime_transition_is_rejected(self):
        machine = RuntimeStateMachine()
        with self.assertRaises(InvalidStateTransition):
            machine.transition(RuntimeState.RUNNING)

    def test_terminal_states_reject_further_transitions(self):
        machine = RuntimeStateMachine()
        machine.transition(RuntimeState.READY)
        machine.transition(RuntimeState.RUNNING)
        machine.transition(RuntimeState.FAULTED)
        with self.assertRaises(InvalidStateTransition):
            machine.transition(RuntimeState.READY)

    def test_episode_outcome_does_not_include_runtime_fault(self):
        values = {item.value for item in EpisodeOutcome}
        self.assertIn("DOMAIN_LOSS", values)
        self.assertNotIn("FAULTED", values)


if __name__ == "__main__":
    unittest.main()
