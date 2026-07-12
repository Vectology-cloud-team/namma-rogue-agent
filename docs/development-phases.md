# Development Phases

## Phase 0: Preserve Existing Assets

- collect old Rogue code,
- collect Python controller code,
- collect logs,
- collect notes,
- collect build steps,
- record everything in `docs/legacy-asset-inventory.md`.

## Phase 1: Select Rogue Source

- compare candidate Rogue implementations,
- verify licenses,
- verify build environment,
- evaluate modification difficulty,
- evaluate headless suitability,
- evaluate seed reproducibility,
- make recommendation.

## Phase 2: Determinism

- seed control,
- remove or isolate time dependencies,
- define replay base format,
- add deterministic tests.

## Phase 3: Headless Environment

- `reset`,
- `step`,
- observation schema,
- action schema,
- terminal state,
- legal actions.

## Phase 4: Rule-Based Bot

- exploration,
- combat,
- food handling,
- traps,
- unattended 1000-episode test.

## Phase 5: Local AI Planner

- local provider abstraction,
- `llama.cpp` provider,
- structured planner input,
- structured planner output,
- deterministic executor.

## Phase 6: Logging And Reflection

- per-episode records,
- death-cause analysis,
- success and failure datasets,
- replay inspection tools.

## Phase 7: Amulet Acquisition

- acquisition strategy,
- deepest-level tracking,
- survival policy.

## Phase 8: Return To Surface

- return strategy,
- known-map reuse,
- success-rate tracking.

## Phase 9: NaMMA Ethernet

- inference API,
- latency measurement,
- timeout behavior,
- error handling.

## Phase 10: NaMMA OCuLink

- PCI Express transport design,
- DMA design,
- driver work,
- performance measurement.
