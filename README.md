# NaMMA Rogue Autonomous Agent

NaMMA Rogue Autonomous Agent is a project to let a local AI
autonomously play the game Rogue: descend, explore, fight, manage
inventory and food, obtain the amulet, and return to the surface.

The project is currently in the design and development-preparation
phase. This repository does not yet contain a playable Rogue engine, a
local AI integration, a NaMMA interface, or an OCuLink driver.

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

This branch prepares the repository before implementation:

- documents project goals,
- records architecture decisions,
- defines observation and action schemas,
- compares Rogue implementation candidates and license risks,
- sketches local AI and NaMMA provider interfaces,
- breaks development into phases,
- records risks and open questions,
- records the current legacy asset inventory.

Implementation should begin only after this design is reviewed.

## License Status

The repository license and the Rogue implementation license have not yet
been selected. Do not import third-party Rogue source code until its
license and redistribution conditions are confirmed.

Candidate sources are tracked in `docs/rogue-source-selection.md`.
Local asset findings are tracked in `docs/legacy-asset-inventory.md`.
Build probes and license evidence are tracked in
`docs/build-probes.md` and `docs/license-review.md`.

## Open Questions

- Which Rogue implementation should be used as the base?
- Which NetHack/NLE environment API ideas, if any, are worth referencing
  while keeping Rogue as the target game?
- What exact NaMMA request/response format should be shared between Ethernet and OCuLink?
- What latency and throughput targets are required for NaMMA inference?
- Which replay data is sufficient to reproduce a full episode?
