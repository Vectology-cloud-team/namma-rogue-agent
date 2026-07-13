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
- work from C and C++ callers,
- avoid Python-specific types,
- avoid curses types,
- avoid exposing Rogue internal structs,
- avoid direct access to Rogue global symbols,
- be independent of transport choice.

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
- request and result structs carry `struct_size`,
- request and observation schemas may carry independent schema versions,
- future extensions should be capability-reported, not guessed.

Large reserved areas are avoided in Phase 8. `struct_size` is the preferred
forward-compatibility mechanism for early development.

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
- strings returned by C are immutable and valid only for the documented
  lifetime,
- reset invalidates prior observation and debug-state references,
- variable-length cells, inventory, and messages should use capacity/query
  patterns before production use.

## Source Identity

The native backend must be able to report:

- upstream identity,
- upstream archive SHA-256,
- compatibility patch identity,
- source commit,
- build identity,
- compiler identity,
- ABI version.

This identity aligns with the Phase 7 `DeterminismContext`. The exact Golden
Baseline values should be referenced from the Golden Source documents or build
metadata instead of copied manually into many places.

## Terminal And Error Semantics

Status codes indicate ABI-call success or failure. Domain terminal conditions
are reported separately through terminal status and action results.

Important distinction:

- `NAMMA_ROGUE_INVALID_ARGUMENT` means the ABI request is malformed.
- `NAMMA_ROGUE_INVALID_STATE` means the handle or lifecycle state is wrong.
- `NAMMA_ROGUE_DOMAIN_TERMINAL` means the domain is already terminal.
- terminal success, loss, abort, save, or error are domain outcomes, not
  process exits.

Phase 9 must replace direct `exit()` paths with host-visible terminal results
before in-process integration is safe.

## C++ Boundary

The header is C-compatible and wraps declarations in `extern "C"` when
included from C++.

C++ name mangling must not be part of the ABI contract.
