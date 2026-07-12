# Build Probes

This file records build attempts made during source selection. It does
not approve importing any source into this repository.

## Probe: Local Rogue 5.4.4 Tree On Ubuntu

- Date: 2026-07-12
- Source under test: `%USERPROFILE%\Downloads\rogue`
- Probe host: `mfr7202505`
- Operating system: Ubuntu 24.04 family, Linux kernel 6.14.0-33-generic.
- Compiler: GCC 13.3.0.
- Make: GNU Make 4.3.
- Curses availability: `libncursesw.so.6` and `libncurses.so.6` were
  present.
- Source transfer: temporary tar outside the repository.
- Repository source import: none.

Commands attempted on the probe host:

```sh
chmod +x ./configure
./configure --with-ncurses
make
```

Result:

- `configure --with-ncurses`: success.
- `make`: failed.

Failure:

```text
make: *** No rule to make target 'new_level.o', needed by 'rogue'. Stop.
```

Observed warnings before the failure:

- `log_inventory` had implicit declaration and conflicting type warnings.
- `fight.c` emitted an `sprintf` overflow warning.
- `mach_dep.c` ignored a `fgets` return value.

Interpretation:

- The local tree is close to buildable on modern Ubuntu.
- The tree is incomplete or has stale build metadata because build files
  reference `new_level.c`, but that file was not present.
- This is a source-completeness blocker, not a reason to modify the
  repository.

Recommended next action:

- Locate the matching pristine upstream Rogue 5.4.4 / rogueforge
  archive, or recover the missing `new_level.c` from the old local
  project assets.
- Re-run the build probe only after the exact source tree is complete.

## Probe: NetBSD `games/rogue`

- Source: https://github.com/NetBSD/src/tree/trunk/games/rogue
- Build attempted: no.
- Reason: license ambiguity must be reviewed before spending effort on
  portability or import work.

## Probe: Berkeley Rogue 4.22

- Build attempted: no.
- Reason: exact source tree has not been located.
