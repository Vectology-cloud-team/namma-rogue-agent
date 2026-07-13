# Replay Architecture

Replay records are evidence for reproducibility, debugging, evaluation,
and comparison. This document is design only. It does not implement
replay code or choose a file format.

## Three Replay Responsibilities

Replay must be separated into three responsibilities.

### Replay Recorder / Replay Store

Responsibilities:

- record episode events,
- read stored episode events,
- maintain replay indexes,
- maintain checksums,
- expose replay evidence to tools.

Replay Recorder and Replay Store are not DecisionProviders.

### RecordedDecisionProvider

Responsibilities:

- return saved decision results,
- behave as one DecisionProvider implementation,
- support comparison against live Human, RuleBased, LLM, or NaMMA
  decisions.

`RecordedDecisionProvider` does not replay the domain by itself.

### Runtime Replay Mode

Responsibilities:

- re-run a domain using seed and ExecutedAction sequence,
- compare checksums,
- compare ActionResult values,
- compare terminal outcome,
- report the first divergence.

Runtime Replay Mode is not a DecisionProvider.

Replay storage and Runtime Replay Mode should not be described as
providers.

## Replay Levels

Level 0: Metadata Only

- episode metadata,
- runtime version,
- terminal outcome,
- turn count.

Level 1: Deterministic Replay

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

Level 1 is the only required replay level for Phase 7.

Level 2: Observation Replay

- Level 1 data,
- full AgentObservation payloads,
- provider prompt summaries,
- provider response summaries.

Level 2 is future work.

Level 3: Diagnostic Replay

- Level 2 data,
- PrivilegedDebugState,
- full snapshots,
- compression,
- binary format.

Level 3 is future work and may require access controls.

## Replay Data Candidate Comparison

| Data | Benefit | Cost | Reproducibility |
| --- | --- | --- | --- |
| ExecutedAction sequence | Small control boundary. | Needs exact runtime identity. | High with seeds. |
| AgentObservation sequence | Easy to inspect. | Larger and not hidden-state complete. | Medium. |
| PrivilegedDebugState | Strong diagnostic evidence. | Must not reach normal providers. | High for debugging. |
| Deterministic seeds | Very compact. | Not enough without actions. | High only with actions. |
| Episode metadata | Explains context. | Not executable alone. | Supportive. |

## Replay Record Structure

Minimum Level 1 sections:

- episode metadata,
- source and build identity,
- compatibility patch identity,
- configuration hash,
- seed block,
- turn records,
- terminal summary,
- checksum summary.

Turn record fields:

- turn number,
- ExecutedAction,
- ActionResult,
- deterministic checksum when available,
- timing summary.

## Replay And Debug State

`PrivilegedDebugState` may be stored only in diagnostic replay or tests.
It must not be included in normal DecisionProvider requests.

Replay readers must label privileged data clearly.

## Replay Open Questions

- Replay Binary Format.
- Compression.
- Snapshot interval.
- Whether observations should be canonical JSON.
- Whether provider prompts should be stored verbatim.
- How to replay nondeterministic hardware or real robot episodes.
