# ADR 0001: Rogue Native Boundary

Status: Proposed

Date: 2026-07-13

## Context

The runtime needs a stable boundary between Python orchestration and Rogue
5.4.4. Phase 8 designs this boundary but does not headless Rogue and does not
connect to a real native library.

The boundary must support deterministic reset and step later, avoid curses as
the AI control contract, and preserve a human-compatible Rogue build.

## Option A: In-Process C ABI Shared Library

Advantages:

- direct access to authoritative state,
- low latency,
- clear reset and step boundary,
- good fit for NaMMA evaluation loops,
- no PTY dependency,
- source and build identity can be reported directly.

Disadvantages:

- Rogue global state must be contained,
- `exit()`, signals, and curses paths must be refactored,
- ABI memory ownership must be designed carefully,
- process crashes are not isolated by default.

## Option B: Subprocess Plus PTY

Advantages:

- fewer immediate source changes,
- close to human terminal execution,
- useful for diagnostics and smoke checks.

Disadvantages:

- terminal size and escape sequences become control dependencies,
- screen diffing is brittle,
- state extraction is incomplete,
- hidden-state boundaries are ambiguous,
- reset and replay are fragile,
- deterministic checksums are hard to define.

## Option C: Subprocess Plus Structured IPC In Rogue

Advantages:

- process isolation,
- abnormal exits are easier to contain,
- JSONL or binary logs can aid debugging,
- can reuse some action and observation schemas.

Disadvantages:

- serialization overhead,
- two lifecycles must be managed,
- the C side still needs reset, step, and observation implementation,
- IPC transport can distract from game-state boundary design.

## Decision

Primary recommendation:

- in-process C ABI with an opaque handle.

Diagnostic fallback:

- subprocess or PTY for launch checks and human-style smoke tests only.

Possible future isolation:

- structured subprocess IPC behind `RogueNativeBackend`.

The Runtime sees only `RogueNativeBackend`. This lets the Python adapter test
against a fake backend now and connect to a real native backend later without
changing the Runtime Orchestrator contract.

## Consequences

Phase 9 must first contain:

- `exit()` paths,
- signal and autosave behavior,
- command input,
- terminal status,
- minimal observation extraction,
- deterministic seed startup.

The Native ABI must not expose Rogue internal pointers, curses types, or
Python objects.

The selected ABI is an in-process host native ABI only. It is not an Ethernet
wire protocol, OCuLink or PCIe DMA layout, shared-memory ABI, serialized
replay format, or NaMMA transport protocol. The reason is that the ABI uses
pointers, `size_t`, backend-owned memory lifetimes, and host compiler layout
rules. Future NaMMA communication must sit behind a separate Transport
Adapter with an explicit serialized representation.

Phase 8 also chooses the smaller initial observation contract: one
`recent_message` in the C ABI and Python native observation, with available
action types supplied by `RogueDomainAdapter` as static capability data. Reset
returns only reset status; the adapter calls observe and source-identity
queries after reset succeeds.
