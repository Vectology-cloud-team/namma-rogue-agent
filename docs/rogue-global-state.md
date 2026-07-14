# Rogue 5.4.4 Global State And Reentrancy

Rogue 5.4.4 is not currently reentrant. Its authoritative game state is mostly
global and is restored through explicit save-state readers.

## Global State Categories

Important global categories:

- player and stats,
- level, rooms, passages, and map cells,
- monsters and floor-object lists,
- inventory and equipment pointers,
- message buffers,
- command-repeat and running state,
- daemon and fuse state,
- hunger and status-effect state,
- score and save-file state,
- RNG seed and startup identity,
- curses state,
- signal handler state.

`state.c::rs_save_file()` is the best existing map of this state.

## File-Static And Static Local State

Notable static or file-level state found during Phase 8 inspection:

| Source | State | Risk |
| --- | --- | --- |
| `command.c` | `static char countch`, `direction`, `newcount` | repeat and direction state can survive reset |
| `misc.c` | `static coord last_delt` in `get_dir()` | direction default can survive reset |
| `rip.c` | `static time_t date` | terminal display state |
| `mdport.c` | terminal mode and shell helpers | process and terminal coupling |
| `rooms.c` | room placement helper state | generation reset risk |
| `daemon.c` | daemon list | delayed effects and timers |
| `daemons.c` | hunger and timing helpers | turn progression |
| `move.c` | movement helper coord `nh` | current move candidate |

This is not a complete C parser result. It is a human-reviewed inventory of
reset risks.

## External Dependencies

The current game depends on:

- wall-clock time,
- process ID,
- environment variables,
- terminal size,
- curses global state,
- signal process state,
- file-system paths for save and score.

The future Native Backend must report this identity to the Runtime and avoid
using uncontrolled time or PID for deterministic episodes.

## Reset Requirements

A correct in-process reset will need to reinitialize:

- `player`,
- `places`,
- `rooms`,
- `passages`,
- `mlist`,
- `lvl_obj`,
- `cur_weapon`, `cur_armor`, and rings,
- command-repeat state,
- running and chase state,
- daemon and fuse lists,
- hunger state,
- message buffers,
- `level`, `max_level`, `stairs`, and `seenstairs`,
- `amulet`,
- RNG `seed` and `dnum`,
- terminal status,
- any static locals that preserve command context.

The first implementation can be one process, one handle, and one thread. That
is an implementation profile, not a permanent ABI promise.

## Reentrancy Position

Phase 8 recommends:

- ABI design should permit multiple handles in the future.
- Phase 9 may document and enforce one handle per process if necessary.
- Global Rogue internals must not be exposed as writable ABI symbols.
- Any non-reentrant limitation must be reported through backend capabilities.

The Runtime should treat reentrancy as a backend capability, not as a property
of all domains.
