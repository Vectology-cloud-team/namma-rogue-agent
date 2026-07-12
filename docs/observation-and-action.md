# Observation And Action Schema

All schemas must include a `schema_version`. Breaking changes require a version bump and migration notes.

## Objective Phase

Initial objective phases:

- `DESCEND`
- `FIND_AMULET`
- `ASCEND`
- `RETURNED_WITH_AMULET`
- `DEAD`
- `FAILED`

After the amulet is obtained, the objective should switch automatically from exploration to return.

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

Inventory references should use stable item IDs assigned inside the episode. The agent should not depend on display text alone.

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

## Observation Fields

Minimum observation fields:

- `schema_version`
- `episode_id`
- `turn`
- `seed`
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
- `objective_phase`
- `has_amulet`
- `visible_map`
- `known_map`
- `visible_monsters`
- `visible_items`
- `inventory`
- `equipment`
- `recent_messages`
- `legal_actions`
- `terminal`
- `terminal_reason`
- `score`

## Map Representation

Keep two map views:

- `visible_map`: currently visible cells.
- `known_map`: cells remembered by the episode.

The known map may include stale information. The observation should make that clear where needed.

## Legal Actions

Every turn should include `legal_actions`. The environment must reject actions not present in this list or actions that fail schema validation.
