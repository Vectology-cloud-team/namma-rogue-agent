# Rogue 5.4.4 Compatibility Layer

This document describes the Phase 5 compatibility layer for building
Rogueforge Rogue 5.4.4 on Ubuntu 24.04.

The purpose is narrow: build and launch the original game on modern
Ubuntu without changing game logic.

## Source Layout

```text
rogue/
|-- pristine/
|   `-- rogue5.4.4/
`-- patched/
    `-- rogue5.4.4/
```

`rogue/pristine/rogue5.4.4` is the unmodified upstream Golden Baseline
from the Rogueforge source archive:

```text
7d37a61fc098bda0e6fac30799da347294067e8e079e4b40d6c781468e08e8a1
```

Do not edit the pristine tree.

`rogue/patched/rogue5.4.4` is the buildable development copy for the
current compatibility layer. The difference between the two trees is
recorded in:

```text
patches/0001-ncurses-compatibility.patch
```

## Patch Summary

Patch:

```text
0001-ncurses-compatibility.patch
```

Reason:

Modern ncurses makes `WINDOW` an opaque type. The upstream source writes
directly to `curscr->_cury` and `curscr->_curx` in `main.c`, which no
longer compiles.

Change:

- Add `compat/compat_ncurses.h`.
- Include the compatibility header from `main.c`.
- Replace direct `curscr` field writes with `wmove(curscr, y, x)`
  through a small helper.

This affects only curses cursor restoration after suspend/resume. It
does not change random number generation, dungeon generation, monsters,
items, combat, save/load, victory conditions, or `new_level.c`.

## ncurses Cursor Compatibility

The old code restores the physical terminal cursor with `mvcur()` and
then directly updates the logical cursor position stored inside
`curscr`:

```c
curscr->_cury = oy;
curscr->_curx = ox;
```

Modern ncurses makes the `WINDOW` internals private, so those fields are
not available to application code. The replacement calls
`wmove(curscr, oy, ox)`, which updates the logical cursor position for
the `curscr` window without immediately writing output to the terminal.
That corresponds to the intent of the original direct field update.

The helper ignores the `wmove()` return value because `oy` and `ox` are
captured immediately beforehand with `getyx(curscr, oy, ox)`, so they
should describe a valid cursor position for the same window during the
same suspend/resume path. If terminal resize handling is added later,
this assumption should be reviewed. Phase 5 does not implement terminal
resize support.

Runtime behavior is checked by the POSIX suspend/resume test in
`tests/test_rogue_launch.py`.

## File-Level Change Record

| File | Reason | Before | After | Logic impact |
| --- | --- | --- | --- | --- |
| `compat/compat_ncurses.h` | ncurses API compatibility | file absent | helper wraps `wmove(curscr, y, x)` | none |
| `main.c` | remove opaque `WINDOW` field access | writes `curscr->_cury` and `curscr->_curx` | calls `namma_compat_move_curscr(oy, ox)` | none |

## Logic Diff Classification

Machine comparison between `pristine` and `patched`:

| Class | Files | Notes |
| --- | ---: | --- |
| Logic | 0 | no game logic file behavior changed |
| UI | 1 | `main.c` cursor restoration compatibility |
| Build | 0 | no configure or Makefile change |
| Compatibility | 2 | `main.c`, `compat/compat_ncurses.h` |
| Documentation | 0 | source-tree documentation unchanged |

Tree comparison:

```text
same=54
changed=1
only_left=0
only_right=1
```

Important unchanged hashes:

| File | Pristine SHA-256 | Patched SHA-256 |
| --- | --- | --- |
| `new_level.c` | `f042cec22f90cbb91ab7142b6d8d42ddf5ca4e5e3e5377deeca6061c8f95f67b` | `f042cec22f90cbb91ab7142b6d8d42ddf5ca4e5e3e5377deeca6061c8f95f67b` |
| `LICENSE.TXT` | `c44793b39e8b9f7d73c41fd0f0257c025988fa80b7d6afebda801b72e6660043` | `c44793b39e8b9f7d73c41fd0f0257c025988fa80b7d6afebda801b72e6660043` |

Tree hashes:

| Tree | File count | SHA-256 |
| --- | ---: | --- |
| pristine | 55 | `ef7dde4703745b011fd3f1cd831998452e92dda484d6079e7005d7a54dfc6f25` |
| patched | 56 | `de6a8883d426008f7909a5dc2be33d0fc883cf8bcbb386b00f1a819bc84a85aa` |

## Prohibited Changes Not Made

Phase 5 did not change:

- random number behavior,
- game loop behavior,
- enemy AI,
- map generation,
- item behavior,
- save/load behavior,
- display text,
- victory conditions,
- `new_level.c`,
- exploration algorithms.

Phase 5 also did not add Agent, Observer, Replay, Reset, Step,
Headless, NaMMA, LLM, Viewer, Python controller, or 64x160 work.

## Validation

Ubuntu 24.04 gcc validation is recorded in `docs/build-ubuntu24.md`.

The launch smoke test is `tests/test_rogue_launch.py`. It is skipped by
default unless `ROGUE_BINARY` points to a built Rogue executable.

Patch reproducibility is checked by
`scripts/verify_compatibility_patch.py`. On systems without the external
`patch` command, the script reports a clear skip. On `mfr7202505`, it
must report:

```text
PATCH_APPLY=PASS
PATCHED_TREE_MATCH=PASS
PRISTINE_TREE_UNCHANGED=PASS
```
