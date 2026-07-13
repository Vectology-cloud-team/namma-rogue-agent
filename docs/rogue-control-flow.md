# Rogue 5.4.4 Control Flow

This document records the Phase 8 read-only control-flow inspection of
Rogueforge Rogue 5.4.4. It covers both:

- `rogue/pristine/rogue5.4.4`
- `rogue/patched/rogue5.4.4`

The patched tree only changes the ncurses compatibility path in
`main.c::tstp()` and adds `compat/compat_ncurses.h`. No Phase 8 Rogue
game code changes are made.

## Inspected Source Scope

The Rogue source tree contains 36 C or header source files:

```text
armor.c
chase.c
command.c
daemon.c
daemons.c
extern.c
extern.h
fight.c
init.c
io.c
list.c
mach_dep.c
main.c
mdport.c
misc.c
monsters.c
move.c
new_level.c
options.c
pack.c
passages.c
potions.c
rings.c
rip.c
rogue.h
rooms.c
save.c
score.h
scrolls.c
state.c
sticks.c
things.c
vers.c
weapons.c
wizard.c
xcrypt.c
```

## Process Lifecycle

The process entry point is `main.c::main(int argc, char **argv, char **envp)`.

Startup order:

1. `md_init()` initializes machine-dependent terminal and signal behavior.
2. Environment and home-directory state are read from `HOME`, `ROGUEOPTS`,
   and machine-dependent helpers.
3. `time(NULL)` and `md_getpid()` are used to initialize `dnum` and `seed`.
   Wizard mode can override this through `SEED`.
4. Score-file access is initialized with `open_score()`.
5. Score inspection and death-debug command-line options may call `exit(0)`.
6. `init_check()` validates startup constraints.
7. If a save file argument is present, `restore(argv[1], envp)` is called.
   Normal restore continues into `playit()` and does not return to `main()`.
8. New-game startup calls `initscr()`, probability and player initialization,
   `setup()`, terminal-size checks, helper window creation, and `new_level()`.
9. Daemons and fuses are started for runners, doctor, wandering monsters, and
   stomach handling.
10. `playit()` enters the main command loop.

Normal new-game loop:

```text
main()
  -> md_init()
  -> initscr()
  -> init_probs()
  -> init_player()
  -> setup()
  -> new_level()
  -> start_daemon() / fuse()
  -> playit()
      -> while (playing) command()
      -> endit(0)
```

## Restore Lifecycle

The restore path is in `save.c::restore(char *file, char **envp)`.

Restore order:

1. Open and validate the save file.
2. Initialize curses with `initscr()`.
3. Re-run terminal setup.
4. Restore global game state through `rs_restore_file()`.
5. Resume terminal mode with `md_tstpresume()`.
6. Redraw, report the restart message, and enter `playit()`.

Restore currently mixes process, terminal, and game state recovery. Phase 9
must not expose this whole path as reset until exit, signal, and terminal
behavior are contained.

## Main Loop

The main gameplay loop is `main.c::playit()`.

`playit()` parses runtime options, initializes room position tracking, and
then repeatedly calls `command()` while `playing` remains true.

```c
while (playing)
    command();
endit(0);
```

For Phase 9, `playit()` is the broad episode loop, but `command()` is the
more useful first boundary for a single external action.

## Turn Lifecycle

The command and turn lifecycle is centered on `command.c::command()`.

High-level order:

1. Before-turn daemons and fuses run when `after` is true.
2. Haste may cause two command-cycle iterations.
3. The map, status, cursor, and screen are refreshed.
4. Input is selected from running state, repeated count state, or `readchar()`.
5. Count prefixes and direction prefixes may read additional characters.
6. A command switch executes the selected command.
7. Commands that do not consume a turn set `after = FALSE`.
8. After-turn daemons, fuses, ring effects, and teleport handling run when
   `after` remains true.

The important Phase 8 conclusion is that one input command is not always one
game turn:

- Count prefixes can make one command consume multiple turns.
- Haste can cause two command cycles.
- Directional item commands may read extra input before executing.
- Inventory, help, option, and some display commands do not consume a turn.
- Some failed game actions still consume a turn.

## Input Boundary

The primary input function is `io.c::readchar()`, which delegates to
`mdport.c::md_readchar()`.

`command()` also consumes implicit input from these global command states:

- `running`
- `to_death`
- `count`
- `countch`
- `runch`
- `last_comm`
- `last_dir`

The Phase 9 minimal boundary should replace the source of command input
without changing command execution logic. The first candidate is to introduce
a host-controlled command source below `readchar()` or just above the call
sites in `command()`, then keep the old curses path for human play.

## Movement Boundary

Semantic movement is implemented by `move.c::do_move(int dy, int dx)`.

`do_move()` handles:

- no-move effects such as bear traps,
- confusion,
- map bounds,
- walls, doors, passages, and floor movement,
- hidden trap discovery,
- monster collision and combat dispatch,
- room entry and exit,
- visible stairs tracking,
- hero position update and redraw.

This function is game logic. Phase 9 should call it through existing command
dispatch rather than rewriting movement semantics.

## Level Change And Win Flow

Descent is in `command.c::d_level()`.

- It requires `hero` to be on `STAIRS`.
- It increments `level`.
- It clears `seenstairs`.
- It calls `new_level()`.

Ascent is in `command.c::u_level()`.

- It requires `hero` to be on `STAIRS`.
- If `amulet` is true and `level` becomes zero, it calls `total_winner()`.
- Otherwise it calls `new_level()`.

The amulet object is created in `new_level.c::new_level()` after
`AMULETLEVEL`. Picking it up sets the global `amulet` flag in `pack.c`.

## Death, Victory, Quit, And Save

Important terminal paths:

| Condition | Function | Current behavior |
| --- | --- | --- |
| Death | `rip.c::death(char monst)` | Tombstone and score path, then `my_exit(0)` |
| Victory | `rip.c::total_winner()` | Winner display and scoring path |
| User quit | `main.c::quit(int sig)` | Interactive confirmation, then score and exit |
| Hangup or signal save | `save.c::auto_save(int sig)` | Save file path, then `exit(0)` |
| Manual save | `save.c::save_game()` and `save.c::save_file()` | Prompt, write state, then `exit(0)` |
| Normal loop end | `main.c::endit(int sig)` | Cleanup and exit |
| Fatal internal path | `main.c::my_exit(int st)` | Terminal reset, then `exit(st)` |

Phase 9 must turn these process exits into host-visible terminal statuses.
The ABI boundary must not allow Rogue internals to call `exit()` across the
runtime host boundary.

## Signal Handling

Signal setup is machine-dependent and enters through `md_init()` and
`mdport.c`. Runtime-sensitive paths include:

- interrupt quit,
- suspend and resume,
- hangup autosave,
- terminal reset,
- shell escape.

The Phase 5 compatibility patch changed only the suspend/resume logical cursor
update in `main.c::tstp()`. Phase 8 does not change that behavior.

## Phase 9 Boundary Recommendation

Phase 9 should introduce the smallest injectable command boundary:

1. Keep Rogue command execution in `command.c::command()`.
2. Add a host-supplied command source that can feed one semantic action as an
   existing Rogue command key or key sequence.
3. Keep curses drawing available for the patched human build.
4. Contain `exit()`, save, death, victory, and signal paths before exposing
   reset and step to Python.
5. Start with `MOVE`, `WAIT`, and `QUIT`.

This is lower risk than rewriting the loop around `do_move()` because it keeps
turn-consuming edge cases inside existing Rogue logic.
