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

## Next Phase Conditions

Before Phase 8 starts, the following decisions are needed:

- whether the Runtime Contract is accepted,
- which parts of the Python reference become permanent contracts,
- how RogueDomainAdapter should bridge C Rogue and Python Runtime,
- which replay fields must remain stable,
- which DecisionProvider transport should be attempted first.
