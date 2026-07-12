# Rogue 5.4.4 Baseline Investigation

This document records the Rogue 5.4.4 baseline investigation performed
after PR #2. It does not select a final Rogue implementation and does
not approve importing Rogue source into this repository.

Phase 4 follow-up is recorded in `docs/rogue-544-golden-source.md`.
That pass recovered the direct Rogueforge `rogue5.4.4-src.tar.gz`
archive and supersedes the mirror-only baseline source evidence.

Current controlling status:

```text
Upstream Golden Baseline: Rogueforge Rogue 5.4.4, APPROVED AND FIXED
Modern Ubuntu Build Profile: BLOCKED pending minimal ncurses compatibility patch
Repository Source Import: PENDING compatibility-patch and license-notice verification
Legacy Local Modification Reuse: DEFERRED / UNVERIFIED
```

Current baseline investigation target:

```text
Local Rogue 5.4.4 / rogueforge 09/05/07
```

Current adoption status:

```text
Upstream Golden Baseline: Rogueforge Rogue 5.4.4, APPROVED AND FIXED
Modern Ubuntu Build Profile: BLOCKED pending minimal ncurses compatibility patch
Repository Source Import: PENDING compatibility-patch and license-notice verification
Legacy Local Modification Reuse: DEFERRED / UNVERIFIED
```

## Work Area

The investigation work area was outside this repository:

```text
%USERPROFILE%\Documents\Codex\rogue-544-investigation\
```

The original local tree `%USERPROFILE%\Downloads\rogue` was copied to
`extracted\local-existing\rogue` before comparison. The original local
tree was not changed.

## Retrieved Sources

### Rogueforge Original Candidate

- Source used for baseline comparison: `phs/rogue`.
- Tag: `v5.4.4`.
- Upstream claim: Rogue 5.4.4 from `http://rogue.rogueforge.net/`.
- Source type: archived GitHub mirror of a Rogueforge source tree.
- Local archive name: `phs-rogue-v5.4.4-git-archive.tar`.
- Archive SHA-256:
  `096a1648deb14e67d1c246519ec95341dc45317013b9bf0662d7bbd07577b2ba`.
- Extracted path:
  `extracted\rogueforge-original\rogue-v5.4.4-phs-tag`.
- License file: `LICENSE.TXT` present.
- Extraction result: complete Git archive extraction.

This was the mirror baseline candidate for that investigation pass. It
is superseded by the direct Rogueforge archive recovered in Phase 4.

### Maintenance Fork Reference

- Source used as reference only: `kngwyu/rogue5.4.4`.
- Commit: `6282f8b5c6f4c1103d788eb8adb1298e23d2cd1e`.
- Local archive name: `kngwyu-rogue5.4.4-head-git-archive.tar`.
- Archive SHA-256:
  `0f5b06acc66d68735f1aa63068ebf3abb2a520880ad47702eb0b1108fbd59366`.
- License file: `LICENSE.TXT` present.
- Use: reference only, not pristine baseline.

The fork states that it mirrors Rogue 5.4.4 and includes local build
changes. Those changes make it useful for comparison, but prevent it
from being treated as the pristine baseline.

### Direct Rogueforge Archive Search

Direct attempts to retrieve likely Rogueforge archive URLs did not
produce a usable original archive in this environment.

- HTTPS requests failed during TLS negotiation.
- HTTP requests returned small 404 HTML responses.
- No direct Rogueforge tarball was accepted as source evidence.

## Version Evidence

The baseline tree contains:

- Package release string: `release = "5.4.4"` in `vers.c`.
- Runtime version string: `rogue (rogueforge) 09/05/07` in `vers.c`.
- File SCCS tag: `@(#)main.c 4.22 (Berkeley) 02/05/99`.
- File SCCS tag: `@(#)new_level.c 4.38 (Berkeley) 02/05/99`.

Current interpretation:

- `5.4.4` is the Rogue package or game release under investigation.
- `rogueforge 09/05/07` is the release string in this source tree.
- `main.c 4.22` is a file-level SCCS revision tag.
- A standalone game distribution named `Rogue v4.22` has not been
  verified.

## Completeness

The `phs/rogue` `v5.4.4` archive inventory produced:

- File count: 57.
- Files expected by `Makefile.in`: 55.
- Missing files expected by `Makefile.in`: 0.
- Extra files outside `Makefile.in`: `.gitignore`, `README.md`.
- `new_level.c`: present.
- `LICENSE.TXT`: present.

The copied local tree inventory produced:

- File count: 62.
- Missing files expected by `Makefile.in`: 1.
- Missing file: `new_level.c`.
- Extra files include controller scripts and backup/original files.

## new_level.c

The baseline `new_level.c` is present.

- SHA-256:
  `55b9331a6078fadc9acca4298026802b8fc488465cad334fdef969955d2f2232`.
- SCCS tag: `@(#)new_level.c 4.38 (Berkeley) 02/05/99`.
- Role: creates and draws a new dungeon level.
- Build references: `Makefile.in`, `Makefile.std`, and `rogue54.vcproj`.
- Callers: `main.c`, `command.c`, and `move.c`.

This file is missing from `%USERPROFILE%\Downloads\rogue`, which
explains the previous local build failure at `new_level.o`.

## Amulet And Return Rules

The baseline contains the Rogue amulet and return-to-surface rules:

- `AMULETLEVEL` is defined as level 26 in `rogue.h`.
- `AMULET` is defined as the amulet object symbol in `rogue.h`.
- `new_level.c` places the amulet when the level reaches
  `AMULETLEVEL` and the player does not already have it.
- `pack.c` sets the `amulet` flag when the amulet is picked up.
- `command.c` calls `total_winner()` when the player returns above the
  dungeon while carrying the amulet.
- `rip.c` implements `total_winner()`.

## Build Probe

Build probes were run on `mfr7202505` in temporary directories outside
the repository.

Probe environment:

- OS: Ubuntu 24.04 family, Linux kernel 6.14.0-33-generic.
- Compiler: GCC 13.3.0.
- Make: GNU Make 4.3.
- Autoconf: not installed.
- Curses libraries: `libncursesw.so.6` and `libncurses.so.6` present.

Baseline build result:

- Pristine `sh ./configure`: failed because generated scripts contain
  CRLF line endings.
- Build-copy generated-script LF normalization: `configure` succeeded.
- `make`: failed in `main.c` with incomplete `WINDOW` typedef access.
- Build environment option `-DNCURSES_INTERNALS`: did not complete the
  build; later errors appeared in `mdport.c`.
- Runtime check: not tested because no binary was produced.

Classification:

- CRLF failure: generated-script portability issue in the source tree.
- `WINDOW` failure: modern ncurses compatibility blocker.
- No source compatibility patch was made.
- No game logic change was attempted.

The `kngwyu/rogue5.4.4` reference fork showed the same `main.c`
`WINDOW` blocker in this Ubuntu 24.04 probe.

## Diff Against Local Existing Tree

Comparison command output against the copied local tree:

- Same byte-for-byte: 2 files.
- Same after text line-ending normalization: 47 files.
- Changed content: 5 files.
- Present only in baseline: 3 files.
- Present only in local tree: 6 files.

Changed content files:

- `command.c`
- `io.c`
- `main.c`
- `rip.c`
- `rogue.h`

Present only in baseline:

- `.gitignore`
- `README.md`
- `new_level.c`

Present only in local tree:

- `draw_rogue_log.py`
- `io.BAK`
- `io.c.orig`
- `rogue.BAK`
- `rogue.h.org`
- `rogue_controller.py`

Clear local project modifications:

- `command.c` calls `log_inventory()` and `log_status()`.
- `io.c` defines logging functions and writes `/tmp/rogue_log.txt`.
- `main.c` removes `/tmp/rogue_log.txt` at startup and contains seed
  control clues.
- `rip.c` writes death information to the log.
- `rogue.h` contains declarations for local logging additions.

Known adjacent local assets:

- Loose `%USERPROFILE%\Downloads\extern.h` contains `MAXLINES 64` and
  `MAXCOLS 160`.
- Python controller and viewer scripts reference `/tmp/rogue_log.txt`.

Unknown provenance:

- Backup/original files in the local tree.
- Python controller and viewer scripts.
- Loose 64x160-related fragments outside the compared local tree.
- Any local author rights for logging, seed, controller, and screen-size
  changes.

## License Matrix

| Component | Evidence | Status |
| --- | --- | --- |
| Original Rogue-derived code | `LICENSE.TXT`, source headers | PASS |
| Nicholas J. Kisseberth portions | `LICENSE.TXT`, `state.c`, `mdport.c` | PASS |
| David Burren `xcrypt.c` | `LICENSE.TXT`, `xcrypt.c` | PASS |
| Autoconf helper files | Generated-tool notices | PASS WITH NOTICE RETENTION |
| Local logging and controller changes | Local diffs and scripts | Ownership unverified |
| Local 64x160 fragments | Loose adjacent files | Ownership unverified |

License conclusion:

```text
Pristine archive license evidence: PASS
Generated helper-file notices: PASS WITH NOTICE RETENTION
Repository inclusion: PENDING PROJECT APPROVAL
Local modification reuse: UNVERIFIED
```

## Adoption Gate

| Gate | Status | Notes |
| --- | --- | --- |
| Concrete source tree located | PASS | `phs/rogue` tag `v5.4.4` |
| Baseline archive hash recorded | PASS | Git archive SHA-256 recorded |
| `LICENSE.TXT` present | PASS | Project approval still required |
| `new_level.c` present | PASS | Present in baseline, missing locally |
| Amulet and return rules present | PASS | Source evidence found |
| Modern Ubuntu configure | BLOCKED | CRLF generated-script issue |
| Modern Ubuntu make | FAIL | ncurses `WINDOW` compatibility blocker |
| Runtime version check | NOT TESTED | No binary produced |
| Local diff classified | PARTIAL | Clear logging diffs found |
| Local modification ownership | BLOCKED | Authorship and rights unknown |
| Repository inclusion | BLOCKED | Pending legal and provenance review |

## Recommendation

Continue using `phs/rogue` tag `v5.4.4` as the baseline for Rogue
5.4.4 investigation and local legacy-diff analysis.

Do not adopt it as the project Rogue implementation yet. The remaining
blockers are:

- project approval of `LICENSE.TXT` and helper-file notices,
- provenance review of local modifications,
- a clean modern Linux build strategy,
- confirmation that any compatibility patch avoids game logic changes,
- Shinoda approval of whether local logging and 64x160 assets may be
  reused.
