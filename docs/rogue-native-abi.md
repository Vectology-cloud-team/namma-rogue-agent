# Rogue Native ABI

Phase 8 defines the intended boundary between the Python Runtime and future
native Rogue 5.4.4 integration. The real Rogue native implementation is not
added in Phase 8.

The specification header lives at:

```text
adapter/native/include/namma_rogue_api.h
```

## Design Goals

The ABI should:

- use a C ABI,
- use an opaque handle,
- expose fixed-width integer fields,
- carry an ABI version,
- return explicit status codes,
- avoid C enum storage in public structures,
- work from C and C++ callers,
- avoid Python-specific types,
- avoid curses types,
- avoid exposing Rogue internal structs,
- avoid direct access to Rogue global symbols,
- stay behind the Python `RogueNativeBackend` Protocol.

## Host Native ABI Scope

This ABI is an in-process host native ABI.

It is not:

- an Ethernet wire protocol,
- an OCuLink or PCIe DMA layout,
- a shared-memory ABI,
- a serialized replay format,
- a NaMMA transport protocol.

Reason:

- it contains pointer fields,
- it contains `size_t`,
- it assumes backend-owned memory lifetime rules,
- it depends on host compiler ABI and alignment.

Future NaMMA communication must use a separate Transport Adapter and an
explicit serialized format. Phase 8 does not choose that transport format.

## Explicit Non-Goals

The ABI must not:

- return `THING *` or other Rogue internal pointers,
- return `WINDOW *` or other curses pointers,
- let callers mutate Rogue internal memory,
- require JSON strings as the core data model,
- require C-to-Python callbacks,
- propagate exceptions or `longjmp` across the boundary,
- terminate the host process with `exit()`,
- read standard input inside action functions,
- ask interactive confirmation questions.

## Versioning

The header defines:

- `NAMMA_ROGUE_ABI_VERSION_MAJOR`
- `NAMMA_ROGUE_ABI_VERSION_MINOR`
- `NAMMA_ROGUE_ABI_VERSION`

Policy:

- major changes may break binary or semantic compatibility,
- minor changes add backward-compatible capabilities,
- enum values must not be reordered,
- status, action type, direction, and terminal kind are `uint32_t` typedefs
  with fixed macro values,
- request and result structs carry `struct_size`,
- request and observation schemas may carry independent schema versions,
- future extensions should be capability-reported, not guessed.

Large reserved areas are avoided in Phase 8. `struct_size` is the preferred
forward-compatibility mechanism for early development.

Unknown future integer values must not cause undefined behavior. A callee may
return `NAMMA_ROGUE_UNSUPPORTED` or `NAMMA_ROGUE_INVALID_ARGUMENT` when it
receives a value that it does not implement.

## Main API Shape

The Phase 8 header declares these main entry points:

- `namma_rogue_abi_version`
- `namma_rogue_create`
- `namma_rogue_reset`
- `namma_rogue_observe`
- `namma_rogue_validate_action`
- `namma_rogue_apply_action`
- `namma_rogue_terminal_status`
- `namma_rogue_debug_state`
- `namma_rogue_source_identity`
- `namma_rogue_destroy`

`namma_rogue_handle_t` is opaque. Callers cannot inspect or mutate Rogue
state directly.

## Reset Contract

`namma_rogue_reset` initializes or reinitializes the domain and returns only a
reset result:

- `struct_size`,
- `schema_version`,
- `status`.

The reset result does not contain an observation and does not contain domain
events. The Python `RogueDomainAdapter.reset()` mirrors this contract:

1. call backend `reset`,
2. call backend `observe`,
3. call backend `source_identity`.

The adapter builds Runtime `DomainResetResult` from the post-reset
observation and source identity. This keeps the C ABI reset result small and
avoids a partial observation contract inside reset.

## Observation Contract

Phase 8 chooses the smaller Phase 9 starting point:

- C ABI observation returns one `recent_message`,
- C ABI observation does not return available action types,
- Python `RogueNativeObservation` also carries one `recent_message`,
- `RogueDomainAdapter` attaches available action types from static Phase 8
  capability data.

`visible_cells` are a backend-owned read-only array plus count. Each cell
carries position, glyph, terrain, and walkability. `terminal_reason` is a
backend-owned read-only string with the same pointer lifetime rules as
`recent_message`.

## Domain Events

The Phase 8 C ABI does not return domain events from reset or action calls.
It deliberately does not expose event counts without event data. If a future C
ABI returns domain events, it must define:

- an event structure,
- an event array,
- an event count,
- pointer lifetime,
- schema version.

The Python fake backend may still include Runtime `ActionResult.domain_events`
for tests and Replay Level 1. These events are Python-side adapter artifacts,
not C ABI reset-result fields.

## Struct Initialization

Public structs use this convention:

- callers zero-initialize structures,
- callers set `struct_size` to `sizeof(the struct they pass)`,
- callers set the relevant schema or ABI version fields,
- callees check that `struct_size` is at least the minimum supported size,
- callees do not write beyond caller-provided `struct_size`,
- unknown trailing fields are ignored,
- major ABI mismatch returns `NAMMA_ROGUE_UNSUPPORTED`,
- minor ABI versions may add backward-compatible fields or functions,
- output pointers must not be used after a failed call unless the function
  explicitly documents otherwise.

Phase 8 has no real C implementation, so short-`struct_size` behavior is
specified rather than executed. Phase 9 implementation tests must include a
stub or real backend case where a too-small struct returns
`NAMMA_ROGUE_INVALID_ARGUMENT` or `NAMMA_ROGUE_UNSUPPORTED` before writing
output.

## Memory Ownership

Phase 8 compares two ownership models.

### Option 1: Caller-Allocated Buffers

The caller allocates fixed headers and data buffers. The C side fills them and
returns the required capacity when buffers are too small.

Advantages:

- clear ownership,
- stable across language boundaries,
- easy cleanup responsibility,
- friendly to FFI callers.

Disadvantages:

- more boilerplate,
- caller must perform query and fill calls for variable-length data,
- early prototypes are slightly slower to write.

### Option 2: Backend-Owned Snapshots

The C side owns an immutable snapshot that stays valid until the next ABI call
or until reset.

Advantages:

- simpler initial observe calls,
- fewer allocation steps,
- easier to mirror existing Rogue globals.

Disadvantages:

- lifetime rules are easier to misuse,
- references become invalid after reset or next call,
- thread-safety is weaker,
- language bindings need careful copying.

## Phase 8 Recommendation

Use caller-allocated fixed header structures with a query pattern for
variable-length arrays.

Phase 9 may temporarily implement one process, one handle, and one thread.
That profile should be reported as a capability, not encoded as a permanent
ABI limit.

Rules:

- the caller owns the handle after `namma_rogue_create` succeeds,
- `namma_rogue_destroy` releases the handle,
- using a destroyed handle is invalid,
- observations do not expose writable Rogue internals,
- pointer data returned by C is immutable and valid only for the documented
  lifetime,
- reset invalidates prior observation, message, identity, and debug-state
  references,
- variable-length cells, inventory, and messages should use capacity/query
  patterns before production use.

Initial pointer lifetime rule:

- memory is owned by the handle or backend,
- callers must not free or modify it,
- pointers are valid until the next mutating API call on the same handle,
- pointers are invalidated by `namma_rogue_reset`,
- pointers are invalidated by `namma_rogue_destroy`,
- the initial implementation profile is not thread-safe,
- callers must copy data when a longer lifetime is required.

Pointer fields covered by this rule:

- `visible_cells`,
- `recent_message`,
- `terminal_reason`,
- validated action `message`,
- action result `message`,
- terminal status `reason`,
- debug state `snapshot_data`,
- all source identity strings.

Consecutive `namma_rogue_observe()` calls are read-only from the ABI
perspective, but a backend may refresh internal scratch buffers while serving
an observe call. Callers that need to retain previous observation pointers
must copy the data before any later ABI call.

## Source Identity

The native backend must be able to report:

- upstream identity,
- upstream archive SHA-256,
- compatibility patch identity,
- source commit,
- build identity,
- compiler identity,
- ABI version.

This identity aligns with the Phase 7 `DeterminismContext`. Exact Golden
Baseline values should be generated from one metadata source in the future
instead of copied manually into documents, Python defaults, and C build files.

The Phase 8 fake backend reports a fake-backend-scoped identity. It is not the
formal identity of a real Rogue native backend. Future real backends should
report the upstream archive SHA-256, compatibility patch hash, source commit,
compiler identity, and build identity from generated build metadata.

## Terminal And Error Semantics

Status codes indicate ABI-call success or failure. Domain terminal conditions
are reported separately through terminal status and action results.

Important distinction:

- `NAMMA_ROGUE_INVALID_ARGUMENT` means the ABI request is malformed.
- `NAMMA_ROGUE_INVALID_STATE` means the handle or lifecycle state is wrong.
- `NAMMA_ROGUE_DOMAIN_TERMINAL` means the domain is already terminal.
- terminal success, loss, abort, or save are Rogue domain outcomes, not
  process exits.

Native backend or ABI errors are status-code failures and map to
`DomainAdapterError` on the Python side. They are not terminal kinds. A runtime
fault is represented as RuntimeState `FAULTED` and EpisodeOutcome
`NO_OUTCOME`.

Action validation uses `namma_rogue_validation_status_t`, not
`namma_rogue_status_t`.

| Validation value | Meaning |
| --- | --- |
| `NAMMA_ROGUE_VALIDATION_VALID` | The action is valid for application. |
| `NAMMA_ROGUE_VALIDATION_REJECTED_SCHEMA` | The request does not match the action schema. |
| `NAMMA_ROGUE_VALIDATION_REJECTED_OBSERVABLE_RULE` | The request is rejected using observable rules only. |

`namma_rogue_status_t` remains reserved for ABI call success or failure, such
as invalid pointers, unsupported ABI versions, invalid handles, or internal
errors.

Terminal kind values:

| Value | Meaning |
| --- | --- |
| `NAMMA_ROGUE_TERMINAL_NONE` | The Rogue episode is not terminal. |
| `NAMMA_ROGUE_TERMINAL_SUCCESS` | Rogue victory, such as amulet return. |
| `NAMMA_ROGUE_TERMINAL_LOSS` | Rogue domain loss, such as death. |
| `NAMMA_ROGUE_TERMINAL_USER_ABORT` | User or provider requested quit. |
| `NAMMA_ROGUE_TERMINAL_SAVED` | Reserved for legacy save-and-process-exit behavior. |

`NAMMA_ROGUE_TERMINAL_SAVED` is not RuntimeState `PAUSED`. Classic Rogue save
exits the process after writing the save file. Phase 9 does not implement save
through the ABI; the value is reserved so that a later implementation can
distinguish save-and-exit from success, loss, and quit.

`NAMMA_ROGUE_TERMINAL_RUNTIME_ERROR` is deliberately not defined. Runtime and
native backend errors use `namma_rogue_status_t`.

Phase 9 must replace direct `exit()` paths with host-visible terminal results
before in-process integration is safe.

## Layout Verification

The compile-only native tests verify that:

- status, action type, direction, and terminal kind are 32-bit fields,
- important fixed-size structs have stable offsets and sizes,
- pointer-containing structs have offsets computed from pointer alignment,
- C and C++ see the same header layout rules.

Structs containing pointers or `size_t` can differ between 32-bit and 64-bit
builds. Tests therefore use pointer-size and alignment formulas for those
offsets instead of hard-coding 64-bit sizes into the ABI specification.

## C++ Boundary

The header is C-compatible and wraps declarations in `extern "C"` when
included from C++.

C++ name mangling must not be part of the ABI contract.
