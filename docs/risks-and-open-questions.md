# Risks And Open Questions

## Technical Risks

- Rogue source license may be unclear.
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
- NetHack/NLE has strong research precedent but may drift from the explicit Rogue target.
- A local model may not reliably plan long-horizon dungeon strategy without a deterministic executor and memory.
- Rule-based baselines may outperform early neural planners; this is useful and should be measured rather than hidden.

## Open Questions

- Which exact Rogue implementation should be used?
- Is original Rogue behavior required, or is a compatible Rogue-like acceptable?
- What license will this repository use?
- What is the minimum acceptable observation for NaMMA?
- How much episode memory should be included in each planning request?
- Should replay store full observations or hashes plus periodic snapshots?
- What are the latency targets for mini PC local AI and NaMMA?
- What parts of existing assets, if any, can be reused safely?

## Immediate Recommendation

Start with source selection and deterministic headless boundaries before any AI integration. Do not import Rogue source until the license review is complete.
