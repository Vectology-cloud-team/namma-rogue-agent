# Legacy Asset Inventory

This inventory records local Rogue-related assets found outside the
repository. It is an evidence log, not an import approval. Do not copy
these assets into this repository until license, provenance,
redistribution terms, and modification ownership are reviewed.

Local paths are intentionally written with `%USERPROFILE%` instead of a
machine-specific absolute user directory.

## Search Scope

Checked locations:

- `%USERPROFILE%\Documents`
- `%USERPROFILE%\Downloads`
- `%USERPROFILE%\Documents\Codex`

Locations not present on this machine:

- `%USERPROFILE%\Desktop`
- `%USERPROFILE%\source`
- `%USERPROFILE%\projects`

Search exclusions:

- `.git`
- `node_modules`
- `.venv`
- `venv`
- `__pycache__`
- generated dependency and cache directories

## Found Assets

### LA-001: Local Rogue Source Tree

- Path: `%USERPROFILE%\Downloads\rogue`
- Summary: local Rogue source tree with C source, build files,
  documentation templates, a prebuilt `rogue` binary, logs, and Python
  helper scripts.
- Apparent version: Rogue 5.4.4.
- Version evidence: `vers.c` defines `release = "5.4.4"` and
  `version[] = "rogue (rogueforge) 09/05/07"`.
- Investigation status: current most promising investigation target,
  but not selected.
- Berkeley evidence: `main.c` contains the SCCS-style file tag
  `@(#)main.c 4.22 (Berkeley) 02/05/99`.
- License file: `LICENSE.TXT` is present.
- Source headers: most C files refer to `LICENSE.TXT`.
- Build files: `configure`, `configure.ac`, `Makefile.in`,
  `Makefile.std`, and project files are present.
- Build status: configure succeeded on Ubuntu 24.04, but `make` failed
  because `new_level.o` is listed as a target while `new_level.c` was
  not present in the local tree.
- Baseline comparison: compared against `phs/rogue` tag `v5.4.4`,
  exported as `phs-rogue-v5.4.4-git-archive.tar`.
- Baseline result: `new_level.c` is present in the baseline and absent
  from this local tree.
- Completeness status: `Makefile`, `MANIFEST`, `README`, `CHANGES`,
  `FILES`, and in-tree pristine archives were not found.
- History status: `.git`, `.svn`, and `CVS` were not found.
- Amulet rule evidence: `AMULETLEVEL`, `AMULET`, `total_winner()`, and
  amulet object handling are present.
- Curses dependency: high.
- Reusable: possibly, after source completeness and license review.
- Repository inclusion: prohibited until verified.

Diff against `phs/rogue` tag `v5.4.4`:

- Same byte-for-byte: 2 files.
- Same after text line-ending normalization: 47 files.
- Changed content: `command.c`, `io.c`, `main.c`, `rip.c`, `rogue.h`.
- Present only in baseline: `.gitignore`, `README.md`, `new_level.c`.
- Present only in local tree: `draw_rogue_log.py`, `io.BAK`,
  `io.c.orig`, `rogue.BAK`, `rogue.h.org`, `rogue_controller.py`.

Clear local project modification evidence:

- `command.c` calls `log_inventory()` and `log_status()`.
- `io.c` defines logging functions and writes `/tmp/rogue_log.txt`.
- `main.c` removes `/tmp/rogue_log.txt` at startup and contains seed
  control clues.
- `rip.c` writes death information to the log.
- `rogue.h` contains local logging declarations.

Classification:

- Upstream unchanged: 47 files after text line-ending normalization.
- Local Vectology modification: logging and seed-related changes appear
  in `command.c`, `io.c`, `main.c`, `rip.c`, and `rogue.h`.
- Generated or temporary: backup/original files and prior build output.
- Unknown provenance: Python scripts, loose 64x160 fragments, and local
  modification authorship.

### LA-002: Loose Modified Rogue Source Fragments

- Path: `%USERPROFILE%\Downloads\main.c`
- Path: `%USERPROFILE%\Downloads\extern.h`
- Path: `%USERPROFILE%\Downloads\extern.c`
- Path: `%USERPROFILE%\Downloads\rooms.c`
- Path: `%USERPROFILE%\Downloads\rogue.h`
- Summary: loose C source fragments adjacent to the local tree.
- Important evidence: `%USERPROFILE%\Downloads\extern.h` defines
  `MAXLINES 64` and `MAXCOLS 160`.
- Relationship to 4K / 64x160 work: likely related to earlier enlarged
  screen experiments.
- Relationship to LA-001: filenames and headers overlap with the
  source tree, but the loose files are not a complete standalone source
  tree.
- License file: no adjacent `LICENSE.TXT` was inspected for the loose
  fragment set; the headers point to a `LICENSE.TXT`.
- Build status: not buildable as a standalone tree.
- Reusable: as reference material for reapplying display-size changes,
  not as imported source until provenance is verified.
- Repository inclusion: prohibited until verified.

### LA-003: Python Controller And Viewer Scripts

- Path: `%USERPROFILE%\Downloads\rogue_controller.py`
- Path: `%USERPROFILE%\Downloads\rogue_log_viewer.py`
- Path: `%USERPROFILE%\Downloads\rogue_map_viewer.py`
- Path: `%USERPROFILE%\Downloads\draw_rogue_log.py`
- Path: `%USERPROFILE%\Downloads\rogue\rogue_controller.py`
- Summary: Python helper scripts for controlling Rogue or visualizing
  Rogue logs.
- Evidence: scripts reference `/tmp/rogue_log.txt`.
- Encoding note: some comments appear mojibake-encoded.
- License status: unverified.
- Reusable: useful as design notes for logging, pseudo-terminal
  control, and viewers after ownership is confirmed.
- Repository inclusion: prohibited until verified.

### LA-004: Rogue Logs

- Path: `%USERPROFILE%\Downloads\rogue_log.txt`
- Path: `%USERPROFILE%\Downloads\rogue\rogue_log.txt`
- Summary: logs from earlier Rogue runs.
- Reusable: useful for understanding previous status and inventory log
  formats.
- License status: local data, ownership still to confirm before
  publishing.
- Repository inclusion: do not import until reviewed for privacy and
  ownership.

### LA-005: Temporary NetBSD Inspection Files

- Path: `work\netbsd-rogue-main.c`
- Path: `work\netbsd-rogue-level.c`
- Path: `work\netbsd-rogue-rogue.h`
- Summary: temporary files created during source-candidate inspection.
- Source: NetBSD `src/games/rogue` raw files.
- Reusable: evidence only.
- Repository inclusion: prohibited pending license review.

## Berkeley Rogue 4.22 Finding

No standalone source tree or executable output matching
`Rogue v4.22 (Berkeley 02/05/99)` was found.

What was found:

- `main.c` contains `@(#)main.c 4.22 (Berkeley) 02/05/99`.
- The same local source tree reports game release `5.4.4` in `vers.c`.
- The same local source tree reports `rogue (rogueforge) 09/05/07`.

Current interpretation:

- `4.22` is currently treated as a file-level SCCS revision tag for
  `main.c`, not as a verified game distribution version.
- The exact prior "Berkeley Rogue 4.22" asset remains unverified.
- If older notes used `Rogue v4.22`, it is still unknown whether that
  came from a game-displayed version or from a human reading the
  `main.c` tag as the game version.
- Prior 4K / 64x160 work probably exists as local modifications or
  loose fragments, but the exact patch set has not been recovered.

## Archive Search Result

No pristine Rogue 5.4.4 / rogueforge archive was found in the searched
user-area paths.

The only matching archive-like result was `work\rogue-local.tar`, a
temporary tar created from `%USERPROFILE%\Downloads\rogue` during the
investigation. It is not a pristine upstream distribution.

## Preservation Rules

- Do not delete local legacy assets.
- Do not copy source into this repository until license review clears
  it.
- Record build, provenance, and license evidence before any import.
- Treat Python scripts and logs as private local assets until reviewed.
