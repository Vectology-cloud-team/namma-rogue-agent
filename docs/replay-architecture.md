# Replay Architecture

Replay records are evidence for reproducibility, debugging, evaluation,
and comparison. This document defines what replay may store; it does not
implement replay code or a file format.

## Replay Goals

- Reproduce deterministic episodes when possible.
- Compare provider behavior across versions.
- Debug failures without exposing hidden state to normal agents.
- Support game, simulation, and device targets.
- Keep storage levels configurable.

## Replay Data Candidates

| Data | Benefit | Cost | Reproducibility | Typical Size |
| --- | --- | --- | --- | --- |
| Input Sequence | Small and close to control boundary. | Needs exact runtime and seed. | High if deterministic. | Low |
| Observation Sequence | Easy to inspect and compare. | May not reproduce hidden state. | Medium. | Medium |
| State Snapshot | Strong debugging evidence. | May expose hidden or private state. | High for diagnostics. | High |
| Deterministic Seed | Compact reproducibility anchor. | Not enough without actions. | High only with exact runtime. | Very low |
| Episode Metadata | Explains context and versions. | Not executable alone. | Supportive. | Low |

## Recommended Replay Levels

Level 0: Metadata Only

- Episode metadata.
- Seeds.
- Runtime version.
- Terminal result.

Use for high-volume statistics.

Level 1: Deterministic Replay

- Metadata.
- Seeds.
- Input or executed action sequence.
- Configuration hash.
- Source or firmware identity.

Use for deterministic regression runs.

Level 2: Observation Replay

- Level 1.
- Agent observation sequence.
- Action results.
- Provider request and response summaries when permitted.

Use for planner debugging and comparison.

Level 3: Diagnostic Replay

- Level 2.
- Periodic state snapshots.
- Optional `PrivilegedDebugState`.
- Checksum chain.

Use for test failures, engine debugging, and validation tooling only.

## Replay Record Structure

Minimum logical sections:

- episode metadata,
- seed block,
- configuration block,
- runtime version block,
- provider profile block,
- turn records,
- terminal summary,
- checksum summary.

Turn record candidates:

- turn number,
- observation hash,
- optional observation payload,
- requested action,
- validated action,
- executed action,
- action result,
- provider request hash,
- provider response hash,
- timings,
- errors.

## Deterministic Replay

Deterministic replay requires the same:

- Game Core or device simulator version,
- Deterministic Runtime version,
- configuration,
- world seed,
- episode seed,
- action sequence,
- compatibility patches,
- platform assumptions when relevant.

If any dimension is not fixed, replay should be marked as diagnostic
rather than deterministic.

## Replay And Debug State

`PrivilegedDebugState` may be stored in diagnostic replay, but it must
not be included in normal provider requests or agent observations.

Replay readers must label privileged data clearly. A replay viewer may
show privileged state only in debug mode.

## Replay Comparison

Replay comparison should support:

- terminal result comparison,
- turn count comparison,
- observation hash comparison,
- action sequence comparison,
- provider latency comparison,
- score or task metric comparison,
- first divergence turn.

## Storage Policy

The replay writer should allow configurable retention:

- keep all Level 3 failures,
- keep sampled successful episodes,
- keep aggregate metadata for all episodes,
- drop or redact provider prompts if they contain sensitive data,
- compress large observation or snapshot streams when a format is chosen.

## Replay Open Questions

- Replay Binary Format.
- Compression.
- Snapshot interval.
- Whether observations should be canonical JSON.
- Whether provider prompts should be stored verbatim.
- Whether state snapshots should be encrypted or access-controlled.
- How to replay nondeterministic hardware or real robot episodes.
