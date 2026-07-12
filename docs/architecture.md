# System Architecture

## Layer 1: Rogue Engine

The Rogue engine owns the game rules:

- dungeon generation,
- player state,
- monsters,
- combat,
- inventory,
- item effects,
- traps,
- amulet,
- victory and death,
- random number generation.

The engine must not depend on HTTP, Python-specific runtime behavior,
LLM providers, NaMMA providers, or curses. It may expose a narrow API
that the environment layer can call.

## Layer 2: Rogue Environment

The environment turns the engine into a headless evaluation target:

- `reset`,
- `step`,
- seed selection,
- action validation,
- observation generation,
- legal action generation,
- episode management,
- replay recording,
- snapshotting,
- terminal-state reporting.

The environment is the only layer that should expose current observable
game state to the agent.

The environment may also expose a separate `PrivilegedDebugState` for
debugging, validation, and replay generation. Normal agents and AI
planners must not receive that privileged state.

## Layer 3: Agent

The agent decides what to do next. It is split into:

- Planner: local AI or NaMMA produces a high-level plan.
- Deterministic Executor: normal program code turns the plan into legal one-turn actions.
- Validator: rejects malformed, unsafe, or impossible actions.
- Episode Memory: builds remembered knowledge from past observations,
  including known maps, visited cells, known stairs, exploration
  frontiers, failed targets, loop history, plans, actions, and outcomes.
- Retry Manager: starts the next episode after terminal failure.

The planner should not emit raw Rogue keypresses. It should emit
structured plans or semantic actions.

## Layer 4: Viewer

The viewer presents the environment state for humans:

- ASCII display,
- debug panels,
- replay playback,
- explanation of what the AI considered.

The viewer must use environment output and replay data. It should not inspect private engine internals.

## Control Flow

```text
Rogue Engine -> Rogue Environment -> Agent -> validated action -> Rogue Environment -> Rogue Engine
                                      |
                                      `-> Viewer / Replay
```

## Reproducibility Boundary

The deterministic boundary is:

- Rogue implementation version,
- repository commit,
- seed,
- configuration,
- action sequence.

Given the same boundary inputs, dungeon generation, combat outcomes, player state, and terminal result should match.
