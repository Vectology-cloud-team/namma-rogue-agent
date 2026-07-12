# NaMMA Rogue Autonomous Agent

NaMMA Rogue Autonomous Agent is a project to let a local AI
autonomously play the game Rogue: descend, explore, fight, manage
inventory and food, obtain the amulet, and return to the surface.

The project is currently in the Rogue compatibility phase. This
repository contains the Rogueforge Rogue 5.4.4 pristine baseline and a
minimal Ubuntu 24.04 compatibility copy, but it does not yet contain a
headless environment, local AI integration, NaMMA interface, or OCuLink
driver.

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

The system is divided into four layers:

- Rogue Engine: deterministic game logic, dungeon generation, monsters,
  combat, inventory, items, traps, amulet state, victory, death, and
  random number handling.
- Rogue Environment: headless reset/step API, seed control, action
  validation, observation generation, legal action generation, episode
  management, replay, snapshots, and terminal-state reporting.
- Agent: local AI provider abstraction, planner, deterministic executor,
  action validation, episode memory, failure recovery, and retry policy.
- Viewer: human-readable ASCII display, debug display, replay playback,
  and explanation of what the AI considered.

The viewer must consume environment output rather than reading Rogue internals directly.

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

This branch establishes the first compatibility layer after the Golden
Baseline decision:

- imports the Rogueforge Rogue 5.4.4 pristine upstream tree,
- keeps a separate patched build tree,
- records the ncurses compatibility patch under `patches/`,
- verifies Ubuntu 24.04 gcc configure, make, launch, and quit,
- records clang as pending because it is not installed on the probe
  host,
- leaves all Agent, Observer, Replay, Reset, Step, Headless, NaMMA,
  LLM, Viewer, Python controller, and 64x160 work out of scope.

Game logic changes remain out of scope for this branch.

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
- Modern Ubuntu gcc build: passed with the minimal ncurses
  compatibility patch.
- Modern Ubuntu clang build: pending because clang is not installed on
  `mfr7202505`.
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

- Should the Phase 5 compatibility patch be accepted as the initial
  Ubuntu build profile?
- Which NetHack/NLE environment API ideas, if any, are worth referencing
  while keeping Rogue as the target game?
- What exact NaMMA request/response format should be shared between Ethernet and OCuLink?
- What latency and throughput targets are required for NaMMA inference?
- Which replay data is sufficient to reproduce a full episode?
