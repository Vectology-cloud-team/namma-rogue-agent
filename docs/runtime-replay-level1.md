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
- ExecutedAction sequence,
- ActionResult sequence,
- deterministic checksum sequence,
- EpisodeOutcome.

Mismatches must be reported. They must not be silently ignored.
