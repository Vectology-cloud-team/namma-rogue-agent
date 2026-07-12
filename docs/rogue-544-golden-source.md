# Rogue 5.4.4 Golden Source Evaluation

This document records the Phase 4 Rogue 5.4.4 Golden Source
evaluation. Rogue source code is not imported into this repository.

Current Golden Source decision:

```text
Decision: Adoption deferred
```

The best source candidate is now fixed as the Rogueforge Rogue 5.4.4
source archive, but it does not yet satisfy the Golden Source
definition because unmodified `make` fails on Ubuntu 24.04.

## Candidate

Golden Source candidate:

```text
Rogueforge Rogue 5.4.4 source archive
```

Primary URL:

```text
http://rogue.rogueforge.net/files/rogue5.4/rogue5.4.4-src.tar.gz
```

Archive SHA-256:

```text
7d37a61fc098bda0e6fac30799da347294067e8e079e4b40d6c781468e08e8a1
```

Archive size:

```text
209839 bytes
```

Working directory used outside Git:

```text
%USERPROFILE%\Documents\Codex\rogue-golden-source\
```

## Source Retrieval Matrix

| Source | Result | Size | Evidence |
| --- | --- | ---: | --- |
| Rogueforge current | PASS | 209839 | source archive |
| Wayback archive | PASS | 209839 | matching archive |
| GitHub mirror archive | PASS | 213905 | source files match |
| GitHub mirror clone | PASS | n/a | tag `v5.4.4` |
| GitLab mirror clone | BLOCKED | n/a | clone timed out |
| GitLab archive | BLOCKED | 5461 | sign-in HTML |
| GitLab API archive | BLOCKED | 35 | 404 payload |

Rogueforge current:

- URL:
  `http://rogue.rogueforge.net/files/rogue5.4/rogue5.4.4-src.tar.gz`
- SHA-256:
  `7d37a61fc098bda0e6fac30799da347294067e8e079e4b40d6c781468e08e8a1`

Wayback archive:

- URL:
  `https://web.archive.org/web/20120510094226id_/http://rogue.rogueforge.net/files/rogue5.4/rogue5.4.4-src.tar.gz`
- SHA-256:
  `7d37a61fc098bda0e6fac30799da347294067e8e079e4b40d6c781468e08e8a1`

GitHub mirror archive:

- URL:
  `https://github.com/phs/rogue/archive/refs/tags/v5.4.4.tar.gz`
- SHA-256:
  `aea2204f046576e06ba1bc53808cc193306e4a694a92a573e739289117f91a41`

GitHub mirror clone:

- URL: `https://github.com/phs/rogue`
- Tag: `v5.4.4`
- Commit: `c7c119f893bd2f8255f2ad78d58a32664ddb9a97`

GitLab mirror attempts:

- Clone URL: `https://gitlab.com/psmith/rogue.git`
- Archive URL:
  `https://gitlab.com/psmith/rogue/-/archive/v5.4.4/rogue-v5.4.4.tar.gz`
- API archive: GitLab project archive API for `psmith/rogue`.

The Rogueforge current archive and the Wayback archive have identical
SHA-256 values. The GitHub mirror archive has wrapper metadata from
GitHub, but its 55 Rogue source files match the Rogueforge source
archive exactly.

## Completeness

The Rogueforge archive extracts to:

```text
rogue5.4.4/
```

Completeness result:

- Total files: 55.
- Files expected from `Makefile.in`: 55.
- Missing files from `Makefile.in`: 0.
- Extra files outside `Makefile.in`: 0.
- Required `LICENSE.TXT`: present.
- Required `Makefile.in`: present.
- Required `configure`: present.
- Required `new_level.c`: present.

Important file hashes:

| File | Size | SHA-256 |
| --- | ---: | --- |
| `LICENSE.TXT` | 4932 | `c44793b39e8b9f7d73c41fd0f0257c025988fa80b7d6afebda801b72e6660043` |
| `Makefile.in` | 6929 | `928890744cfa37f01a7a045a4d1036c6e2f403cd49770eb701ea4bafab290ca8` |
| `configure` | 207030 | `da12702114e6a90dbc340a31fcc9ca671e4e44273d6defe454c6c3f9f9cd82dc` |
| `new_level.c` | 5131 | `f042cec22f90cbb91ab7142b6d8d42ddf5ca4e5e3e5377deeca6061c8f95f67b` |

The tree manifest SHA-256 produced by `scripts/hash_tree.py` is:

```text
ef7dde4703745b011fd3f1cd831998452e92dda484d6079e7005d7a54dfc6f25
```

This tree hash is a project-local manifest hash, not an upstream
release checksum.

## Version Evidence

Source evidence:

- Game or package version: `release = "5.4.4"` in `vers.c`.
- Runtime version string in source:
  `version[] = "rogue (rogueforge) 09/05/07"` in `vers.c`.
- SCCS revision: `@(#)main.c 4.22 (Berkeley) 02/05/99`.
- SCCS revision: `@(#)new_level.c 4.38 (Berkeley) 02/05/99`.

Interpretation:

- `5.4.4` is the Rogue release under evaluation.
- `rogueforge 09/05/07` is the runtime version string embedded in the
  source.
- `main.c 4.22` is a file revision tag, not verified as a standalone
  game release.
- Runtime output could not be verified because the unmodified build did
  not produce a binary.

## Ubuntu Build Probe

Probe host:

```text
mfr7202505
```

Environment:

- OS: Ubuntu 24.04 family, Linux kernel 6.14.0-33-generic.
- Compiler: GCC 13.3.0.
- Make: GNU Make 4.3.
- `libncurses-dev`: installed.
- `libncursesw.so.6` and `libncurses.so.6`: present.
- `autoconf`: not installed, but not required because the archive
  already contains `configure`.

Commands:

```sh
./configure
make
```

Result:

- `./configure`: PASS.
- `make`: FAIL.

Build failure:

```text
main.c:241:11: error: invalid use of incomplete typedef 'WINDOW'
main.c:242:11: error: invalid use of incomplete typedef 'WINDOW'
make: *** [Makefile:130: main.o] Error 1
```

Classification:

- This is not a missing dependency failure.
- This is a modern ncurses compatibility failure.
- No source file was modified.
- No game logic change was attempted.

## Launch Probe

Launch status:

```text
NOT TESTED
```

Reason:

- The unmodified build did not produce a `rogue` binary.
- New-game start, dungeon display, and quit behavior could not be
  verified from the source build.

## Local Tree Comparison

Compared against:

```text
%USERPROFILE%\Downloads\rogue
```

The local tree was copied to the external work directory before
comparison. The original local tree was not changed.

Summary:

- Same files: 49.
- Changed files: 5.
- Present only in Rogueforge Golden candidate: 1.
- Present only in local tree: 6.

### Changed Files

| File | Golden SHA-256 | Local SHA-256 | Classification |
| --- | --- | --- | --- |
| `command.c` | `398c1fc84575791ab1fbe3112c3e23c33bb1d70c68e381f6cbe406e15aa4b361` | `493d6cd9431ce5c4b2d49e4683ba8dbacf2ffa6024df47237b10d5130ef3a73a` | A: local logging calls |
| `io.c` | `01d24e08a31975d3cedc19dbd3323319f3e39cb93aadebb852b58834d822c916` | `c51d988471f49b0256559a05c37225b490b8138d691dadba01b5cab4f483367d` | A: local logging implementation |
| `main.c` | `8e3af15fc72ec1d86026efc9117a31f3bd51ceb704ca74d2e6f4962d7f0a2a1a` | `4ec6d86d65f09bdebc391fb2d65583aa25aeb04e1fbc381de506a3cc72a378ea` | A: startup log and seed clues |
| `rip.c` | `f385286c82698a1281c912bc6c1565cbca165e965eeecc4d21d71fcd78210d79` | `e2e405dbe42d877fb49fd9f5a17dd6fbb0ef1c5ebf187e7f5bc39e606faaa239` | A: death logging |
| `rogue.h` | `bad47c721a3fbd1029c6370ef3829521097c998609a30c4f413cd396192ebd77` | `3019efc3a30ae601a5c2167012763d83b25a08d637c453d93cc7c40e96dfde0f` | A: local declarations |

### Present Only In Golden Candidate

| File | Golden SHA-256 | Classification |
| --- | --- | --- |
| `new_level.c` | `f042cec22f90cbb91ab7142b6d8d42ddf5ca4e5e3e5377deeca6061c8f95f67b` | D: missing from local tree |

### Present Only In Local Tree

| File | Local SHA-256 | Classification |
| --- | --- | --- |
| `draw_rogue_log.py` | `238cfc97cdb85990dae4f2d773c67dd46ff0cc9e3d36c2ca6d07442e9679394d` | D: provenance unknown |
| `io.BAK` | `240bbf1879660eb76c55102844e62fec7cee1f6302c86f2c281216574d79e2eb` | C: backup or temporary |
| `io.c.orig` | `01d24e08a31975d3cedc19dbd3323319f3e39cb93aadebb852b58834d822c916` | C: original copy |
| `rogue.BAK` | `4607d8e2d839ac9bf3f93e600655ac5a75e61f2152a6bf26e6246b53aad6e1a0` | C: backup or build artifact |
| `rogue.h.org` | `bad47c721a3fbd1029c6370ef3829521097c998609a30c4f413cd396192ebd77` | C: original copy |
| `rogue_controller.py` | `bbf51166044b03db675eefaf5092e2399343de5db191ae23789f8c8abbaf5dca` | D: provenance unknown |

B: build compatibility changes were not found in the local tree diff.

## License Evaluation

| Component | Evidence | Status |
| --- | --- | --- |
| Original Rogue-derived files | Source headers point to `LICENSE.TXT`; `LICENSE.TXT` present | PASS |
| Nicholas J. Kisseberth files | `state.c`, `mdport.c`, and `LICENSE.TXT` contain matching origin evidence | PASS |
| David Burren `xcrypt.c` | `xcrypt.c` and `LICENSE.TXT` contain matching origin evidence | PASS |
| Autoconf helper files | Helper files are present and generated-tool notices remain to be reviewed | BLOCKED |
| Local modifications | Local logging/controller changes are outside pristine Rogueforge archive | UNVERIFIED |

License conclusion:

```text
Pristine archive license evidence: PASS
Repository inclusion: BLOCKED until generated-file notices and project policy are reviewed
Local modification reuse: UNVERIFIED
```

## Golden Source Gate

| Gate | Status | Notes |
| --- | --- | --- |
| Rogue 5.4.4 pristine source acquired | PASS | Rogueforge current archive acquired |
| SHA-256 fixed | PASS | Archive SHA recorded |
| Complete source | PASS | 55 expected files, 0 missing |
| `new_level.c` present | PASS | Present and hashed |
| License evidence | PASS | Main source evidence present |
| Ubuntu `./configure` | PASS | Succeeded on `mfr7202505` |
| Ubuntu unmodified `make` | FAIL | Modern ncurses `WINDOW` blocker |
| Unmodified launch | NOT TESTED | No binary produced |
| Local diff acquired | PASS | Diff and SHA table recorded |
| Local modification tracking | BLOCKED | Local authorship and reuse rights unknown |

## Decision

Final Phase 4 decision:

```text
Adoption deferred
```

The Rogueforge Rogue 5.4.4 source archive is the correct source to keep
as the leading Golden Source candidate because it is directly available
from Rogueforge, matches the Wayback archive byte-for-byte, and matches
the GitHub mirror source files.

It should not be formally adopted yet because the Golden Source
definition requires a buildable source, and unmodified `make` currently
fails on Ubuntu 24.04.

Required Shinoda decisions:

- Decide whether a minimal ncurses compatibility patch is acceptable as
  a documented build patch before importing Rogue source.
- Decide whether generated Autoconf helper notices require legal review
  before repository inclusion.
- Decide whether local logging, controller, seed, and 64x160 assets may
  be reused after provenance review.
- Decide whether `new_level.c` should be recovered from the Rogueforge
  archive only after the source import phase begins.
