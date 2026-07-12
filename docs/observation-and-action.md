# Observation And Action Schema

All schemas must include a `schema_version`. Breaking changes require a
version bump and migration notes.

## Objective Phase

Initial objective phases:

- `DESCEND`
- `FIND_AMULET`
- `ASCEND`
- `RETURNED_WITH_AMULET`
- `DEAD`
- `FAILED`

After the amulet is obtained, the objective should switch automatically
from exploration to return.

## Responsibility Boundary

The environment provides the agent with an `AgentObservation` for the
current turn. This observation contains only what the player can
currently perceive, plus player state, inventory, equipment, recent
messages, and action grammar information.

The agent owns `EpisodeMemory`. It builds memory from the stream of past
observations and action results. The environment must not provide
agent-facing remembered maps as if they were current game state.

If debugging, validation, or replay generation needs complete internal
game state, define it separately as `PrivilegedDebugState`.
`PrivilegedDebugState` is not input to normal agents, AI planners, or
NaMMA inference.

## AgentObservation Fields

Minimum `AgentObservation` fields:

- `schema_version`
- `episode_id`
- `turn`
- `seed`
- `dungeon_level`
- `objective_phase`
- `player_position`
- `hp`
- `hp_max`
- `strength`
- `armor`
- `experience`
- `gold`
- `hunger`
- `status_effects`
- `has_amulet`
- `visible_map_cells`
- `visible_monsters`
- `visible_items`
- `inventory`
- `equipment`
- `recent_messages`
- `observable_legal_actions`
- `terminal`
- `terminal_reason`
- `score`

The observation may include player-recognizable state such as blindness,
hallucination, levitation, confusion, hunger state, equipment identity
known to the player, and item labels known to the player.

The observation must not include hidden traps, undiscovered secret doors,
unseen monsters, full dungeon layout, future random outcomes, or the
agent's remembered `known_map`.

## Agent Episode Memory

The agent may maintain `EpisodeMemory` derived from observations and
action results. Example fields:

- `known_map`
- `visited_cells`
- `known_stairs`
- `exploration_frontiers`
- `previously_observed_monsters`
- `previously_observed_items`
- `level_history`
- `current_plan`
- `failed_targets`
- `loop_history`

`known_map` belongs here, not in the environment's normal agent
observation. It may be stale and must be updated from new observations.

## PrivilegedDebugState

`PrivilegedDebugState` is optional and separate from `AgentObservation`.
It is intended for tests, replay generation, invariant checking, and
debugging.

It may contain complete internal information such as:

- full dungeon map,
- hidden traps,
- secret doors,
- all monsters,
- all items,
- raw random generator state,
- engine-only flags,
- exact object identities not yet known to the player.

Normal agents, AI planners, local models, and NaMMA providers must not
receive `PrivilegedDebugState`.

## Action Types

Initial semantic actions:

- `move`
- `wait`
- `attack`
- `open`
- `close`
- `search`
- `pickup`
- `drop`
- `eat`
- `drink`
- `read`
- `equip`
- `unequip`
- `throw`
- `use_item`
- `descend`
- `ascend`
- `cancel`

Movement directions should be an enum:

- `N`
- `NE`
- `E`
- `SE`
- `S`
- `SW`
- `W`
- `NW`

Inventory references should use stable item IDs assigned inside the
episode. The agent should not depend on display text alone.

## Action Example

```json
{
  "schema_version": "0.1",
  "type": "move",
  "direction": "N"
}
```

## Planner Output Example

```json
{
  "schema_version": "0.1",
  "goal": "explore_current_level",
  "target": {
    "type": "unexplored_frontier",
    "x": 52,
    "y": 18
  },
  "combat_policy": "avoid_when_hp_below_40_percent",
  "replan_when": [
    "enemy_seen",
    "target_reached",
    "hp_below_30_percent",
    "new_item_acquired"
  ]
}
```

## Legal Actions And Hidden Information

`legal_actions` must not leak hidden game state. Initial designs may use
the name `observable_legal_actions` to make that boundary explicit.

Observable legal actions are generated from:

- currently observable player state,
- currently visible map cells,
- currently visible monsters and items,
- current inventory and equipment,
- known input grammar,
- action schema rules.

Observable legal actions must not reveal:

- undiscovered traps,
- hidden doors,
- unseen monsters,
- unidentified item truth,
- future combat or random outcomes,
- full map topology.

It is acceptable for a game-rule action to fail after execution. For
example, a player may search and find nothing, try to move into something
that turns out to block movement, or attempt an action whose outcome is
unknown until tried.

Distinguish these concepts:

- `syntactically_valid_actions`: actions that match the schema and input
  grammar.
- `observable_legal_actions`: actions that appear currently available
  from observable information.
- `action_result`: the outcome after the environment attempts an action.

Action validation must reject malformed or schema-invalid actions without
revealing future information or hidden state. A failed in-game attempt
should be reported through `action_result`, not by leaking hidden facts
before execution.
