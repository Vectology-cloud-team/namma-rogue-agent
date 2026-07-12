# Rogue Source Selection

Current selection status: No Rogue implementation has been selected.

The target game is Rogue. The remaining source-selection question is
which Rogue implementation should be used. NetHack and the NetHack
Learning Environment may only be referenced for environment design
ideas.

Do not copy any Rogue implementation into this repository until its
exact source tree, license text, redistribution terms, and modification
terms are verified.

NetHack and the NetHack Learning Environment are not candidate target
games and are not candidate Rogue source bases. They are referenced only
for environment API design, observation/action modeling, replay,
evaluation, and testing methodology.

## Selection Priorities

1. The license is clear.
2. The game has the Amulet of Yendor acquisition and return-to-surface rules.
3. The source can be built on modern Linux.
4. The game logic can be made headless without excessive rewriting.
5. Fixed seeds and replay can be implemented cleanly.
6. Existing Rogue 4.22-era assets can be reused.
7. The curses display can remain as a viewer.
8. Behavior remains close to original Rogue.

## Candidate Summary

Local Rogue 5.4.4 / rogueforge 09/05/07 tree:

- Status: current most promising investigation target, but not selected.
- License: evidence is present but not fully reviewed.
- Build: configure succeeds, make fails on missing `new_level.c`.
- Repository inclusion: prohibited pending review.

NetBSD `games/rogue`:

- Status: confirmed and inspected external candidate.
- License: conflicting header evidence requires review.
- Build: not built in this project.
- Recommendation: best currently inspected technical candidate, blocked
  pending license review.

Berkeley Rogue 4.22:

- Status: known candidate not yet located or verified.
- License: unverified.
- Build: unknown.
- Recommendation: past-assets priority candidate, blocked pending exact
  source and license verification.

Rogue 3.x restoration or port:

- Status: unverified category.
- License: unverified.
- Build: unknown.
- Recommendation: research category only.

Modern Linux-preserved Rogue project:

- Status: unverified category.
- License: unverified.
- Build: unknown.
- Recommendation: research category only.

From-scratch Rogue-compatible engine:

- Status: fallback strategy, not a Rogue source candidate.
- License: repository license to choose.
- Build: designed by this project.
- Recommendation: consider only if external sources remain blocked.

## Confirmed And Inspected Candidates

### Local Rogue 5.4.4 / rogueforge 09/05/07 Tree

Status:

- Inspected local legacy asset.
- Current most promising investigation target.
- Not selected.
- Do not import into this repository until source completeness, local
  modification ownership, and license review are complete.

Required status wording:

```text
Technical candidate: promising
License evidence: present but not fully reviewed
Repository inclusion: prohibited pending review
Commercial project adoption: not yet approved
```

Facts inspected:

- Formal name: local Rogue 5.4.4 / rogueforge tree.
- Version: `release = "5.4.4"`.
- Version string: `rogue (rogueforge) 09/05/07`.
- Local source: `%USERPROFILE%\Downloads\rogue`.
- Distribution origin: local copy; upstream URL not verified because
  external fetches to likely sources failed in the current environment.
- Last update status: local tree date not treated as upstream evidence.
- License file presence: `LICENSE.TXT` present.
- License evidence: source headers refer to `LICENSE.TXT`.
- License body: BSD-3-clause-style terms for Toy, Arnold, and Wichman;
  separate BSD-style terms for Nicholas J. Kisseberth portions; separate
  BSD-style terms for David Burren `xcrypt.c` portions.
- Amulet rules: `AMULETLEVEL`, `AMULET`, amulet object handling, and
  `total_winner()` are present.
- Build status on Ubuntu 24.04: configure succeeds, make fails because
  `new_level.o` is required but `new_level.c` is absent from the local
  tree.
- Curses dependency: high; curses calls and screen refresh are mixed
  into command and display flow.
- Seed evidence: seed variables and environment-based seed path are
  present in `main.c`.
- Berkeley Rogue 4.22 relationship: includes file-level SCCS tag
  `@(#)main.c 4.22 (Berkeley) 02/05/99`; this is not sufficient to
  prove a game release named Rogue 4.22.
- Past asset compatibility: high, because the local tree and loose files
  contain logging hooks and 64x160-related fragments.

Reasons it is the current most promising investigation target:

- A concrete source tree exists locally.
- `LICENSE.TXT` exists.
- Amulet acquisition and return logic are present.
- It is closely related to previous controller, log, and 64x160 assets.
- It contains seed-control clues.

Current blockers:

- `new_level.c` is missing.
- A pristine upstream distribution has not been found.
- Local modification authorship and rights are unverified.
- A complete build has not been verified.
- Formal adoption requires license review.

Assessment:

- Redistribution possibility: likely allowed by included BSD-style
  upstream license text, but blocked until local modifications and exact
  provenance are verified.
- Modification possibility: likely allowed by included BSD-style
  upstream license text, but blocked until local modifications and exact
  provenance are verified.
- Commercial use possibility: likely allowed by included BSD-style
  upstream license text, but blocked until local modifications and exact
  provenance are verified.
- Linux build possibility: close but not clean because `new_level.c` is
  missing or the local build metadata is stale.
- Game logic / display separation difficulty: medium to high.
- Fixed seed difficulty: medium; seed plumbing exists but must be made a
  first-class environment input.
- `reset` / `step` API difficulty: medium to high because the game loop,
  curses, input, and display are intertwined.
- Past asset compatibility: best currently found local match.
- Recommendation: continue investigating first, but do not select until
  source completeness, provenance, and license review are resolved.

Repository inclusion:

```text
Repository inclusion: prohibited pending review
```

### NetBSD `games/rogue`

Status:

- Best currently inspected technical candidate, blocked pending license
  review.
- Technically inspectable, but not selected.
- Do not import into this repository until license review is complete.

Facts inspected:

- Formal name: NetBSD `games/rogue`.
- Version evidence: Berkeley SCCS strings such as
  `8.1 (Berkeley) 5/31/93`.
- Source: https://github.com/NetBSD/src/tree/trunk/games/rogue.
- Last update status: active NetBSD source tree.
- License file presence: no standalone subdirectory `LICENSE` was
  inspected.
- License evidence: source headers were inspected.
- Amulet rules: `AMULET`, `AMULET_LEVEL`, `put_amulet()`, and
  `has_amulet()` are present in inspected source.
- Build status on this project machine: not tested.

License notes:

- Source headers include a Regents of the University of California
  BSD-style redistribution notice.
- The same files also contain older Rogue text stating that the code is
  not to be traded, sold, or used for personal gain or profit.
- This creates a license ambiguity that must be reviewed before use.

Assessment:

- Redistribution possibility: blocked pending review.
- Modification possibility: blocked pending review.
- Commercial use possibility: blocked pending review.
- Linux build possibility: likely feasible with portability work, but
  unverified in this project.
- Curses dependency: high; inspected headers include `<curses.h>`.
- Game logic / display separation difficulty: medium to high.
- Fixed seed difficulty: medium; RNG functions are identifiable.
- `reset` / `step` API difficulty: medium to high.
- Berkeley Rogue 4.22 relationship: not the same as the suspected
  `Rogue v4.22 (Berkeley 02/05/99)` past asset.
- Past asset compatibility: uncertain.
- Recommendation: keep as the best currently inspected technical
  candidate, but do not select until license review clears it.

Repository inclusion:

```text
Repository inclusion: Prohibited until reviewed
```

## Known Candidate Not Yet Located Or Verified

### Berkeley Rogue 4.22

Status:

- Past-assets priority candidate, blocked pending source and license
  verification.
- Expected to be the most compatible option if the previous project used
  a source tree actually identified as `Rogue v4.22 (Berkeley 02/05/99)`.
- Not selected.

Open facts:

- Formal name: Berkeley Rogue 4.22.
- Version display to verify: `Rogue v4.22 (Berkeley 02/05/99)`.
- Exact source tree: not located.
- Source origin: not verified.
- Berkeley relationship: not verified.
- License file presence: not inspected.
- License body: not inspected.
- Current distribution source: not verified.
- Modern Linux build status: unknown.

Current local evidence:

- A file tag `@(#)main.c 4.22 (Berkeley) 02/05/99` was found.
- That tag appears inside a tree whose game version is Rogue 5.4.4.
- No standalone Berkeley Rogue 4.22 tree was found.
- Therefore `4.22` is currently treated as a source file revision tag,
  not as a verified game implementation version.
- If previous notes said `Rogue v4.22`, it remains unknown whether that
  was a game-displayed version or a human interpretation of the
  `main.c` SCCS tag.

Assessment:

- Redistribution possibility: unknown.
- Modification possibility: unknown.
- Commercial use possibility: unknown.
- Curses dependency: likely high, but unverified for the exact source.
- Game logic / display separation difficulty: likely high.
- Fixed seed difficulty: likely medium, but exact RNG entry point must be
  inspected.
- `reset` / `step` API difficulty: likely high.
- Amulet and return rules: expected for Rogue, but must be verified in
  the exact source.
- Past asset compatibility: likely highest if this is the exact codebase
  used previously.
- 4K / 64x160 reapplication: likely easiest if prior patches were made
  against this source tree.
- Main headless changes: isolate input, isolate rendering, expose state,
  expose observable legal actions, control RNG seed, and replace the
  process-level game loop with episode state.

Repository inclusion:

```text
License status: Unverified
Repository inclusion: Prohibited until verified
```

## Unverified Candidate Categories

These are research categories, not concrete implementation candidates
yet. A category becomes a candidate only after a specific source tree is
located and its license files, source headers, README, COPYING, and
distribution notes are inspected.

### Rogue 3.x Restoration Or Port

- Version: exact 3.x release not selected.
- Source: not yet verified.
- Last update status: unknown.
- License files: not inspected.
- License body: not inspected.
- Linux build possibility: unknown.
- Curses dependency: likely high.
- Game logic / display separation difficulty: likely high.
- Fixed seed difficulty: unknown.
- `reset` / `step` API difficulty: likely high.
- Amulet and return rules: expected for Rogue, but unverified.
- Berkeley Rogue 4.22 relationship: older Rogue family, exact divergence
  unknown.
- Past asset compatibility: probably lower than exact Rogue 4.22.

```text
License status: Unverified
Repository inclusion: Prohibited until verified
```

### Modern Linux-Preserved Rogue Project

- Version: exact project not selected.
- Source: not yet verified.
- Last update status: unknown.
- License files: not inspected.
- License body: not inspected.
- Linux build possibility: the main reason to research this category.
- Curses dependency: likely medium to high.
- Game logic / display separation difficulty: project-dependent.
- Fixed seed difficulty: project-dependent.
- `reset` / `step` API difficulty: project-dependent.
- Amulet and return rules: required; reject the project if absent.
- Berkeley Rogue 4.22 relationship: must be documented per project.
- Past asset compatibility: unknown.

```text
License status: Unverified
Repository inclusion: Prohibited until verified
```

## Fallback Option

### From-Scratch Rogue-Compatible Engine

This is not a Rogue source candidate. It is a fallback implementation
strategy if all external source candidates remain blocked by license,
source completeness, or maintainability risk.

- Source: this repository.
- License: repository license still to be selected.
- Linux build possibility: can be designed in from the start.
- Curses dependency: optional viewer only.
- Game logic / display separation difficulty: lowest if designed
  correctly.
- Fixed seed difficulty: lowest if designed correctly.
- `reset` / `step` API difficulty: lowest if designed correctly.
- Amulet and return rules: must be implemented explicitly.
- Berkeley Rogue 4.22 relationship: behavioral compatibility only.
- Past asset compatibility: low for source patches, medium for lessons,
  logs, tests, and UI assumptions.

## Reference Projects

### NetHack

Why it is referenced:

- environment architecture,
- long-horizon roguelike agent evaluation,
- replay ideas,
- structured command modeling,
- license wording examples.

License handling:

- Not a Rogue source candidate.
- Do not mix its license with Rogue candidates.

### NetHack Learning Environment

Why it is referenced:

- AI environment API,
- observation/action modeling,
- task suites,
- replay and dataset patterns,
- evaluation methodology.

License handling:

- Not a Rogue source candidate.
- Verify its license only if referencing or copying NLE-specific code.

## Desired First-Choice Characteristics

The desired first-choice source has:

- clear license text,
- clear redistribution permission,
- clear modification permission,
- clear commercial-use status,
- Amulet of Yendor and return-to-surface rules,
- a modern Linux build path,
- separable game logic and display,
- controllable RNG seed,
- a plausible path to `reset` / `step`,
- enough similarity to Rogue 4.22-era local assets to reuse prior
  project knowledge.

No currently identified source satisfies all of these requirements.

## Current Recommendation Set

### First Investigation Priority: Local Rogue 5.4.4 Profile

This is not a final selection.

Reason:

- The local Rogue 5.4.4 / rogueforge tree is the current most promising
  investigation target because it has the strongest combination of
  license-file evidence, amulet-rule evidence, seed evidence, and
  compatibility with previously found local assets.

Benefits:

- Includes a concrete local source tree.
- Includes `LICENSE.TXT`.
- Includes Amulet and return-to-surface mechanics.
- Contains existing status and inventory logging hooks.
- Has nearby 64x160-related fragments that may help reapply past work.

Risks:

- Local tree is incomplete or build metadata is stale because
  `new_level.c` is missing.
- Exact upstream distribution and local modification authorship are not
  yet verified.
- Curses, input, rendering, and game loop are intertwined.

License caution:

- Treat the upstream license as promising but not sufficient until local
  modifications, loose files, and provenance are reviewed.

Implementation impact:

- Medium if `new_level.c` or a pristine matching upstream archive is
  recovered.
- High if the missing file must be reconstructed or the source tree is
  heavily locally modified.

### Second Recommendation: NetBSD `games/rogue`

This is not a final selection.

Reason:

- NetBSD `games/rogue` is the best currently inspected external
  technical candidate.

Benefits:

- Concrete maintained source tree.
- Amulet and return mechanics are present.
- RNG functions are identifiable.

Risks:

- License headers contain conflicting evidence.
- It is not the suspected prior local source.
- Past 4K / 64x160 assets may not apply cleanly.

License caution:

- Blocked until a legal review resolves the old noncommercial/profit
  restriction text.

Implementation impact:

- Medium to high because display separation and command-loop refactoring
  are real work.

### Past-Assets Priority: Berkeley Rogue 4.22 Or Local 4.22-Tagged Assets

This is not a final selection.

Reason:

- If the exact historical source tree is recovered, it is likely the
  best base for reusing previous screen-size, logging, and controller
  work.

Benefits:

- Highest likely compatibility with prior project assets.
- Best option for reapplying old screen-size and controller work.

Risks:

- No exact source tree has been found.
- License is unknown for the exact tree.
- Local evidence may indicate a file revision tag, not a game version.

License caution:

- Blocked until the exact tree and license are verified.

Implementation impact:

- Low to medium if exact prior patches and build steps are found.
- High if only fragments remain.

## Shinoda Decision Items

- Decide whether to continue recovering the missing local Rogue 5.4.4
  `new_level.c` or pristine upstream archive.
- Decide whether commercial-use clarity is required before any import.
- Decide whether compatibility with past local assets outweighs a
  maintained source tree.
- Decide whether NetBSD license ambiguity is acceptable to send for
  legal review.
- Decide whether a from-scratch engine is acceptable if historical
  source candidates remain blocked.

## Required Next Steps

- Locate a pristine upstream archive matching the local Rogue 5.4.4
  / rogueforge tree.
- Recover or verify `new_level.c` for the local tree.
- Locate the exact source or executable that displays
  `Rogue v4.22 (Berkeley 02/05/99)`, if it exists.
- Inspect concrete Rogue 3.x source distributions.
- Inspect `LICENSE`, `COPYING`, `README`, source headers, and
  distribution-site license notes for each concrete candidate.
- Build each viable candidate on modern Ubuntu or the mini PC.
- Confirm Amulet of Yendor placement and return-to-surface rules.
- Confirm whether RNG seed can be fixed.
- Prototype a minimal `reset` / `step` boundary only after a source is
  selected.

## Reference URLs

- https://github.com/NetBSD/src/tree/trunk/games/rogue
- https://raw.githubusercontent.com/NetBSD/src/trunk/games/rogue/rogue.h
- https://raw.githubusercontent.com/NetBSD/src/trunk/games/rogue/level.c
- https://www.nethack.org/common/license.html
- https://github.com/facebookresearch/nle
- https://en.wikipedia.org/wiki/Rogue_(video_game)
