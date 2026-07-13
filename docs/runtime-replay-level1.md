# Runtime Replay Level 1

Replay Level 1 is the only replay level implemented in Phase 7.

## Stored Items

Replay Level 1 stores:

- schema version,
- episode ID,
- source identity,
- build identity,
- compatibility patch identity,
- configuration hash,
- world seed,
- episode seed,
- turn,
- ExecutedAction,
- ActionResult,
- deterministic checksum,
- terminal outcome.

Replay Level 1 stores only actions that were actually executed by the
Domain. Schema validation rejection and observable-rule validation rejection
are not recorded as ExecutedAction entries because the Domain did not execute
them. In the Phase 7 initial Runtime Profile, those validation rejections are
Runtime faults and the fault detail is held in `EpisodeResult.runtime_error`.

An action that passes validation but fails inside the Domain, such as the Fake
Domain `BUMP` action, is still an ExecutedAction. It is recorded with an
ActionResult status such as `ATTEMPT_FAILED_IN_DOMAIN`.

## Not Stored

Replay Level 1 does not store:

- full PrivilegedDebugState,
- full provider prompts,
- full provider responses,
- full AgentObservation payloads,
- full snapshots,
- compressed binary payloads.

## In-Memory Store

Phase 7 uses an in-memory Replay Store. File formats are deferred.

JSONL output may be added later, but it is not required by this phase.

## Verification

Replay verification compares:

- turn count,
- ExecutedAction sequence for actions actually applied to the Domain,
- ActionResult sequence,
- deterministic checksum sequence,
- EpisodeOutcome.

Mismatches must be reported. They must not be silently ignored.
