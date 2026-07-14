# Rogue 5.4.4 State Inventory

This document records where authoritative Rogue 5.4.4 state currently lives.
It is based on read-only inspection of the pristine and patched source trees.

`extern.c`, `extern.h`, `rogue.h`, and `state.c` are especially important.
`state.c::rs_save_file()` and `state.c::rs_restore_file()` provide a practical
inventory of state that Rogue already considers persistent.

## State Ownership Summary

| State item | Source file | Symbol or structure | Storage | Owner | Observation suitability | Replay relevance | Risk |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Player position | `rogue.h`, `extern.c` | `player.t_pos`, `hero` macro | global `THING` | Rogue core | Agent observable when visible | High | Medium |
| HP and max HP | `rogue.h` | `player.t_stats.s_hpt`, `s_maxhp` | global `THING` | Rogue core | Agent observable | High | Medium |
| Strength | `rogue.h` | `player.t_stats.s_str` | global `THING` | Rogue core | Agent observable | Medium | Medium |
| Armor class | `rogue.h` | `player.t_stats.s_arm` | global `THING` | Rogue core | Agent observable | Medium | Medium |
| Experience | `rogue.h` | `player.t_stats.s_exp`, `s_lvl` | global `THING` | Rogue core | Agent observable | Medium | Medium |
| Gold | `extern.c` | `purse` | global int | Rogue core | Agent observable | Medium | Low |
| Hunger | `extern.c` | `food_left`, `hungry_state` | global int | Rogue core | Agent observable as status only | High | Medium |
| Status effects | `rogue.h`, `extern.c` | player flags, ring state, daemon state | global | Rogue core | Agent observable after redaction | High | High |
| Dungeon level | `extern.c` | `level`, `max_level` | global int | Rogue core | Agent observable | High | Low |
| Map cells | `extern.c` | `places[MAXLINES*MAXCOLS]` | global array | Rogue core | Redacted visible cells only | High | High |
| Rooms | `extern.c` | `rooms[MAXROOMS]` | global array | Rogue core | Debug or derived visible map | High | High |
| Passages | `extern.c` | `passages[MAXPASS]` | global array | Rogue core | Debug or derived visible map | High | Medium |
| Stairs | `extern.c` | `stairs`, `seenstairs` | global coord and bool | Rogue core | Observable only after seen | High | Medium |
| Monsters | `extern.c` | `mlist`, `THING` list | global list | Rogue core | Visible monsters only | High | High |
| Floor items | `extern.c` | `lvl_obj`, `THING` list | global list | Rogue core | Visible and reachable items only | High | High |
| Inventory | `rogue.h`, `extern.c` | `player.t_pack` | list on player | Rogue core | Agent observable | High | Medium |
| Equipment | `extern.c` | `cur_weapon`, `cur_armor`, `cur_ring[2]` | global pointers | Rogue core | Agent observable | High | High |
| Amulet possession | `extern.c` | `amulet` | global bool | Rogue core | Agent observable after pickup | High | Low |
| Message buffer | `extern.c`, `io.c` | `huh`, `msg()` buffer path | global char buffers | Rogue UI/core | Recent messages observable | Medium | Medium |
| Turn and command counters | `extern.c`, `command.c` | `count`, `no_move`, static locals | global and static | Rogue core | Not directly observable | High | High |
| RNG state | `extern.c`, `extern.h` | `seed`, `dnum`, `RN` macro | global int | Rogue core | Never exposed to agent | Critical | High |
| Terminal condition | multiple | death, winner, quit, save paths | control flow | Rogue core | Runtime terminal status | Critical | High |
| Death reason | `rip.c` | `death(char monst)` argument | stack/control path | Rogue core | Agent may receive terminal reason | High | Medium |
| Victory state | `rip.c`, `command.c` | `total_winner()`, `amulet`, `level` | globals/control path | Rogue core | Terminal status | High | Medium |

## Player And Stats

The player is the global `THING player`. The `hero` macro aliases
`player.t_pos`. Player statistics are held in `struct stats` inside
`player.t_stats`.

Read locations include status rendering, combat, movement, item effects, and
death handling. Write locations include initialization, movement, combat,
potions, rings, hunger, traps, and restore.

Observation priority for Phase 9:

1. `hero`
2. `player.t_stats.s_hpt`
3. `player.t_stats.s_maxhp`
4. `level`
5. recent messages
6. visible cells

## Map, Rooms, And Visibility

The authoritative map is `places[MAXLINES*MAXCOLS]`. Rooms and passages are
stored separately in `rooms[]` and `passages[]`.

The agent-facing observation must not expose:

- hidden traps,
- secret doors before discovery,
- unvisited rooms,
- unseen monsters,
- floor items outside current visibility,
- future random choices.

`PrivilegedDebugState` may include full map and object lists for tests and
diagnostics, but normal DecisionProvider calls must not receive it.

## Inventory And Equipment

Inventory is the player's pack list. Equipment globals point into inventory:

- `cur_weapon`
- `cur_armor`
- `cur_ring[LEFT]`
- `cur_ring[RIGHT]`

Item identity is risky because Rogue includes identification mechanics. Phase
9 should expose inventory names through the same path a player could see, not
through raw object type and flags.

## RNG State

The main game RNG is the global `seed` and the `RN` macro:

```c
#define RN (((seed = seed*11109+13849) >> 16) & 0xffff)
```

`rnd()` and `roll()` in `main.c` are the normal callers. Many gameplay files
call those helpers.

Determinism risks:

- startup currently uses wall-clock time and PID,
- restore calls `srand(md_getpid())`,
- command loops can consume random values in non-obvious places,
- hidden trap and monster behavior can alter RNG consumption.

Phase 9 must set episode seed explicitly before new-game generation and must
record source and build identity in the DeterminismContext.

## Terminal State

Rogue does not currently centralize terminal state. It exits through many
paths:

- death,
- winner,
- quit,
- save,
- autosave,
- normal loop end,
- startup failure,
- signal paths.

Phase 9 should introduce a single host-visible terminal-status path before the
Python backend is connected.

## State Reset Risk

A one-process multi-episode runtime must reset more than player and map state.
Risky state includes:

- global object lists,
- daemon and fuse lists,
- command-repeat state,
- running and chase state,
- message buffers,
- terminal state,
- inventory and equipment pointers,
- score and save-file state,
- signal handler state,
- static locals in command and direction helpers,
- curses global state.

Phase 9 may start with one process, one handle, and one thread, but the ABI
should not permanently encode that as the only possible future.
