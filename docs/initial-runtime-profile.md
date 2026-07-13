# Initial Runtime Profile

This document defines the Phase 7 initial implementation profile. It is
design only. It does not implement runtime code.

The runtime should avoid blocking future domains, but Phase 7 will not
implement abstractions that are not required by the Rogue single-agent
runtime profile.

## Profile

Target domain:

- Rogue only.

Actors:

- Single actor.

Concurrent episodes:

- One.

Provider call:

- Synchronous.

Turn model:

- One semantic ExecutedAction per runtime turn.

Planner:

- Optional.
- `RuleBasedDecisionProvider` may return an action directly.

Streaming:

- Not supported initially.

Batch:

- Not supported initially.

Multi-agent:

- Not supported initially.

Continuous control:

- Not supported initially.

Real-time guarantee:

- None.

Development data model:

- JSON-compatible logical objects.

Internal C boundary:

- Typed C structs.

Replay:

- Level 1 deterministic replay first.

Provider transport:

- In-process or localhost first.

NaMMA Ethernet / OCuLink:

- Deferred behind DecisionProvider interface.

PrivilegedDebugState:

- Tests and diagnostic replay only.

Timeout:

- Explicit error or configured fallback.
- Never silently reuse stale output.

## Phase 7 Required Replay Data

Level 1 deterministic replay should store:

- source and build identity,
- compatibility patch identity,
- config hash,
- world seed,
- episode seed,
- ExecutedAction sequence,
- ActionResult values,
- terminal outcome,
- turn count,
- per-turn deterministic checksum when available.

## Deferred Replay Data

These are future Level 2 or Level 3 items:

- full AgentObservation payloads,
- full provider prompts,
- full provider responses,
- PrivilegedDebugState,
- full snapshots,
- compression,
- binary format.

## Deferred Capabilities

These are future capabilities, not Phase 7 requirements:

- NetHack,
- Minecraft,
- ROS2,
- robots,
- Accuvision,
- multi-agent,
- distributed runtime,
- cloud provider,
- training,
- streaming,
- batch,
- continuous action,
- real-time control.
