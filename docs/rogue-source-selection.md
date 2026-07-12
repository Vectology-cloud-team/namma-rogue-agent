# Rogue Source Selection

The target game is Rogue. Do not copy any Rogue implementation into this repository until its exact source tree, license text, redistribution terms, and modification terms are verified.

NetHack and the NetHack Learning Environment are not candidate target games and are not candidate Rogue source bases. They are referenced only for environment API design, observation/action modeling, replay, evaluation, and testing methodology.

## Selection Priorities

1. The license is clear.
2. The game has the Amulet of Yendor acquisition and return-to-surface rules.
3. The source can be built on modern Linux.
4. The game logic can be made headless without excessive rewriting.
5. Fixed seeds and replay can be implemented cleanly.
6. Existing Rogue 4.22-era assets can be reused.
7. The curses display can remain as a viewer.
8. Behavior remains close to original Rogue.

## Rogue Source Candidates

| Candidate | Version | Source | Last update status | License files / headers | License status | Repository inclusion | Recommendation |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Berkeley Rogue 4.22 | `Rogue v4.22 (Berkeley 02/05/99)` as reported by prior project context | Prior/local asset or mirror still to be identified | Unknown | Not yet inspected in a source tree | Unverified | Prohibited until verified | Past-assets priority candidate only after locating the exact source tree |
| NetBSD `games/rogue` | Berkeley SCCS `8.1 (Berkeley) 5/31/93`; NetBSD `rogue.h` revision observed as 2025-04-07 | https://github.com/NetBSD/src/tree/trunk/games/rogue | Actively maintained in NetBSD source tree | Source headers include a Regents of the University of California BSD-style notice and an older Rogue notice forbidding trade/sale/personal gain | Conflicting / needs legal review | Prohibited until reviewed | Strong technical candidate, not yet a clean license candidate |
| Rogue 5.x restoration or port | 5.x family, exact release not selected | Candidate tarballs/mirrors such as historical Rogue restoration archives; exact accessible source tree not yet verified | Unknown | Not yet inspected | Unverified | Prohibited until verified | Required comparison item; do not use until a concrete source tree is inspected |
| Rogue 3.x restoration or port | 3.x family, exact release not selected | Candidate tarballs/mirrors such as historical Rogue restoration archives; exact accessible source tree not yet verified | Unknown | Not yet inspected | Unverified | Prohibited until verified | Required comparison item; likely useful for behavior comparison, not yet for implementation |
| Modern Linux-preserved original-Rogue project | Exact project not selected | Examples to investigate include BSD-derived ports and preservation projects that provide build scripts for Linux | Unknown | Not yet inspected except NetBSD source headers above | Unverified unless based on reviewed NetBSD tree | Prohibited until verified | Good implementation path if license and build evidence are clean |
| From-scratch Rogue-compatible engine | Project-owned | This repository | New work | Repository license to be selected | Controlled by this project | Allowed after repository license decision | Best fallback if all source candidates remain license-blocked |

## Candidate Details

### Berkeley Rogue 4.22

- Formal name: Berkeley Rogue 4.22, displayed in prior project context as `Rogue v4.22 (Berkeley 02/05/99)`.
- Version: 4.22.
- Repository or distribution source: not yet identified in an inspectable source tree.
- Last update status: unknown; the displayed date suggests a 1999 Berkeley-labeled build or patch level, but this has not been tied to a verified source distribution.
- License file presence: unknown.
- License body: not inspected.
- Redistribution possibility: unknown.
- Modification possibility: unknown.
- Commercial use possibility: unknown.
- Linux build possibility: unknown until the exact source tree is located.
- Curses dependency: likely high, based on the Rogue family and prior screen-control assets, but unverified for this exact tree.
- Game logic / display separation difficulty: likely high unless the existing code already has clean module boundaries.
- Fixed seed difficulty: likely medium; exact RNG entry point must be inspected.
- `reset` / `step` API difficulty: likely high because the historical code is expected to be interactive.
- Amulet and return rules: expected for Rogue, but must be confirmed in the exact source.
- Relationship to Berkeley Rogue 4.22: this is the specific past-assets candidate.
- Compatibility with past assets: highest likely compatibility if the prior work really used this build.
- 4K / 64x160 reapplication: likely easiest here if prior patches were against this codebase.
- Main headless changes: isolate input, isolate rendering, expose dungeon state, expose legal actions, control RNG seed, replace process-level game loop with episode state.
- License status: Unverified.
- Repository inclusion: Prohibited until verified.
- Recommendation: keep as the past-assets priority option, but do not import until the exact source and license are found.

### NetBSD `games/rogue`

- Formal name: NetBSD `games/rogue`.
- Version: Berkeley SCCS strings observed as `8.1 (Berkeley) 5/31/93`; NetBSD file revisions are newer.
- Repository or distribution source: https://github.com/NetBSD/src/tree/trunk/games/rogue.
- Last update status: active NetBSD source tree; `rogue.h` showed a 2025 NetBSD revision in the inspected raw file.
- License file presence: no standalone `LICENSE` was inspected for this subdirectory; source headers were inspected.
- License body: source headers include a Regents of the University of California BSD-style redistribution notice. The same files also contain older Rogue text stating that the code is not to be traded, sold, or used for personal gain or profit.
- Redistribution possibility: source redistribution appears allowed by the BSD-style notice, but the older noncommercial/profit restriction creates a conflict that must be reviewed.
- Modification possibility: source modification appears allowed by the BSD-style notice and older Rogue notice, but commercial and profit restrictions remain unclear.
- Commercial use possibility: not clear because of the older noncommercial/profit restriction in source headers.
- Linux build possibility: likely feasible with portability work because this is maintained in a modern BSD tree and uses standard C plus curses, but it has not been built on this project machine.
- Curses dependency: high; `rogue.h` includes `<curses.h>`.
- Game logic / display separation difficulty: medium to high; game state is structured in C globals, but rendering calls are mixed into gameplay paths.
- Fixed seed difficulty: medium; `md_gseed()` and `srrandom()` exist and can become a controlled seed boundary.
- `reset` / `step` API difficulty: medium to high; `play_level()` and command input must be refactored or wrapped.
- Amulet and return rules: present in inspected source: `AMULET`, `AMULET_LEVEL`, `put_amulet()`, `has_amulet()`, and up/down level logic are present.
- Berkeley Rogue 4.22 relationship: not the same as `Rogue v4.22 (Berkeley 02/05/99)`; it is a BSD/NetBSD-maintained Rogue tree with Berkeley SCCS history.
- Compatibility with past assets: uncertain; likely lower than exact 4.22 if past patches rely on specific screen dimensions or source layout.
- 4K / 64x160 reapplication: possible but likely requires reworking `DROWS`, `DCOLS`, status layout, and curses assumptions.
- Main headless changes: separate curses output, make RNG injectable, turn command loop into `step`, expose observation, legal actions, terminal reasons, and replay hooks.
- License status: Conflicting / requires review.
- Repository inclusion: Prohibited until reviewed.
- Recommendation: technically promising; license ambiguity prevents first recommendation until reviewed.

### Rogue 5.x Restoration Or Port

- Formal name: not selected; likely candidates include historical 5.x restoration archives or ports.
- Version: exact 5.x release unknown.
- Repository or distribution source: not yet verified. The previously attempted Rogue restoration host was not reachable from this environment.
- Last update status: unknown.
- License file presence: not inspected.
- License body: not inspected.
- Redistribution possibility: unknown.
- Modification possibility: unknown.
- Commercial use possibility: unknown.
- Linux build possibility: unknown until a concrete source tree is inspected.
- Curses dependency: likely high.
- Game logic / display separation difficulty: likely medium to high.
- Fixed seed difficulty: unknown.
- `reset` / `step` API difficulty: likely high without prior refactoring.
- Amulet and return rules: expected for Rogue 5.x, but must be verified in source.
- Berkeley Rogue 4.22 relationship: same broad Rogue lineage, exact relationship unknown.
- Compatibility with past assets: unknown; likely lower than 4.22 unless file layout is close.
- License status: Unverified.
- Repository inclusion: Prohibited until verified.
- Recommendation: required research branch, not an implementation base yet.

### Rogue 3.x Restoration Or Port

- Formal name: not selected; likely candidates include historical 3.x restoration archives or ports.
- Version: exact 3.x release unknown.
- Repository or distribution source: not yet verified.
- Last update status: unknown.
- License file presence: not inspected.
- License body: not inspected.
- Redistribution possibility: unknown.
- Modification possibility: unknown.
- Commercial use possibility: unknown.
- Linux build possibility: unknown until a concrete source tree is inspected.
- Curses dependency: likely high.
- Game logic / display separation difficulty: likely high because older code may have tighter terminal coupling.
- Fixed seed difficulty: unknown.
- `reset` / `step` API difficulty: likely high.
- Amulet and return rules: expected for Rogue, but must be verified in source.
- Berkeley Rogue 4.22 relationship: older Rogue family; exact divergence from 4.22 unknown.
- Compatibility with past assets: probably lower than 4.22.
- License status: Unverified.
- Repository inclusion: Prohibited until verified.
- Recommendation: useful for historical behavior comparison, not first implementation candidate.

### Modern Linux-Preserved Original-Rogue Project

- Formal name: not selected.
- Version: unknown.
- Repository or distribution source: investigate BSD-derived maintained trees, package-manager source packages, and preservation projects with Linux build instructions.
- Last update status: unknown until selected.
- License file presence: not inspected.
- License body: not inspected.
- Redistribution possibility: unknown.
- Modification possibility: unknown.
- Commercial use possibility: unknown.
- Linux build possibility: core purpose of this candidate category.
- Curses dependency: likely medium to high.
- Game logic / display separation difficulty: depends on project quality.
- Fixed seed difficulty: depends on project quality.
- `reset` / `step` API difficulty: depends on project quality.
- Amulet and return rules: must be present; otherwise it should be rejected.
- Berkeley Rogue 4.22 relationship: must be documented per concrete project.
- Compatibility with past assets: unknown.
- License status: Unverified.
- Repository inclusion: Prohibited until verified.
- Recommendation: potentially first recommendation if a concrete, license-clear, Linux-buildable project is found.

### From-Scratch Rogue-Compatible Engine

- Formal name: NaMMA Rogue engine, if selected later.
- Version: project-defined.
- Repository or distribution source: this repository.
- Last update status: new work.
- License file presence: repository license still to be selected.
- License body: controlled by this project after selection.
- Redistribution possibility: controlled by this project.
- Modification possibility: controlled by this project.
- Commercial use possibility: controlled by this project.
- Linux build possibility: can be designed for Linux from the start.
- Curses dependency: optional viewer only.
- Game logic / display separation difficulty: lowest if designed correctly.
- Fixed seed difficulty: lowest if designed correctly.
- `reset` / `step` API difficulty: lowest if designed correctly.
- Amulet and return rules: must be implemented explicitly.
- Berkeley Rogue 4.22 relationship: behavioral compatibility only; no source compatibility.
- Compatibility with past assets: low for source patches, medium for lessons and test cases.
- License status: Pending repository license selection.
- Repository inclusion: allowed after repository license decision.
- Recommendation: best fallback if external source licensing remains blocked.

## Reference Projects

| Project | Version / Source | Why it is referenced | License handling |
| --- | --- | --- | --- |
| NetHack | Official NetHack project and license page | Environment architecture, long-horizon roguelike agent evaluation, replay ideas, structured command modeling, license wording examples | Not a Rogue source candidate; do not mix its license with Rogue candidates |
| NetHack Learning Environment | `facebookresearch/nle`, now archived and pointing to a successor home | AI environment API, observation/action modeling, task suites, replay/dataset patterns, evaluation methodology | Not a Rogue source candidate; verify its own license only if referencing or copying NLE-specific code |

## Reference URLs

- https://github.com/NetBSD/src/tree/trunk/games/rogue
- https://raw.githubusercontent.com/NetBSD/src/trunk/games/rogue/rogue.h
- https://raw.githubusercontent.com/NetBSD/src/trunk/games/rogue/level.c
- https://www.nethack.org/common/license.html
- https://github.com/facebookresearch/nle
- https://en.wikipedia.org/wiki/Rogue_(video_game)

## Recommendation Set

### First Recommendation: Find A License-Clear Modern Linux Rogue Port

Reason: this best matches the priority list if a concrete source tree has clear license text, Linux build steps, and original Rogue rules.

Pros:

- Lower porting cost than exact historical code.
- Likely easier to build and test on the mini PC.
- May already have portability fixes.

Cons:

- A suitable candidate has not yet been verified.
- It may diverge from Berkeley Rogue 4.22 and prior assets.

License caution: no source may be imported until `LICENSE`, `COPYING`, `README`, source headers, and distribution notes have been inspected.

Implementation impact: medium; likely less work than 4.22 if build tooling is current.

### Second Recommendation: NetBSD `games/rogue` After License Review

Reason: the source is inspectable, maintained, has Rogue amulet mechanics, and exposes useful RNG and state boundaries.

Pros:

- Concrete source tree.
- Modern maintained BSD source.
- Amulet and return mechanics are present.
- RNG functions are identifiable.

Cons:

- Curses is embedded.
- It is not the same as the suspected Berkeley 4.22 past code.
- Header text contains an older noncommercial/profit restriction that conflicts with simple permissive-license assumptions.

License caution: treat as blocked until legal review resolves the BSD-style notice plus older Rogue restriction.

Implementation impact: medium to high; likely feasible, but display separation and command-loop refactoring are real work.

### Past-Assets Priority: Locate And Verify Berkeley Rogue 4.22

Reason: if prior work used `Rogue v4.22 (Berkeley 02/05/99)`, this has the best chance of reusing existing patches, logs, 4K display work, and 64x160 assumptions.

Pros:

- Highest likely compatibility with prior project assets.
- Best option for reapplying old screen-size and controller work.
- Most direct path if old source and patches are found.

Cons:

- No verified source tree has been inspected yet.
- License is unknown.
- Build and portability status are unknown.
- Headless conversion may be harder than with a maintained port.

License caution: License status: Unverified. Repository inclusion: Prohibited until verified.

Implementation impact: low to medium if past patches are found and build cleanly; high if only an old unpatched source dump exists.

## Shinoda Decision Items

- Locate the exact Berkeley Rogue 4.22 source tree used in prior work, if any.
- Decide whether commercial-use clarity is required before any source import.
- Decide whether compatibility with past 4.22 assets outweighs starting from a maintained source tree.
- Decide whether a from-scratch engine is acceptable if all historical source candidates remain license-blocked.
- Decide whether the first implementation should prioritize headless API cleanliness over exact historical behavior.

## Required Next Steps

- Identify concrete 5.x and 3.x Rogue source distributions.
- For each candidate, inspect `LICENSE`, `COPYING`, `README`, source headers, and distribution-site license notes.
- Build each viable candidate on modern Ubuntu or the mini PC.
- Confirm Amulet of Yendor placement and return-to-surface rules.
- Confirm whether RNG seed can be fixed.
- Prototype a minimal `reset` / `step` boundary without copying unverified code into this repository.
