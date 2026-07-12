# Ubuntu 24.04 Build Report

This report records the Phase 5 compatibility build for Rogueforge Rogue
5.4.4. The goal is to build and launch the game on Ubuntu 24.04 without
changing game logic.

## Source

Upstream Golden Baseline:

```text
Rogueforge Rogue 5.4.4 source archive
```

Archive SHA-256:

```text
7d37a61fc098bda0e6fac30799da347294067e8e079e4b40d6c781468e08e8a1
```

Repository layout:

- `rogue/pristine/rogue5.4.4`: unmodified upstream source tree.
- `rogue/patched/rogue5.4.4`: buildable compatibility copy.
- `patches/0001-ncurses-compatibility.patch`: patch from pristine to
  patched source.

The pristine tree must not be edited. Compatibility work is kept in the
patched tree and patch files.

## Environment

Probe host:

```text
mfr7202505
```

Environment observed on 2026-07-13:

| Item | Value |
| --- | --- |
| OS | Ubuntu 24.04.2 LTS |
| Kernel | 6.14.0-33-generic |
| Make | GNU Make 4.3 |
| ncurses | 6.4.20240113 |
| patch | GNU patch 2.7.6 |

Archive integrity on the probe host:

```text
ARCHIVE_SHA256_RESULT=PASS
```

## Build Procedure

The remote probe used the verified upstream archive and applied the
patch series to a temporary build copy:

```sh
sha256sum rogueforge-current-rogue5.4.4-src.tar.gz
tar -xzf rogueforge-current-rogue5.4.4-src.tar.gz
cp -a rogue5.4.4 build-gcc
cd build-gcc
patch -p1 < 0001-ncurses-compatibility.patch
CC=gcc ./configure
make
```

The archive was expanded on Ubuntu so the original executable bits for
`configure`, `config.guess`, `config.sub`, and `install-sh` were
preserved.

## Build Matrix

| Compiler | Version | configure | make | Binary | Launch |
| --- | --- | --- | --- | --- | --- |
| gcc | 13.3.0 | PASS | PASS | PASS | PASS |
| clang | not installed | NOT RUN | NOT RUN | NOT RUN | NOT RUN |

`clang` was not present on `mfr7202505`. Installing it would require
sudo access; the attempted sudo authentication did not succeed, so no
clang package was installed and the clang matrix entry remains pending.

## Warnings

The gcc build completed, with warnings from existing upstream code:

- `fight.c`: possible `sprintf` format overflow in `attack`.
- `mach_dep.c`: ignored `fgets` return value in `lock_sc`.
- `rip.c`: ignored `fgets` return value in `death`.

These warnings were not changed in Phase 5 because the current scope is
only the minimal compatibility layer needed to build and launch the
game. They do not block the gcc binary.

## Launch Probe

The launch probe ran the gcc-built binary under a POSIX PTY using
`tests/test_rogue_launch.py`:

```sh
ROGUE_BINARY=$PWD/rogue python3 /tmp/test_rogue_launch.py -v
```

Result:

```text
test_launch_new_game_and_quit ... ok
Ran 1 test
OK
```

The test verified:

- startup completed,
- a new game began,
- the dungeon display contained the player glyph,
- the status line contained level, gold, hp, strength, armor, and
  experience fields,
- `Q`, `y`, and Return completed the normal quit path.

## Final State

Ubuntu 24.04 with gcc now satisfies:

- `configure`: PASS
- `make`: PASS
- executable generation: PASS
- launch: PASS
- new game: PASS
- dungeon display: PASS
- quit: PASS

The clang build remains pending because clang is not installed on the
probe host.

## Future CI Notes

A future GitHub Actions job can reproduce this by installing the system
packages for gcc, clang, make, patch, and ncurses development headers,
then applying `patches/0001-ncurses-compatibility.patch` to a pristine
source checkout and running:

```sh
CC=gcc ./configure
make
ROGUE_BINARY=$PWD/rogue python3 -m unittest tests.test_rogue_launch
```

For clang, use a separate clean build directory:

```sh
CC=clang ./configure
make
```
