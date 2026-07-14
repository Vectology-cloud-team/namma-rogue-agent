"""ctypes-backed Rogue native backend bootstrap.

Phase 9 uses this backend to prove that the Runtime can talk to a real native
library through the Phase 8 ABI. It does not load modified Rogue game logic and
does not implement headless Rogue play.
"""

from __future__ import annotations

import ctypes
from pathlib import Path

from ..actions import (
    ActionResult,
    ActionStatus,
    RequestedAction,
    ValidatedAction,
    ValidationStatus,
)
from ..determinism import DeterminismContext
from ..domain import DomainTerminalStatus
from ..models import DomainAdapterError
from ..observations import PrivilegedDebugState
from ..state import EpisodeOutcome
from .models import (
    RogueNativeConfig,
    RogueNativeObservation,
    RoguePosition,
    RogueResetResult,
    RogueSourceIdentity,
    RogueVisibleCell,
)


ABI_MAJOR = 0
ABI_MINOR = 2
ABI_VERSION = (ABI_MAJOR << 16) | ABI_MINOR
SCHEMA_VERSION = 1

STATUS_OK = 0
STATUS_INVALID_ARGUMENT = 1
STATUS_INVALID_STATE = 2
STATUS_UNSUPPORTED = 3
STATUS_DOMAIN_TERMINAL = 4
STATUS_INTERNAL_ERROR = 5

VALIDATION_VALID = 0
VALIDATION_REJECTED_SCHEMA = 1
VALIDATION_REJECTED_OBSERVABLE_RULE = 2

ACTION_NONE = 0
ACTION_MOVE = 1
ACTION_WAIT = 2
ACTION_QUIT = 17

DIRECTION_NONE = 0
DIRECTION_VALUES = {
    "NONE": 0,
    "N": 1,
    "NE": 2,
    "E": 3,
    "SE": 4,
    "S": 5,
    "SW": 6,
    "W": 7,
    "NW": 8,
}
DIRECTION_NAMES = {value: key for key, value in DIRECTION_VALUES.items()}

TERMINAL_NONE = 0
TERMINAL_SUCCESS = 1
TERMINAL_LOSS = 2
TERMINAL_USER_ABORT = 3
TERMINAL_SAVED = 4

STATUS_NAMES = {
    STATUS_OK: "OK",
    STATUS_INVALID_ARGUMENT: "INVALID_ARGUMENT",
    STATUS_INVALID_STATE: "INVALID_STATE",
    STATUS_UNSUPPORTED: "UNSUPPORTED",
    STATUS_DOMAIN_TERMINAL: "DOMAIN_TERMINAL",
    STATUS_INTERNAL_ERROR: "INTERNAL_ERROR",
}
VALIDATION_NAMES = {
    VALIDATION_VALID: ValidationStatus.VALID,
    VALIDATION_REJECTED_SCHEMA: ValidationStatus.REJECTED_SCHEMA,
    VALIDATION_REJECTED_OBSERVABLE_RULE: ValidationStatus.REJECTED_OBSERVABLE_RULE,
}
ACTION_VALUES = {
    "MOVE": ACTION_MOVE,
    "WAIT": ACTION_WAIT,
    "QUIT": ACTION_QUIT,
}
TERMINAL_OUTCOMES = {
    TERMINAL_NONE: EpisodeOutcome.NO_OUTCOME,
    TERMINAL_SUCCESS: EpisodeOutcome.SUCCESS,
    TERMINAL_LOSS: EpisodeOutcome.DOMAIN_LOSS,
    TERMINAL_USER_ABORT: EpisodeOutcome.USER_ABORT,
    TERMINAL_SAVED: EpisodeOutcome.USER_ABORT,
}


class RogueNativeBackendError(DomainAdapterError):
    """Base class for native backend bootstrap failures."""


class RogueLibraryLoadError(RogueNativeBackendError):
    """Raised when the native shared library cannot be loaded."""


class RogueAbiVersionError(RogueNativeBackendError):
    """Raised when the native library ABI version is incompatible."""


class RogueSymbolMissingError(RogueNativeBackendError):
    """Raised when a required native symbol is absent."""


class RogueCreateError(RogueNativeBackendError):
    """Raised when native create fails."""


class RogueResetError(RogueNativeBackendError):
    """Raised when native reset fails."""


class RogueObserveError(RogueNativeBackendError):
    """Raised when native observe fails."""


class RogueActionError(RogueNativeBackendError):
    """Raised when native action validation or application fails."""


class RogueTerminalStatusError(RogueNativeBackendError):
    """Raised when native terminal status fails."""


class RogueSourceIdentityError(RogueNativeBackendError):
    """Raised when native source identity retrieval fails."""


class RogueCloseError(RogueNativeBackendError):
    """Raised when native close or destroy fails."""


class NammaRogueConfig(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("abi_version", ctypes.c_uint32),
        ("flags", ctypes.c_uint32),
    ]


class NammaRogueResetRequest(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("schema_version", ctypes.c_uint32),
        ("world_seed", ctypes.c_uint64),
        ("episode_seed", ctypes.c_uint64),
    ]


class NammaRogueResetResult(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("schema_version", ctypes.c_uint32),
        ("status", ctypes.c_uint32),
    ]


class NammaRoguePosition(ctypes.Structure):
    _fields_ = [
        ("y", ctypes.c_int32),
        ("x", ctypes.c_int32),
    ]


class NammaRogueVisibleCell(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("position", NammaRoguePosition),
        ("glyph", ctypes.c_uint32),
        ("terrain", ctypes.c_uint32),
        ("walkable", ctypes.c_uint8),
        ("reserved0", ctypes.c_uint8 * 3),
    ]


class NammaRogueObservation(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("schema_version", ctypes.c_uint32),
        ("dungeon_level", ctypes.c_uint32),
        ("player_position", NammaRoguePosition),
        ("hp", ctypes.c_int32),
        ("hp_max", ctypes.c_int32),
        ("terminal", ctypes.c_uint8),
        ("reserved0", ctypes.c_uint8 * 7),
        ("visible_cells", ctypes.POINTER(NammaRogueVisibleCell)),
        ("visible_cell_count", ctypes.c_size_t),
        ("recent_message", ctypes.c_char_p),
        ("terminal_reason", ctypes.c_char_p),
        ("turn", ctypes.c_uint64),
    ]


class NammaRogueRequestedAction(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("schema_version", ctypes.c_uint32),
        ("action_type", ctypes.c_uint32),
        ("direction", ctypes.c_uint32),
        ("item_slot", ctypes.c_uint32),
        ("flags", ctypes.c_uint32),
    ]


class NammaRogueValidatedAction(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("schema_version", ctypes.c_uint32),
        ("accepted", ctypes.c_uint8),
        ("reserved0", ctypes.c_uint8 * 3),
        ("validation_status", ctypes.c_uint32),
        ("normalized_action", NammaRogueRequestedAction),
        ("message", ctypes.c_char_p),
    ]


class NammaRogueActionResult(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("schema_version", ctypes.c_uint32),
        ("status", ctypes.c_uint32),
        ("terminal_kind", ctypes.c_uint32),
        ("consumed_turn", ctypes.c_uint8),
        ("reserved0", ctypes.c_uint8 * 7),
        ("message", ctypes.c_char_p),
    ]


class NammaRogueTerminalStatus(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("schema_version", ctypes.c_uint32),
        ("terminal", ctypes.c_uint8),
        ("reserved0", ctypes.c_uint8 * 3),
        ("terminal_kind", ctypes.c_uint32),
        ("reason", ctypes.c_char_p),
    ]


class NammaRogueDebugState(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("schema_version", ctypes.c_uint32),
        ("deterministic_checksum", ctypes.c_uint64),
        ("snapshot_data", ctypes.c_void_p),
        ("snapshot_size", ctypes.c_size_t),
    ]


class NammaRogueSourceIdentity(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("abi_version", ctypes.c_uint32),
        ("upstream_identity", ctypes.c_char_p),
        ("upstream_archive_sha256", ctypes.c_char_p),
        ("compatibility_patch_identity", ctypes.c_char_p),
        ("source_commit", ctypes.c_char_p),
        ("build_identity", ctypes.c_char_p),
        ("compiler_identity", ctypes.c_char_p),
    ]


class CtypesRogueNativeBackend:
    """Real native-library bootstrap backend for Rogue."""

    def __init__(self, library_path: str | Path) -> None:
        self.library_path = Path(library_path)
        self._library = self._load_library(self.library_path)
        self._bind_abi_symbol()
        self._abi_version = int(self._namma_rogue_abi_version())
        self._check_abi_version(self._abi_version)
        self._bind_required_symbols()
        self._handle = ctypes.c_void_p()
        self._created = False
        self._closed = False
        self.config = RogueNativeConfig(
            source_identity=RogueSourceIdentity(
                identity_scope="phase9_native_bootstrap",
                upstream_identity="Rogueforge Rogue 5.4.4",
                upstream_archive_sha256="reported-by-native-library",
                compatibility_patch_identity="reported-by-native-library",
                source_commit="reported-by-native-library",
                build_identity=f"ctypes:{self.library_path.name}",
                compiler_identity="reported-by-native-library",
                abi_version=self.abi_version_text,
            ),
            supported_action_types=("WAIT", "QUIT"),
        )

    @property
    def abi_version_text(self) -> str:
        return f"{self._abi_version >> 16}.{self._abi_version & 0xFFFF}"

    def create(self, config: RogueNativeConfig) -> None:
        if self._created and not self._closed:
            return
        native_config = NammaRogueConfig()
        native_config.struct_size = ctypes.sizeof(native_config)
        native_config.abi_version = ABI_VERSION
        native_config.flags = 0
        out_handle = ctypes.c_void_p()
        status = self._namma_rogue_create(
            ctypes.byref(native_config),
            ctypes.byref(out_handle),
        )
        if status != STATUS_OK or not out_handle.value:
            raise RogueCreateError(self._status_message("create", status))
        self._handle = out_handle
        self._created = True
        self._closed = False

    def reset(self, context: DeterminismContext) -> RogueResetResult:
        handle = self._require_handle()
        request = NammaRogueResetRequest()
        request.struct_size = ctypes.sizeof(request)
        request.schema_version = SCHEMA_VERSION
        request.world_seed = context.world_seed
        request.episode_seed = context.episode_seed
        result = NammaRogueResetResult()
        result.struct_size = ctypes.sizeof(result)
        status = self._namma_rogue_reset(
            handle,
            ctypes.byref(request),
            ctypes.byref(result),
        )
        if status != STATUS_OK or result.status != STATUS_OK:
            raise RogueResetError(self._status_message("reset", status or result.status))
        return RogueResetResult(
            schema_version=self.config.native_schema_version,
            status="OK",
        )

    def observe(self) -> RogueNativeObservation:
        handle = self._require_handle()
        observation = NammaRogueObservation()
        observation.struct_size = ctypes.sizeof(observation)
        status = self._namma_rogue_observe(handle, ctypes.byref(observation))
        if status != STATUS_OK:
            raise RogueObserveError(self._status_message("observe", status))
        return RogueNativeObservation(
            schema_version=self.config.native_schema_version,
            dungeon_level=int(observation.dungeon_level),
            player_position=RoguePosition(
                int(observation.player_position.y),
                int(observation.player_position.x),
            ),
            hp=int(observation.hp),
            hp_max=int(observation.hp_max),
            visible_cells=self._visible_cells(observation),
            recent_message=self._decode(observation.recent_message),
            turn=int(observation.turn),
            terminal=bool(observation.terminal),
            terminal_reason=self._decode(observation.terminal_reason),
        )

    def validate_action(self, action: RequestedAction) -> ValidatedAction:
        native_action = self._requested_action(action)
        validated = NammaRogueValidatedAction()
        validated.struct_size = ctypes.sizeof(validated)
        status = self._namma_rogue_validate_action(
            self._require_handle(),
            ctypes.byref(native_action),
            ctypes.byref(validated),
        )
        if status != STATUS_OK:
            raise RogueActionError(self._status_message("validate_action", status))
        validation_status = VALIDATION_NAMES.get(
            int(validated.validation_status),
            ValidationStatus.REJECTED_SCHEMA,
        )
        normalized = self._normalized_parameters(validated.normalized_action)
        return ValidatedAction(
            requested_action=action,
            normalized_parameters=normalized,
            validation_status=validation_status,
            message=self._decode(validated.message),
        )

    def apply_action(self, action: ValidatedAction, turn: int) -> ActionResult:
        if not action.accepted:
            raise RogueActionError("cannot apply a rejected native Rogue action")
        native_validated = NammaRogueValidatedAction()
        native_validated.struct_size = ctypes.sizeof(native_validated)
        native_validated.schema_version = SCHEMA_VERSION
        native_validated.accepted = 1
        native_validated.validation_status = VALIDATION_VALID
        native_validated.normalized_action = self._requested_action(
            action.requested_action,
            action.normalized_parameters,
        )
        result = NammaRogueActionResult()
        result.struct_size = ctypes.sizeof(result)
        status = self._namma_rogue_apply_action(
            self._require_handle(),
            ctypes.byref(native_validated),
            ctypes.byref(result),
        )
        if status != STATUS_OK:
            raise RogueActionError(self._status_message("apply_action", status))
        action_status = (
            ActionStatus.DOMAIN_TERMINAL
            if result.status == STATUS_DOMAIN_TERMINAL
            else ActionStatus.SUCCESS
        )
        action_type = action.requested_action.action_type.upper()
        domain_events = [action_type.lower()]
        terminal = result.terminal_kind != TERMINAL_NONE
        return ActionResult(
            action_id=f"turn-{turn}",
            status=action_status,
            message=self._decode(result.message),
            domain_events=domain_events,
            terminal=terminal,
        )

    def terminal_status(self) -> DomainTerminalStatus:
        status_struct = NammaRogueTerminalStatus()
        status_struct.struct_size = ctypes.sizeof(status_struct)
        status = self._namma_rogue_terminal_status(
            self._require_handle(),
            ctypes.byref(status_struct),
        )
        if status != STATUS_OK:
            raise RogueTerminalStatusError(
                self._status_message("terminal_status", status)
            )
        terminal_kind = int(status_struct.terminal_kind)
        return DomainTerminalStatus(
            terminal=bool(status_struct.terminal),
            outcome=TERMINAL_OUTCOMES.get(terminal_kind, EpisodeOutcome.NO_OUTCOME),
            reason=self._decode(status_struct.reason),
        )

    def privileged_debug_state(self) -> PrivilegedDebugState:
        debug = NammaRogueDebugState()
        debug.struct_size = ctypes.sizeof(debug)
        status = self._namma_rogue_debug_state(
            self._require_handle(),
            ctypes.byref(debug),
        )
        if status != STATUS_OK:
            raise RogueActionError(self._status_message("debug_state", status))
        return PrivilegedDebugState(
            domain_name="rogue",
            payload={
                "replay_verification_state": {
                    "native_checksum": int(debug.deterministic_checksum),
                    "snapshot_size": int(debug.snapshot_size),
                },
            },
        )

    def source_identity(self) -> RogueSourceIdentity:
        identity = NammaRogueSourceIdentity()
        identity.struct_size = ctypes.sizeof(identity)
        status = self._namma_rogue_source_identity(
            self._require_handle(),
            ctypes.byref(identity),
        )
        if status != STATUS_OK:
            raise RogueSourceIdentityError(
                self._status_message("source_identity", status)
            )
        abi_version = int(identity.abi_version)
        return RogueSourceIdentity(
            identity_scope="phase9_native_bootstrap",
            upstream_identity=self._decode(identity.upstream_identity),
            upstream_archive_sha256=self._decode(identity.upstream_archive_sha256),
            compatibility_patch_identity=self._decode(
                identity.compatibility_patch_identity
            ),
            source_commit=self._decode(identity.source_commit),
            build_identity=self._decode(identity.build_identity),
            compiler_identity=self._decode(identity.compiler_identity),
            abi_version=f"{abi_version >> 16}.{abi_version & 0xFFFF}",
        )

    def close(self) -> None:
        if self._closed:
            return
        if self._created and self._handle.value:
            try:
                self._namma_rogue_destroy(self._handle)
            except Exception as exc:  # noqa: BLE001 - native close boundary.
                raise RogueCloseError(f"native destroy failed: {exc}") from exc
        self._handle = ctypes.c_void_p()
        self._closed = True

    def _load_library(self, library_path: Path) -> ctypes.CDLL:
        try:
            return ctypes.CDLL(str(library_path))
        except OSError as exc:
            raise RogueLibraryLoadError(
                f"failed to load Rogue native library {library_path}: {exc}"
            ) from exc

    def _bind_abi_symbol(self) -> None:
        self._namma_rogue_abi_version = self._bind(
            "namma_rogue_abi_version",
            ctypes.c_uint32,
            [],
        )

    def _bind_required_symbols(self) -> None:
        self._namma_rogue_create = self._bind(
            "namma_rogue_create",
            ctypes.c_uint32,
            [
                ctypes.POINTER(NammaRogueConfig),
                ctypes.POINTER(ctypes.c_void_p),
            ],
        )
        self._namma_rogue_reset = self._bind(
            "namma_rogue_reset",
            ctypes.c_uint32,
            [
                ctypes.c_void_p,
                ctypes.POINTER(NammaRogueResetRequest),
                ctypes.POINTER(NammaRogueResetResult),
            ],
        )
        self._namma_rogue_observe = self._bind(
            "namma_rogue_observe",
            ctypes.c_uint32,
            [
                ctypes.c_void_p,
                ctypes.POINTER(NammaRogueObservation),
            ],
        )
        self._namma_rogue_validate_action = self._bind(
            "namma_rogue_validate_action",
            ctypes.c_uint32,
            [
                ctypes.c_void_p,
                ctypes.POINTER(NammaRogueRequestedAction),
                ctypes.POINTER(NammaRogueValidatedAction),
            ],
        )
        self._namma_rogue_apply_action = self._bind(
            "namma_rogue_apply_action",
            ctypes.c_uint32,
            [
                ctypes.c_void_p,
                ctypes.POINTER(NammaRogueValidatedAction),
                ctypes.POINTER(NammaRogueActionResult),
            ],
        )
        self._namma_rogue_terminal_status = self._bind(
            "namma_rogue_terminal_status",
            ctypes.c_uint32,
            [
                ctypes.c_void_p,
                ctypes.POINTER(NammaRogueTerminalStatus),
            ],
        )
        self._namma_rogue_debug_state = self._bind(
            "namma_rogue_debug_state",
            ctypes.c_uint32,
            [
                ctypes.c_void_p,
                ctypes.POINTER(NammaRogueDebugState),
            ],
        )
        self._namma_rogue_source_identity = self._bind(
            "namma_rogue_source_identity",
            ctypes.c_uint32,
            [
                ctypes.c_void_p,
                ctypes.POINTER(NammaRogueSourceIdentity),
            ],
        )
        self._namma_rogue_destroy = self._bind(
            "namma_rogue_destroy",
            None,
            [ctypes.c_void_p],
        )

    def _bind(self, name: str, restype, argtypes):
        try:
            symbol = getattr(self._library, name)
        except AttributeError as exc:
            raise RogueSymbolMissingError(
                f"required Rogue native symbol is missing: {name}"
            ) from exc
        symbol.restype = restype
        symbol.argtypes = argtypes
        return symbol

    def _check_abi_version(self, version: int) -> None:
        major = version >> 16
        minor = version & 0xFFFF
        if major != ABI_MAJOR:
            raise RogueAbiVersionError(
                f"unsupported Rogue ABI major {major}, expected {ABI_MAJOR}"
            )
        if minor < ABI_MINOR:
            raise RogueAbiVersionError(
                f"Rogue ABI minor {minor} is older than required {ABI_MINOR}"
            )

    def _require_handle(self) -> ctypes.c_void_p:
        if self._closed or not self._created or not self._handle.value:
            raise RogueNativeBackendError("Rogue native backend handle is not active")
        return self._handle

    def _requested_action(
        self,
        action: RequestedAction,
        normalized_parameters: dict | None = None,
    ) -> NammaRogueRequestedAction:
        action_type = action.action_type.upper()
        parameters = normalized_parameters or action.parameters
        native = NammaRogueRequestedAction()
        native.struct_size = ctypes.sizeof(native)
        native.schema_version = SCHEMA_VERSION
        native.action_type = ACTION_VALUES.get(action_type, ACTION_NONE)
        direction = str(parameters.get("direction", "NONE")).upper()
        native.direction = DIRECTION_VALUES.get(direction, DIRECTION_NONE)
        native.item_slot = 0
        native.flags = 0
        return native

    def _normalized_parameters(
        self,
        action: NammaRogueRequestedAction,
    ) -> dict[str, str]:
        if action.direction == DIRECTION_NONE:
            return {}
        return {"direction": DIRECTION_NAMES.get(int(action.direction), "NONE")}

    def _visible_cells(
        self,
        observation: NammaRogueObservation,
    ) -> tuple[RogueVisibleCell, ...]:
        cells: list[RogueVisibleCell] = []
        if not observation.visible_cells:
            return ()
        for index in range(int(observation.visible_cell_count)):
            native = observation.visible_cells[index]
            cells.append(
                RogueVisibleCell(
                    position=RoguePosition(
                        int(native.position.y),
                        int(native.position.x),
                    ),
                    glyph=chr(native.glyph) if native.glyph else "",
                    terrain=str(int(native.terrain)),
                    walkable=bool(native.walkable),
                )
            )
        return tuple(cells)

    def _decode(self, value: bytes | None) -> str:
        if value is None:
            return ""
        return value.decode("utf-8", errors="replace")

    def _status_message(self, operation: str, status: int) -> str:
        status_name = STATUS_NAMES.get(int(status), f"UNKNOWN_STATUS_{int(status)}")
        return f"native {operation} failed with {status_name}"
