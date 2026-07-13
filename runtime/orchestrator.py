"""Minimal synchronous Runtime Orchestrator."""

from __future__ import annotations

from dataclasses import dataclass, field
import uuid

from .actions import ActionResult, ActionStatus, ExecutedAction
from .determinism import DeterminismContext, sha256_json
from .domain import DomainAdapter
from .models import (
    DecisionProviderError,
    DomainAdapterError,
    JsonValue,
    RuntimeContractError,
    json_compatible,
)
from .observations import EpisodeMemory
from .provider import DecisionProvider, DecisionRequest, DecisionStatus
from .replay import (
    InMemoryReplayStore,
    ReplayEpisode,
    ReplayEvent,
    ReplayRecorder,
)
from .state import EpisodeOutcome, RuntimeState, RuntimeStateMachine


@dataclass
class RuntimeErrorInfo:
    error_type: str
    message: str


@dataclass
class EpisodeResult:
    episode_id: str
    runtime_state: RuntimeState
    outcome: EpisodeOutcome
    replay_episode: ReplayEpisode
    runtime_error: RuntimeErrorInfo | None = None


@dataclass
class RuntimeOrchestrator:
    domain: DomainAdapter
    decision_provider: DecisionProvider
    context: DeterminismContext
    replay_store: InMemoryReplayStore = field(default_factory=InMemoryReplayStore)
    schema_version: str = "runtime.replay.v1"
    timeout_budget_ms: int = 1000
    max_runtime_turns: int = 1000

    def __post_init__(self) -> None:
        self.state_machine = RuntimeStateMachine()
        self.memory = EpisodeMemory()

    def run_episode(self, episode_id: str | None = None) -> EpisodeResult:
        episode_id = episode_id or str(uuid.uuid4())
        recorder = ReplayRecorder(episode_id)
        outcome = EpisodeOutcome.NO_OUTCOME
        current_context = self.context
        turn = 0

        try:
            self.state_machine.transition(RuntimeState.READY)
            self.domain.reset(current_context)
            self.state_machine.transition(RuntimeState.RUNNING)

            while turn < self.max_runtime_turns:
                observation = self.domain.observe(episode_id, turn)
                self.memory.update_from_observation(observation)
                decision = self.decision_provider.decide(
                    DecisionRequest(
                        request_id=f"{episode_id}:turn-{turn}",
                        schema_version="runtime.decision.v1",
                        episode_id=episode_id,
                        turn=turn,
                        task=observation.task,
                        observation=observation,
                        allowed_action_schema={
                            "action_types": list(observation.available_action_types)
                        },
                        timeout_budget_ms=self.timeout_budget_ms,
                        memory_summary=self.memory.summary(),
                    )
                )
                if (
                    decision.status is not DecisionStatus.OK
                    or decision.requested_action is None
                ):
                    raise DecisionProviderError(
                        f"DecisionProvider failed with status {decision.status.value}"
                    )

                validated = self.domain.validate_action(decision.requested_action)
                executed = ExecutedAction(
                    action_id=f"turn-{turn}",
                    action_type=decision.requested_action.action_type,
                    parameters=dict(validated.normalized_parameters),
                    turn=turn,
                )
                if not validated.accepted:
                    result = ActionResult(
                        action_id=executed.action_id,
                        status=ActionStatus.REJECTED_SCHEMA,
                        message=validated.message,
                        terminal=False,
                    )
                else:
                    result = self.domain.apply_action(validated, turn)

                current_context = current_context.with_action(executed.action_id)
                terminal = self.domain.terminal_status()
                outcome = terminal.outcome if terminal.terminal else EpisodeOutcome.NO_OUTCOME
                checksum = self._deterministic_checksum(current_context)
                recorder.record(
                    ReplayEvent.from_turn(
                        schema_version=self.schema_version,
                        episode_id=episode_id,
                        context=current_context,
                        turn=turn,
                        executed_action=executed,
                        action_result=result,
                        deterministic_checksum=checksum,
                        terminal_outcome=outcome,
                    )
                )

                turn += 1
                if terminal.terminal:
                    self.state_machine.transition(RuntimeState.TERMINATED)
                    episode = recorder.finish(outcome)
                    self.replay_store.save(episode)
                    return EpisodeResult(
                        episode_id=episode_id,
                        runtime_state=self.state_machine.state,
                        outcome=outcome,
                        replay_episode=episode,
                    )

            outcome = EpisodeOutcome.TIME_LIMIT
            self.state_machine.transition(RuntimeState.TERMINATED)
            episode = recorder.finish(outcome)
            self.replay_store.save(episode)
            return EpisodeResult(
                episode_id=episode_id,
                runtime_state=self.state_machine.state,
                outcome=outcome,
                replay_episode=episode,
            )
        except Exception as exc:  # noqa: BLE001 - runtime captures contract faults.
            return self._faulted_result(episode_id, recorder, exc)

    def _faulted_result(
        self,
        episode_id: str,
        recorder: ReplayRecorder,
        exc: Exception,
    ) -> EpisodeResult:
        if not self.state_machine.terminal:
            try:
                self.state_machine.transition(RuntimeState.FAULTED)
            except RuntimeContractError:
                self.state_machine.state = RuntimeState.FAULTED
        episode = recorder.finish(EpisodeOutcome.NO_OUTCOME)
        self.replay_store.save(episode)
        return EpisodeResult(
            episode_id=episode_id,
            runtime_state=RuntimeState.FAULTED,
            outcome=EpisodeOutcome.NO_OUTCOME,
            replay_episode=episode,
            runtime_error=RuntimeErrorInfo(
                error_type=type(exc).__name__,
                message=str(exc),
            ),
        )

    def _deterministic_checksum(self, context: DeterminismContext) -> str:
        debug = self.domain.privileged_debug_state()
        payload = debug.payload
        verification_state = payload.get("replay_verification_state", payload)
        if not isinstance(verification_state, dict):
            raise DomainAdapterError("replay verification state must be a dictionary")
        checksum_input: dict[str, JsonValue] = {
            "context": context.to_json_data(),
            "domain": json_compatible(verification_state),
        }
        return sha256_json(checksum_input)
