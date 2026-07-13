# Phase 7 Implementation

Phase 7 implements the Runtime Contract Skeleton.

## Runtime Profile

Phase 7 uses:

- Rogue-only target profile,
- Fake Domain only,
- single actor,
- single episode,
- synchronous execution,
- one semantic ExecutedAction per turn,
- Python reference implementation,
- standard library only.

The Phase 7 `RuntimeOrchestrator` is one-shot. Reusing one instance for a
second episode is rejected with `InvalidStateTransition`; a later
multi-episode runner can own repeated setup explicitly.

Validation rejection policy:

- `REJECTED_SCHEMA` faults the Runtime as a DecisionProvider contract
  violation.
- `REJECTED_OBSERVABLE_RULE` also faults the Runtime in the initial profile.
- Neither rejection creates an ExecutedAction or Replay Level 1 turn event.
- `ATTEMPT_FAILED_IN_DOMAIN` means validation succeeded, the Domain attempted
  the action, and the result is recorded as an executed turn.

## Fake Domain Purpose

The Fake Domain verifies Runtime Contract behavior without touching Rogue
5.4.4.

The Fake Domain is deterministic and small:

- start at position 0,
- `GO_RIGHT` increments position,
- `GO_LEFT` decrements position,
- `WAIT` keeps position,
- position 3 is success,
- position -2 is domain loss,
- max turn count is time limit.

The Fake Domain includes `BUMP` as an accepted action that fails inside the
Domain. It exists to test the difference between validation rejection and a
real executed action with an in-domain failure result.

## Text Formatting Checks

Phase 7 now includes `scripts/check_text_files.py` because GitHub review found
that non-Markdown source can also become unreadable when multiple Python
statements are collapsed onto one physical line.

Run both worktree and Git blob checks:

```powershell
python scripts/check_text_files.py
python scripts/check_text_files.py --git-ref HEAD
```

The check covers tracked Python, Markdown, text, JSON, YAML, TOML, INI, shell,
and PowerShell files. It detects long physical lines, concatenated Python
imports, concatenated Python class or function definitions, suspiciously tiny
Python physical-line counts, CRLF, Unicode bidi controls, and Unicode format
characters.

## Next Phase Conditions

Before Phase 8 starts, the following decisions are needed:

- whether the Runtime Contract is accepted,
- which parts of the Python reference become permanent contracts,
- how RogueDomainAdapter should bridge C Rogue and Python Runtime,
- which replay fields must remain stable,
- which DecisionProvider transport should be attempted first.
