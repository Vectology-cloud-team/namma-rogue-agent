# Rogue 5.4.4 I/O Boundaries

This document identifies I/O paths that must be separated from the future
Runtime API. It is read-only Phase 8 analysis.

## Input Path

Primary keyboard path:

```text
command.c::command()
  -> io.c::readchar()
      -> mdport.c::md_readchar()
          -> curses getch()
```

Additional prompt-style input occurs through:

- `misc.c::get_dir()`
- item selection helpers,
- save-file prompts,
- quit confirmation,
- option editing,
- shell escape prompts,
- death and winner screens.

The Phase 9 minimum should inject a command source without changing command
semantics. The safest initial target is the `readchar()` boundary, with
strictly bounded command sequences for `MOVE`, `WAIT`, and `QUIT`.

## Drawing Path

Rogue uses curses directly across many files. Common calls include:

- `move`
- `addch`
- `mvaddch`
- `addstr`
- `printw`
- `clear`
- `clrtoeol`
- `refresh`
- `wrefresh`
- `newwin`
- `endwin`

The Phase 5 compatibility patch preserves curses and only adapts the
`curscr` logical cursor update in `main.c::tstp()`.

Phase 8 does not remove curses. Phase 9 should keep the human curses view
working while adding a host-controlled action path.

## Message Path

Messages are produced through `io.c::msg()`, `io.c::addmsg()`, and
`io.c::endmsg()`. The visible message buffer and last-message behavior are
agent-observable only after redaction through `RogueAgentObservation`.

The raw message implementation is UI-coupled and should not become the only
structured observation source.

## File I/O

Important file paths:

| Area | Source | Notes |
| --- | --- | --- |
| Save file | `save.c` | Save and restore mix file I/O, terminal state, and process exit |
| Score file | `mach_dep.c`, `rip.c` | Score writes are part of death, quit, and win flows |
| Startup paths | `main.c`, `mdport.c` | Home directory and option discovery |
| Crypt helpers | `xcrypt.c` | Used by save-state handling |

Phase 9 should avoid save and restore in the first reset/step spike unless
terminal paths are already contained.

## Process And Terminal Effects

Runtime-hostile effects:

- `exit()` and `my_exit()`
- signal handlers,
- terminal mode changes,
- shell escape,
- suspend and resume,
- save-on-signal,
- prompts that block on stdin.

These must not cross the Native ABI boundary. The C side should return a
status code and terminal status instead of terminating the host process.

## Recommended Minimum Split

Minimum input split for Phase 9:

1. Keep the existing curses draw path.
2. Introduce an input provider used by `readchar()` or the call sites in
   `command()`.
3. Allow a bounded command sequence per external semantic action.
4. Return control to the host after one command-cycle candidate.
5. Report whether the domain consumed a game turn, failed in-domain, or
   reached a terminal condition.

The first semantic actions should be:

- `MOVE`
- `WAIT`
- `QUIT`

Raw Rogue key codes may be used inside the adapter implementation, but they
must not be the primary public Runtime contract.
