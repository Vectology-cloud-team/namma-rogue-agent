# Rogue Source Investigation

This document records the current investigation state for Rogue source
selection. It complements `docs/rogue-source-selection.md` by keeping
the evidence trail separate from the recommendation summary.

## Investigation Constraints

- Target game remains Rogue.
- NetHack and NLE are reference projects only.
- No Rogue source is copied into this repository during this phase.
- No Rogue engine, Local AI, NaMMA, headless API, reset/step, or game
  code implementation is started during this phase.

## Local Search Findings

The strongest local finding is `%USERPROFILE%\Downloads\rogue`, a Rogue
5.4.4 / rogueforge source tree with a license file, build files, local
logs, and controller/viewer scripts.

Important evidence:

- `vers.c` reports `release = "5.4.4"`.
- `vers.c` reports `rogue (rogueforge) 09/05/07`.
- `main.c` has `@(#)main.c 4.22 (Berkeley) 02/05/99`.
- `rogue.h` has `@(#)rogue.h 5.42 (Berkeley) 08/06/83`.
- `rogue.h` defines `AMULETLEVEL 26`.
- `command.c`, `rip.c`, `pack.c`, `things.c`, and `misc.c` contain
  amulet and victory related logic.
- `state.c` contains state serialization helpers.
- Local controller/viewer scripts refer to `/tmp/rogue_log.txt`.
- Loose source fragments outside the tree include `MAXLINES 64` and
  `MAXCOLS 160`.

## Local Rogue 5.4.4 Completeness Check

Checked path:

```text
%USERPROFILE%\Downloads\rogue
```

Files and metadata found:

- `Makefile.in`: present.
- `Makefile.std`: present.
- `configure`: present.
- `configure.ac`: present.
- `configure.in`: not found.
- `Makefile`: not found.
- `MANIFEST`: not found.
- `README`: not found.
- `CHANGES`: not found.
- `FILES`: not found.
- `.git`, `.svn`, and `CVS`: not found.
- In-tree archives such as `.zip`, `.tar`, `.tgz`, `.tar.gz`, `.gz`,
  `.bz2`, or `.xz`: not found.

Backup and adjacent evidence found:

- `io.BAK`
- `io.c.orig`
- `rogue.BAK`
- `rogue.h.org`

`new_level.c` completeness result:

- `new_level.c` was not found in `%USERPROFILE%\Downloads\rogue`.
- `new_level.c` was not found in the searched user-area paths.
- `Makefile.in` references `new_level.o` and `new_level.c`.
- `Makefile.std` references `new_level.o` and `new_level.c`.
- `rogue54.vcproj` references `new_level.c`.
- `main.c`, `command.c`, `move.c`, and `rogue.h` reference
  `new_level()` as a function or prototype.
- No same-tree file with an obvious equivalent role was identified.

Current interpretation:

- The local source tree is incomplete, or the build metadata was copied
  from a tree that included `new_level.c`.
- Do not reconstruct `new_level.c` by guessing.
- Do not copy `new_level.c` from another source without provenance and
  license review.

## Pristine Archive Search

User-area search roots:

- `%USERPROFILE%\Downloads`
- `%USERPROFILE%\Documents`
- `%USERPROFILE%\Documents\Codex`

Search patterns included:

- `rogue5.4.4*`
- `rogue-5.4.4*`
- `rogue54*`
- `rogueforge*`
- `rogue-5.4*`
- `rogue*.zip`
- `rogue*.tar`
- `rogue*.tar.gz`
- `rogue*.tgz`
- `rogue*.gz`
- `rogue*.bz2`
- `rogue*.xz`

Result:

- No pristine Rogue 5.4.4 / rogueforge distribution archive was found.
- `work\rogue-local.tar` was found, but it is a temporary tar created
  from the local tree during this investigation and is not an upstream
  distribution artifact.
- `rogue54.sln` and `rogue54.vcproj` were found in the local tree, but
  they are Visual Studio project files, not source archives.

Because no pristine distribution archive was found, a file-by-file
upstream comparison could not be completed.

## Local Modification Classification

No pristine upstream tree was found, so these classifications are based
on local evidence only.

Suspected local modifications:

- `io.c`: differs from `io.c.orig` by 165 added lines and 15 removed
  lines; contains `/tmp/rogue_log.txt`, `log_status()`, and
  `log_inventory()`.
- `command.c`: calls `log_inventory()` and `log_status()`.
- `main.c`: removes `/tmp/rogue_log.txt` at startup and reads `SEED`
  in wizard mode.
- `rip.c`: writes `DEAD reason=...` to `/tmp/rogue_log.txt`.
- `rogue.h`: differs from `rogue.h.org` by 37 added lines; contains
  logging declarations and hook-related additions.
- `%USERPROFILE%\Downloads\extern.h`: loose fragment with
  `MAXLINES 64` and `MAXCOLS 160`.

Generated files or build artifacts:

- `configure`
- `config.guess`
- `config.sub`
- `config.h.in`
- `install-sh`
- `rogue` binary
- `rogue.html.in`
- `rogue.cat.in`

Unknown provenance:

- `rogue_controller.py`
- `rogue_log_viewer.py`
- `rogue_map_viewer.py`
- `draw_rogue_log.py`
- `rogue_log.txt`
- `io.BAK`
- `rogue.BAK`
- loose top-level C fragments under `%USERPROFILE%\Downloads`

## Berkeley Rogue 4.22 Question

The current evidence does not prove that a standalone game version named
Berkeley Rogue 4.22 has been found.

What is confirmed:

- A file revision tag `main.c 4.22 (Berkeley) 02/05/99` exists locally.
- That tag appears in a source tree whose game release is Rogue 5.4.4.

What is not confirmed:

- an executable displaying `Rogue v4.22 (Berkeley 02/05/99)`;
- a standalone Rogue 4.22 distribution archive;
- license text for a standalone Rogue 4.22 distribution;
- a complete source tree matching prior 4K / 64x160 work.
- whether earlier notes saying `Rogue v4.22` came from a game version
  display or from a human reading the `main.c` tag as a version.

Current conclusion:

- Treat Berkeley Rogue 4.22 as a known but unverified past-assets
  priority candidate.
- Treat the local `4.22` evidence as a file revision tag until stronger
  evidence is found.

## Technical Comparison

| Topic | Local Rogue 5.4.4 | NetBSD `games/rogue` | Berkeley Rogue 4.22 | Rogue 3.x | Modern preserved project |
| --- | --- | --- | --- | --- | --- |
| Concrete source located | Yes, local | Yes, external | No | No | Not yet |
| License file | Yes | Not in subdir inspection | Unknown | Unknown | Unknown |
| License status | Partially verified, blocked | Ambiguous, blocked | Unverified | Unverified | Unverified |
| Redistributable | Likely but not approved | Unknown | Unknown | Unknown | Unknown |
| Modifiable | Likely but not approved | Unknown | Unknown | Unknown | Unknown |
| Commercial use | Likely but not approved | Blocked by ambiguity | Unknown | Unknown | Unknown |
| Linux build | Configure ok, make fails | Not tested | Unknown | Unknown | Unknown |
| Curses dependency | High | High | Likely high | Likely high | Project-dependent |
| Logic/display separation | Medium-high difficulty | Medium-high difficulty | Unknown | Unknown | Project-dependent |
| Seed control | Evidence present | Evidence present | Unknown | Unknown | Unknown |
| Reset/step API | Medium-high difficulty | Medium-high difficulty | Unknown | Unknown | Project-dependent |
| Amulet and return rules | Present | Present | Expected, unverified | Expected, unverified | Required, unverified |
| 4.22 relationship | File tag only | Different lineage evidence | Target question | Older family | Project-dependent |
| Past asset compatibility | Highest found | Uncertain | Potentially highest | Low to unknown | Unknown |
| Recommendation | Investigate first | Legal review second | Recover exact source | Research later | Research later |

## External Research Status

External network fetches from the current environment were unreliable
for likely upstream sites such as `raw.githubusercontent.com`,
`rogue.rogueforge.net`, and SourceForge. The NetBSD candidate was
inspected from previously retrieved temporary files and repository URLs.

Because license decisions require exact source text and distribution
notes, external candidates remain blocked unless their source trees can
be fetched and inspected directly.

## Open Follow-Up Searches

- Find a pristine archive matching Rogue 5.4.4 / rogueforge 09/05/07.
- Find `new_level.c` matching the local tree.
- Search for a binary or source tree that prints
  `Rogue v4.22 (Berkeley 02/05/99)`.
- Locate concrete Rogue 3.x restoration or port source.
- Locate a modern Linux-preserved Rogue project with a clear license.
