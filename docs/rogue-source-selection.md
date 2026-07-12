# Rogue Source Selection

Current selection status: No Rogue implementation has been selected.

The target game is Rogue. Do not copy any Rogue implementation into this
repository until its exact source tree, license text, redistribution
terms, and modification terms are verified.

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

## Confirmed And Inspected Candidate

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
- Fixed seed difficulty: medium; `md_gseed()` and `srrandom()` exist.
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
  `Rogue v4.22 (Berkeley 02/05/99)`.
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

### Rogue 5.x Restoration Or Port

- Version: exact 5.x release not selected.
- Source: not yet verified.
- Last update status: unknown.
- License files: not inspected.
- License body: not inspected.
- Linux build possibility: unknown.
- Curses dependency: likely high.
- Game logic / display separation difficulty: likely medium to high.
- Fixed seed difficulty: unknown.
- `reset` / `step` API difficulty: likely high.
- Amulet and return rules: expected for Rogue, but unverified.
- Berkeley Rogue 4.22 relationship: unknown.
- Past asset compatibility: unknown.

```text
License status: Unverified
Repository inclusion: Prohibited until verified
```

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
strategy if all external source candidates remain blocked by license or
maintainability risk.

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
- enough similarity to Rogue 4.22 to reuse prior project knowledge.

No currently identified source satisfies all of these requirements.

## Current Recommendation Set

### Desired First-Choice Characteristics

This is a profile, not a selected implementation.

Reason:

- A license-clear, Linux-buildable Rogue source with original rules would
  best match the project priorities.

Benefits:

- Lower porting cost than exact historical code.
- Easier CI and mini PC validation.
- Cleaner path to headless environment work.

Risks:

- No concrete source has been verified yet.
- It may diverge from Berkeley Rogue 4.22 and prior assets.

### NetBSD `games/rogue`

Position:

- Best currently inspected technical candidate, blocked pending license
  review.

Benefits:

- Concrete source tree.
- Modern maintained BSD source.
- Amulet and return mechanics are present.
- RNG functions are identifiable.

Risks:

- Curses is embedded.
- It is not the suspected Rogue 4.22 past code.
- Source headers contain an older noncommercial/profit restriction.

Implementation impact:

- Medium to high. Display separation and command-loop refactoring are
  real work, but the source is inspectable.

### Berkeley Rogue 4.22

Position:

- Past-assets priority candidate, blocked pending source and license
  verification.

Benefits:

- Highest likely compatibility with prior project assets.
- Best option for reapplying old screen-size and controller work.
- Most direct path if old source and patches are found.

Risks:

- No verified source tree has been inspected.
- License is unknown.
- Build and portability status are unknown.
- Headless conversion may be harder than with a maintained port.

Implementation impact:

- Low to medium if prior patches are found and build cleanly.
- High if only an old unpatched source dump exists.

## Shinoda Decision Items

- Locate the exact Berkeley Rogue 4.22 source tree used in prior work.
- Decide whether commercial-use clarity is required before any import.
- Decide whether compatibility with past Rogue 4.22 assets outweighs a
  maintained source tree.
- Decide whether a from-scratch engine is acceptable if historical source
  candidates remain license-blocked.
- Decide whether the first implementation should prioritize headless API
  cleanliness over exact historical behavior.

## Required Next Steps

- Identify concrete Rogue 5.x and 3.x source distributions.
- Inspect `LICENSE`, `COPYING`, `README`, source headers, and
  distribution-site license notes for each concrete candidate.
- Build each viable candidate on modern Ubuntu or the mini PC.
- Confirm Amulet of Yendor placement and return-to-surface rules.
- Confirm whether RNG seed can be fixed.
- Prototype a minimal `reset` / `step` boundary without copying
  unverified code into this repository.

## Reference URLs

- https://github.com/NetBSD/src/tree/trunk/games/rogue
- https://raw.githubusercontent.com/NetBSD/src/trunk/games/rogue/rogue.h
- https://raw.githubusercontent.com/NetBSD/src/trunk/games/rogue/level.c
- https://www.nethack.org/common/license.html
- https://github.com/facebookresearch/nle
- https://en.wikipedia.org/wiki/Rogue_(video_game)
