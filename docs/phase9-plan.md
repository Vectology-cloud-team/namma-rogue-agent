# Phase 9 Native Integration Plan

Phase 9 starts with a native ABI bootstrap stub before any Rogue 5.4.4
game-code patch. The Phase 9A bootstrap proves ctypes-to-C connectivity
without linking the native ABI to Rogue 5.4.4, headless Rogue, or gameplay
control.

## Phase 9A: Native ABI Bootstrap Stub

Expose the smallest native-library stub boundary while preserving game logic:

- ctypes native library loading,
- create and destroy,
- reset,
- observe,
- source identity,
- terminal status,
- `WAIT` and `QUIT` stub actions,
- C ABI connection,
- Python backend connection,
- Replay Level 1 checksum match for a quit episode.

The Phase 9A bootstrap does not implement `MOVE`, `step()`, fixed-seed Rogue
game startup, map observation, inventory, combat, headless Rogue, or any link
from the Native ABI to Rogue 5.4.4 game code.

## Phase 9B Candidate: Native ABI Stub to Rogue 5.4.4 Linkage

After the Phase 9A bootstrap is reviewed and merged, a later Phase 9B may
begin connecting the native ABI boundary to Rogue 5.4.4. Phase 9B is not
implemented by the bootstrap PR.

Minimum entry conditions:

- Phase 9A is merged.
- Pristine and patched source identity are fixed.
- The Native ABI stub is stable.
- Rogue startup path investigation is current.
- `exit`, signal, save, death, and victory paths are investigated.
- Rogue globals reset feasibility is investigated.
- Integration avoids calling `main()` directly.
- In-process and subprocess approaches are compared before implementation.

Future Phase 9B work may expose a minimal deterministic Rogue boundary:

- fixed-seed new-game startup,
- one command injection path,
- `MOVE`, `WAIT`, and `QUIT`,
- minimal observation,
- terminal status,
- Replay Level 1 checksum match against Rogue-backed state.

## Proposed Task Order

The first task is now the safe Phase 9A bootstrap:

| Task | Source files | Functions | Expected patch size | Game-logic risk | Determinism risk | Test | Rollback |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Native ABI stub library | `native/rogue_native_bootstrap.c`, `runtime/rogue/native_backend.py` | create, destroy, reset, observe, source identity, terminal status, WAIT, QUIT | Medium | None | Low | ctypes backend tests | Revert bootstrap commit |

After bootstrap, future work can begin touching Rogue source:

| Task | Source files | Functions | Expected patch size | Game-logic risk | Determinism risk | Test | Rollback |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Separate startup from `main()` | `main.c` | `main`, `playit`, setup calls | Medium | Medium | Medium | Existing launch plus native reset smoke | Revert startup patch |
| Contain process exits | `main.c`, `rip.c`, `save.c` | `my_exit`, `death`, `total_winner`, `quit`, `save_file` | Medium | Medium | High | Death, quit, winner terminal tests | Revert terminal patch |
| Add host input source | `io.c`, `command.c`, maybe `mdport.c` | `readchar`, `command` | Small to medium | Low | Medium | MOVE/WAIT/QUIT command tests | Revert input-source patch |
| Preserve curses viewer | `main.c`, `io.c` | draw paths | Small | Low | Low | Human launch smoke | Revert viewer adapter |
| Fixed-seed reset | `main.c`, `new_level.c`, init files | setup and new level path | Medium | Medium | High | Same seed map checksum | Revert reset patch |
| Minimal action execution | `command.c`, `move.c` | `command`, `do_move` | Small | Low | Medium | MOVE/WAIT/QUIT through ABI | Revert action patch |
| Minimal observation extraction | `extern.c`, `rogue.h`, new adapter files | player, map, messages | Medium | Medium | Medium | Hidden-state tests | Revert observation patch |
| Terminal status extraction | `main.c`, `rip.c`, `save.c` | exit and score paths | Medium | Medium | High | Quit, death, win status tests | Revert terminal patch |
| C ABI implementation | new native adapter files | `namma_rogue_*` | Medium | Low | Medium | C header and Python backend tests | Revert ABI implementation |
| Python native backend | `runtime/rogue` | backend implementation | Medium | Low | Medium | Replay Level 1 match | Revert backend commit |

## First Patch Set Candidate

The first Rogue patch should be smaller than a full headless conversion:

1. Add a host command-source abstraction.
2. Add a host terminal-status abstraction.
3. Add fixed seed startup for a new game.
4. Keep curses drawing intact.
5. Expose a minimal observation snapshot.

`new_level.c` should not be changed in the first native boundary patch unless
the seed-reset work proves it is unavoidable.

## Minimal Observation Priority

Start with:

- dungeon level,
- player position,
- HP,
- max HP,
- visible cells,
- one recent message,
- terminal flag,
- terminal reason.

The Phase 9 ABI reset result should remain small: reset status only, followed
by an explicit observe call and source-identity query. Domain event counts
must not be added without a complete event structure, array, count, lifetime,
and schema contract.

Defer:

- inventory,
- equipment,
- monster details,
- item details,
- full debug snapshots,
- save and restore integration.

## Highest Risks

Largest technical risk:

- converting exit, signal, and terminal-side effects into safe host returns
  without breaking human play.

Largest determinism risk:

- RNG consumption changes when command input, prompts, and terminal paths are
  split.

Phase 9 should add checksum-based tests as early as possible.
