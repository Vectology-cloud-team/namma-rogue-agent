# Rogue Observation Boundary

Phase 8 defines the Rogue observation boundary without extracting Rogue 5.4.4
game state from C yet.

## Terms

`RogueDomainState`:

- authoritative Rogue-owned state,
- includes hidden and future-relevant information,
- remains inside the C domain or Native Backend,
- is not sent to normal DecisionProvider calls.

`RogueAgentObservation`:

- player-observable information produced for Runtime decisions,
- hides secret and off-screen state,
- is JSON-compatible in the Python reference skeleton,
- is versioned separately from Rogue internal structures.

`RoguePrivilegedDebugState`:

- diagnostic state for tests, replay verification, and debugging,
- may include hidden map, hidden monsters, RNG checksum, and other internals,
- must not be delivered to normal Human, RuleBased, LLM, or NaMMA providers.

`RogueEpisodeMemory`:

- agent-owned memory built from observations and action results,
- may include known map, visited cells, prior messages, and current plan,
- is not authoritative Rogue state.

## Agent Observation Draft

Candidate fields:

- `schema_version`
- `dungeon_level`
- `player_position`
- `hp`
- `hp_max`
- `strength`
- `armor`
- `experience`
- `gold`
- `hunger`
- `status_effects`
- `visible_cells`
- `visible_monsters`
- `visible_items`
- `inventory`
- `equipment`
- `recent_message`
- `terminal`
- `terminal_reason`

Phase 9 should start smaller:

1. `schema_version`
2. `dungeon_level`
3. `player_position`
4. `hp`
5. `hp_max`
6. `visible_cells`
7. `recent_message`
8. `turn`
9. `terminal`
10. `terminal_reason`

## Hidden-State Classification

| Item | Classification | Notes |
| --- | --- | --- |
| Current visible terrain | Agent observable | Derived from visible map cells |
| Player HP | Agent observable | Already visible in status |
| Current inventory names | Agent observable | Use player-facing names, not raw identity flags |
| Known map | Remembered by agent | Built from prior observations |
| Visited cells | Remembered by agent | Episode Memory owns this |
| Previously seen monsters | Remembered by agent | May become stale |
| Current off-screen monsters | Privileged debug only | Do not expose to DecisionProvider |
| Hidden traps | Privileged debug only | Can be visible after discovery |
| Secret doors | Privileged debug only | Until discovery |
| Unidentified item true type | Privileged debug only | Do not bypass identification |
| RNG seed and future rolls | Never exposed | May be used for replay verification only |
| Raw Rogue pointers | Never exposed | ABI must not leak them |
| Curses `WINDOW *` | Never exposed | UI implementation detail |

## Observation Suitability By Source

| Source | Agent observation use | Risk |
| --- | --- | --- |
| `player.t_pos` | Yes | Coordinate convention must be stable |
| `player.t_stats` | Yes | Avoid exposing non-visible status details |
| `places[]` | Visible subset only | Hidden flags and undiscovered cells |
| `rooms[]` and `passages[]` | Debug or derived visible cells | Reveals map topology |
| `mlist` | Visible monsters only | Off-screen leakage |
| `lvl_obj` | Visible items only | Off-screen leakage and identity leakage |
| `huh` and message buffers | One recent message initially | UI wording stability |
| `seed` and `dnum` | Replay debug only | Future information |

## Phase 8 Native Observation Contract

Phase 8 uses the smaller contract that should seed Phase 9:

- the native observation carries a single `recent_message`,
- the native observation carries a `turn` counter for the bootstrap profile,
- available action types are not carried in the C ABI observation,
- `RogueDomainAdapter` supplies available action types from static capability
  data,
- visible cells remain the only variable-length observation array in the
  initial native ABI draft.

## Replay Relationship

Replay Level 1 should record executed semantic actions and deterministic
checksums. Full privileged state may be used to compare fake backend behavior
in tests, but Level 1 should not require every hidden Rogue field.

The same seed and action sequence must produce the same replay checksum when
the source identity and build identity match.
