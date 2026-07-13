# Runtime Contract

This document summarizes the Phase 7 Runtime Contract reference
implementation. The Python code is a reference implementation of the
logical contract, not a permanent protocol choice.

## Scope

Included:

- RuntimeState and EpisodeOutcome.
- DomainAdapter Protocol.
- DecisionProvider Protocol.
- Observation boundary dataclasses.
- Action lifecycle dataclasses.
- DeterminismContext.
- Replay Level 1 event model.
- Fake Domain.
- Fake DecisionProviders.
- Synchronous Runtime Orchestrator.

Excluded:

- RogueDomainAdapter.
- Rogue reset and step.
- Rogue headless conversion.
- Local AI.
- NaMMA.
- HTTP server.
- Protocol Buffers or FlatBuffers.
- Async execution.
- Multiple agents.

## Runtime Boundary

Runtime Orchestrator owns:

- runtime state,
- episode ID,
- turn,
- timeout policy,
- episode outcome,
- replay event emission.

DomainAdapter owns:

- reset,
- observation,
- schema and observable validation,
- one-action application,
- terminal status,
- privileged debug state.

DecisionProvider owns:

- deterministic or external decision generation,
- DecisionRequest to DecisionResponse conversion,
- timeout and unavailable status representation.

## Observation Boundary

`DomainState` is authoritative and domain-specific.

`AgentObservation` is safe for DecisionProvider input.

`PrivilegedDebugState` is only for tests, diagnostics, and replay
verification.

`EpisodeMemory` is agent-side memory and must not store DomainState
directly.

## Action Lifecycle

The lifecycle is:

```text
RequestedAction
ValidatedAction
accepted validation only
ExecutedAction
ActionResult
```

Rejected actions are not ExecutedAction instances. If validation returns
`REJECTED_SCHEMA` or `REJECTED_OBSERVABLE_RULE`, the Phase 7 initial
Runtime Profile treats the DecisionProvider response as a provider contract
violation, faults the Runtime, does not call `DomainAdapter.apply_action()`,
does not advance the Domain turn, and does not emit a Replay Level 1 turn
event.

In-domain attempted failure is different. If validation succeeds and the
Domain attempts the action, the Runtime creates an ExecutedAction, calls the
Domain, and records the ActionResult even when the status is
`ATTEMPT_FAILED_IN_DOMAIN`.

## Runtime Faults

Runtime faults are represented by RuntimeState `FAULTED` plus structured
runtime error information.

Runtime faults are not EpisodeOutcome values.

Rogue death or Fake Domain loss is `DOMAIN_LOSS`, not `FAULTED`.

## Orchestrator Reuse

The Phase 7 `RuntimeOrchestrator` is one-shot. A single instance runs one
episode. Calling `run_episode()` a second time raises `InvalidStateTransition`.

Future multi-episode behavior should be implemented as a separate runner
instead of silently resetting this orchestrator instance.
