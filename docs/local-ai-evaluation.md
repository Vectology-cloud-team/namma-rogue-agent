# Local AI Evaluation

## Initial Direction

The first implementation should use a provider abstraction compatible
with OpenAI-style request/response patterns. `llama.cpp` is the first
expected local backend, but the agent must not depend on a single
inference server.

## Provider Interface

```python
class InferenceProvider(Protocol):
    def infer(
        self,
        request: InferenceRequest,
    ) -> InferenceResponse:
        ...
```

Initial provider candidates:

- `LlamaCppProvider`
- `OllamaProvider`
- `VllmProvider`
- `ReplayProvider`
- `NammaEtherProvider`
- `NammaOculinkProvider`

## Planner And Executor Split

The AI planner should decide:

- current goal,
- exploration target,
- combat policy,
- item-use policy,
- trap-avoidance preference,
- return-to-surface trigger,
- replanning conditions.

The planner receives `AgentObservation` plus the agent's own
`EpisodeMemory`. It must not receive `PrivilegedDebugState`.

The deterministic executor should handle:

- pathfinding,
- A* or equivalent movement planning,
- wall collision avoidance,
- visited-cell management,
- loop detection,
- conversion to one-turn semantic actions,
- rejection of impossible actions.

The AI should not be asked to decide every single movement key when
deterministic code has enough information.

## Baseline Before AI

Before local AI integration, build a rule-based bot that can run many
episodes without human input. Initial acceptance criteria:

- run 1000 unattended episodes,
- no crashes,
- no major memory growth,
- save per-episode results,
- replay at least one seed,
- reject illegal actions without corrupting state.
