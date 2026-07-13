"""Rogue DomainAdapter implementation backed by RogueNativeBackend."""

from __future__ import annotations

from ..actions import RequestedAction, ValidatedAction, ValidationStatus
from ..determinism import DeterminismContext
from ..domain import DomainResetResult, DomainTerminalStatus
from ..models import DomainAdapterError
from ..observations import AgentObservation, DomainState, PrivilegedDebugState
from .backend import RogueNativeBackend
from .models import (
    PHASE8_SUPPORTED_ACTION_TYPES,
    ROGUE_DIRECTIONS,
    RogueNativeConfig,
)


class RogueDomainAdapter:
    """Runtime DomainAdapter for Rogue.

    Phase 8 uses only a fake native backend. A real C ABI backend is deferred.
    """

    def __init__(
        self,
        backend: RogueNativeBackend,
        config: RogueNativeConfig | None = None,
    ) -> None:
        self._backend = backend
        self._config = config or RogueNativeConfig()
        self._created = False
        self._closed = False

    def reset(self, context: DeterminismContext) -> DomainResetResult:
        self._ensure_open()
        if not self._created:
            self._call_backend("create", self._backend.create, self._config)
            self._created = True
        result = self._call_backend("reset", self._backend.reset, context)
        identity = self._call_backend("source_identity", self._backend.source_identity)
        return DomainResetResult(
            domain_state=DomainState(
                domain_name="rogue",
                payload={
                    "source_identity": identity.to_json_data(),
                    "observation": result.observation.to_agent_payload(),
                },
            ),
            domain_events=list(result.domain_events),
        )

    def observe(self, episode_id: str, turn: int) -> AgentObservation:
        self._ensure_open()
        native = self._call_backend("observe", self._backend.observe)
        return AgentObservation(
            schema_version=self._config.observation_schema_version,
            episode_id=episode_id,
            turn=turn,
            task="play_rogue",
            payload=native.to_agent_payload(),
            available_action_types=list(native.available_action_types),
        )

    def validate_action(self, action: RequestedAction) -> ValidatedAction:
        self._ensure_open()
        schema_rejection = self._schema_rejection(action)
        if schema_rejection is not None:
            return schema_rejection
        return self._call_backend(
            "validate_action",
            self._backend.validate_action,
            action,
        )

    def apply_action(self, action: ValidatedAction, turn: int):
        self._ensure_open()
        if not action.accepted:
            raise DomainAdapterError("cannot apply rejected Rogue action")
        return self._call_backend(
            "apply_action",
            self._backend.apply_action,
            action,
            turn,
        )

    def terminal_status(self) -> DomainTerminalStatus:
        self._ensure_open()
        return self._call_backend("terminal_status", self._backend.terminal_status)

    def privileged_debug_state(self) -> PrivilegedDebugState:
        self._ensure_open()
        return self._call_backend(
            "privileged_debug_state",
            self._backend.privileged_debug_state,
        )

    def close(self) -> None:
        if self._closed:
            return
        self._call_backend("close", self._backend.close)
        self._closed = True

    def _schema_rejection(self, action: RequestedAction) -> ValidatedAction | None:
        action_type = action.action_type.upper()
        if action_type not in PHASE8_SUPPORTED_ACTION_TYPES:
            return ValidatedAction(
                requested_action=action,
                normalized_parameters={},
                validation_status=ValidationStatus.REJECTED_SCHEMA,
                message=f"unsupported Phase 8 Rogue action {action.action_type!r}",
            )

        if action_type == "MOVE":
            direction = str(action.parameters.get("direction", "")).upper()
            if direction not in ROGUE_DIRECTIONS or direction == "NONE":
                return ValidatedAction(
                    requested_action=action,
                    normalized_parameters={},
                    validation_status=ValidationStatus.REJECTED_SCHEMA,
                    message="MOVE requires a compass direction",
                )
        return None

    def _ensure_open(self) -> None:
        if self._closed:
            raise DomainAdapterError("RogueDomainAdapter is closed")

    def _call_backend(self, operation: str, method, *args):
        try:
            return method(*args)
        except DomainAdapterError:
            raise
        except Exception as exc:  # noqa: BLE001 - adapter boundary wraps backend faults.
            raise DomainAdapterError(
                f"Rogue native backend {operation} failed: {exc}"
            ) from exc
