# Project Goals

## Final Goal

Build an autonomous agent that can play a Rogue-style dungeon game from start to finish:

1. descend into the dungeon,
2. explore unknown areas,
3. fight enemies,
4. manage food, equipment, and inventory,
5. obtain the amulet,
6. return to the surface,
7. save records and retry automatically after death or failure.

## First Target

The first target is a mini PC-based local AI setup. The mini PC runs the Rogue process, the headless environment, the deterministic executor, and the local inference provider.

The known machine name is `mfr7202505`.

## Final Target

The final target is NaMMA, an FPGA-based local AI on HPFC3. NaMMA should make high-level planning decisions while the mini PC continues to execute game logic and deterministic low-level actions.

## Non-Goals For This Initial Phase

- no large Rogue engine modification,
- no unverified Rogue source import,
- no local model download,
- no llama.cpp installation,
- no NaMMA Ethernet implementation,
- no OCuLink driver implementation,
- no training pipeline,
- no direct push to `main`.

## Success Criteria For This Phase

- repository structure exists,
- architecture is documented,
- action and observation schemas are drafted,
- Rogue source candidates and license risks are recorded,
- local AI and NaMMA interface direction is documented,
- development phases are broken down,
- risks and open questions are visible.
