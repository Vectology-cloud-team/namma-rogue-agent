# Risks And Open Questions

## Technical Risks

- Rogue source license may be unclear.
- The local Rogue 5.4.4 / rogueforge tree has promising license text but
  remains blocked until local modification ownership and source
  completeness are verified.
- The local Rogue 5.4.4 / rogueforge tree currently fails to build
  unchanged because build files reference `new_level.c`, which was not
  found in the local tree.
- The `phs/rogue` Rogue 5.4.4 baseline contains `new_level.c`, but its
  modern Ubuntu build is still blocked by generated-script CRLF and
  ncurses `WINDOW` compatibility issues.
- The Rogueforge Rogue 5.4.4 source archive has now been recovered,
  hash-fixed, and imported as a pristine baseline.
- The Phase 5 patched tree builds and launches with gcc on Ubuntu 24.04,
  but clang remains unverified because it is not installed on the probe
  host.
- The pristine upstream tree and patched development tree must remain
  separate.
- Local Rogue 5.4.4 modifications are concentrated in logging,
  controller, seed, and death-reporting paths, but authorship and reuse
  rights are not verified.
- Legacy local modifications should be preserved as evidence, not
  directly merged into the future source tree.
- The chosen engine may be hard to make deterministic.
- Curses or terminal UI coupling may make headless control expensive.
- Screen scraping can be brittle and should not be the primary interface.
- Local AI latency may be too high for per-turn inference.
- Planner output may be invalid or unsafe without strict validation.
- Replay data may be insufficient if random state is not captured.
- NaMMA Ethernet and OCuLink may diverge unless a shared application interface is defined early.
- OCuLink driver work is likely high-risk and should be delayed until the agent/environment boundary is stable.

## Product And Research Risks

- Original Rogue may be simpler than desired but easier to control.
- NetHack/NLE has strong research precedent, but it must remain reference
  material only and must not become a target-game candidate.
- Agent-facing observations or legal actions could accidentally reveal
  hidden state if privileged debug data is not kept separate.
- A local model may not reliably plan long-horizon dungeon strategy without a deterministic executor and memory.
- Rule-based baselines may outperform early neural planners; this is useful and should be measured rather than hidden.

## Open Questions

- Should `patches/0001-ncurses-compatibility.patch` be accepted as the
  initial Ubuntu 24.04 compatibility patch?
- What clang package/version should be used for the pending clang build
  matrix entry?
- Is the `main.c 4.22 (Berkeley) 02/05/99` evidence only a file-level
  revision tag, or does an exact prior Berkeley Rogue 4.22 distribution
  still exist locally?
- Which Rogue implementation best balances original behavior, license clarity, and headless API work?
- What license will this repository use?
- What is the minimum acceptable observation for NaMMA?
- How much episode memory should be included in each planning request?
- Should replay store full observations or hashes plus periodic snapshots?
- What are the latency targets for mini PC local AI and NaMMA?
- What parts of existing assets, if any, can be reused safely?

## Immediate Recommendation

Keep the Phase 5 scope narrow until the compatibility PR is reviewed.
Do not begin headless, reset/step, replay, Agent, NaMMA, or 64x160 work
from this branch.

Rogueforge Rogue 5.4.4 is the fixed upstream Golden Baseline. The
current source task is reviewing the minimal ncurses compatibility patch
managed separately from the pristine upstream source.
