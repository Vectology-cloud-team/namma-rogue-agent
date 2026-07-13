# NaMMA Rogue Autonomous Agent

NaMMA Rogue Autonomous Agent is a project to let a local AI
autonomously play the game Rogue: descend, explore, fight, manage
inventory and food, obtain the amulet, and return to the surface.

The project is currently in the Phase 8 Rogue Domain Adapter Boundary
phase. This repository contains the Rogueforge Rogue 5.4.4 pristine
baseline and a minimal Ubuntu 24.04 compatibility copy, but it does not
yet contain a headless Rogue environment, real Rogue native backend,
local AI integration, NaMMA implementation, or OCuLink driver.

## Target System

The first development target is a mini PC that runs the Rogue process
and the agent controller. The mini PC is reachable on the network as
`mfr7202505`.

The final target is to let NaMMA, an FPGA-based local AI on HPFC3, make
the high-level planning decisions. The Rogue process remains on the mini
PC.

Two NaMMA connection paths are planned:

- Ethernet: initial integration path, likely through an
  OpenAI-compatible API, HTTP, gRPC, or a small custom TCP protocol.
- OCuLink / PCI Express: later integration path using PCIe concepts such
  as BARs, DMA, request/completion rings, doorbells, interrupts,
  polling, and shared buffers.

## Architecture Overview

The Phase 6 runtime design is centered on `Runtime Orchestrator` rather
than a straight serial stack of processing layers.

Top-level responsibility structure:

```text
Runtime Orchestrator
|-- Domain Adapter
|   |-- Domain Core
|   `-- Observation Builder
|-- Episode Memory
|-- Planner
|   `-- Decision Provider
|-- Action Executor
|-- Replay Recorder / Replay Store
`-- Determinism Context
```

`DomainAdapter` is the shared boundary between the runtime and the
controlled domain. Rogue starts as `RogueDomainAdapter`; future domains
may use `RobotDomainAdapter`, `DeviceDomainAdapter`, or
`SimulatorDomainAdapter`.

`DecisionProvider` is the shared decision boundary. Human, rule-based,
LLM, NaMMA, and recorded decisions should appear as
DecisionProvider implementations. NaMMA Ethernet, OCuLink, PCIe, and
future links remain transport adapters below `NammaDecisionProvider`.

Replay starts with Level 1 deterministic replay. Replay Recorder /
Replay Store are event recording components, while
`RecordedDecisionProvider` is a DecisionProvider implementation.

## Repository Layout

```text
.
|-- README.md
|-- AGENTS.md
|-- .gitignore
|-- docs/
|-- rogue/
|-- env/
|-- agent/
|-- viewer/
|-- training/
|-- experiments/
|-- scripts/
|-- tests/
`-- legacy/
```

See `docs/architecture.md` and `docs/development-phases.md` for the initial design.

## Current Development Phase

The previous phase established the first compatibility layer after the
Golden Baseline decision:

- imports the Rogueforge Rogue 5.4.4 pristine upstream tree,
- keeps a separate patched build tree,
- records the ncurses compatibility patch under `patches/`,
- verifies Ubuntu 24.04 gcc configure, make, launch, and quit,
- records clang as pending because it is not installed on the probe
  host.

Phase 7 implemented a Python reference skeleton for the Runtime Contract
defined in Phase 6. It uses only a Fake Domain and fake DecisionProvider
implementations.

At the end of Phase 7, Rogue 5.4.4 was still unmodified and
RogueDomainAdapter had not yet been added. Phase 8 adds the
RogueDomainAdapter skeleton only; Rogue reset, step, real native backend
loading, Local AI, and NaMMA remain unimplemented.

Runtime design documents:

- `docs/runtime-architecture.md`
- `docs/runtime-state-machine.md`
- `docs/provider-interface.md`
- `docs/replay-architecture.md`
- `docs/observation-model.md`
- `docs/action-model.md`
- `docs/runtime-sequence.md`
- `docs/future-extension.md`
- `docs/initial-runtime-profile.md`
- `docs/runtime-contract.md`
- `docs/runtime-replay-level1.md`
- `docs/phase7-implementation.md`

Phase 7 starts with a Rogue-only, single-actor runtime profile. It uses
synchronous DecisionProvider calls, one semantic ExecutedAction per turn,
JSON-compatible logical objects during development, and Level 1
deterministic replay first.

Runtime implementation documents:

- `runtime/README.md`

Phase 8 defines the Rogue native boundary and adds a RogueDomainAdapter
skeleton that is tested only with a Fake Rogue Native Backend.

Phase 8 design and boundary documents:

- `docs/rogue-control-flow.md`
- `docs/rogue-state-inventory.md`
- `docs/rogue-io-boundaries.md`
- `docs/rogue-global-state.md`
- `docs/rogue-observation-boundary.md`
- `docs/rogue-action-mapping.md`
- `docs/rogue-native-abi.md`
- `docs/phase9-plan.md`
- `docs/adr/0001-rogue-native-boundary.md`

Rogue headless control, real native backend loading, Local AI, NaMMA,
HTTP, viewer, training, multi-agent support, streaming, batch execution,
and 64x160 work remain out of scope.

## License Status

The repository license has not yet been selected. Rogueforge Rogue
5.4.4 license evidence is tracked with notice retention, and legacy
local modifications remain unapproved for direct reuse.

Candidate sources are tracked in `docs/rogue-source-selection.md`.
Local asset findings are tracked in `docs/legacy-asset-inventory.md`.
Build probes and license evidence are tracked in
`docs/build-probes.md` and `docs/license-review.md`.
Rogue 5.4.4 Golden Source evaluation is tracked in
`docs/rogue-544-golden-source.md`.

Current Golden Baseline status:

- Upstream Golden Baseline: Rogueforge Rogue 5.4.4, approved and fixed.
- Phase 5 ncurses compatibility patch: accepted initial Ubuntu 24.04
  gcc build profile after PR #5 merge.
- GCC 13.3: PASS.
- Clang: NOT TESTED because it is not installed on `mfr7202505`.
- Clang verification should happen later in CI or a separate
  clang-equipped environment.
- Repository source layout: pristine upstream tree plus separate patched
  compatibility tree.
- Legacy local modifications: preserved as evidence, not directly
  merged.

Build results are tracked in `docs/build-ubuntu24.md`. Patch boundaries
are tracked in `docs/compatibility-layer.md`.

## Markdown Checks

Run the Markdown physical-line check before committing documentation:

```powershell
python scripts/check_markdown.py
python scripts/check_markdown.py --git-ref HEAD
```

If `python` is not on `PATH`, use an installed Python launcher or an
absolute Python executable path.

## Open Questions

- Which NetHack/NLE environment API ideas, if any, are worth referencing
  while keeping Rogue as the target game?
- What exact NaMMA request/response format should be shared between Ethernet and OCuLink?
- What latency and throughput targets are required for NaMMA inference?
- Which replay data is sufficient to reproduce a full episode?
- Should the first Runtime provider format be JSON, Protocol Buffers,
  FlatBuffer, or another schema?
- Which debug state, if any, may be stored in diagnostic replay?
- What exact transport should `NammaDecisionProvider` use first?
- Should multi-agent support be a separate future runtime profile?
