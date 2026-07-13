# Runtime Sequence

This document describes the expected high-level runtime sequence. It is
design only and does not implement runtime code.

## Episode Sequence

```mermaid
sequenceDiagram
    participant User
    participant Runtime
    participant Env as Environment
    participant Obs as Observation Builder
    participant Mem as Episode Memory
    participant Rep as Replay Recorder
    participant Plan as Planner
    participant Exec as Action Executor
    participant Prov as Provider
    participant Core as Game Core

    User->>Runtime: start episode
    Runtime->>Env: initialize with seeds
    Env->>Core: initialize domain state
    Core-->>Env: initial game state
    Env->>Obs: build observation
    Obs-->>Env: AgentObservation
    Env-->>Runtime: initial observation
    Runtime->>Rep: record metadata and seed block

    loop each turn
        Runtime->>Mem: update from observation
        Runtime->>Plan: observation + memory
        Plan->>Prov: provider request
        Prov-->>Plan: provider response
        Plan->>Exec: requested action or plan
        Exec-->>Runtime: validated action
        Runtime->>Env: execute action
        Env->>Core: executed action
        Core-->>Env: game state + events
        Env->>Obs: build next observation
        Obs-->>Env: AgentObservation
        Env-->>Runtime: ActionResult + observation
        Runtime->>Rep: record turn
    end

    Runtime->>Rep: record terminal summary
    Runtime-->>User: episode summary
```

## Turn Sequence

One turn should have these logical phases:

1. Receive current observation.
2. Update episode memory.
3. Build provider request.
4. Wait for provider response or timeout.
5. Convert provider output to requested action or plan.
6. Validate requested action.
7. Execute validated action.
8. Build action result and next observation.
9. Record replay data.
10. Check terminal state.

## Provider Timeout Sequence

```mermaid
sequenceDiagram
    participant Runtime
    participant Planner
    participant Provider
    participant Executor

    Runtime->>Planner: observation, memory, and budget
    Planner->>Provider: request with timeout
    Provider--xPlanner: timeout
    Planner-->>Runtime: provider error
    Runtime->>Executor: fallback policy if configured
    Executor-->>Runtime: fallback action or no action
```

Timeout handling must be explicit. The runtime should not silently reuse
an old provider response unless that is a configured fallback policy and
is recorded in replay.

## Replay Sequence

Replay provider mode:

1. Load replay metadata.
2. Verify runtime and configuration compatibility.
3. Reconstruct seed plan.
4. Feed recorded actions or provider responses through the same provider
   interface.
5. Compare observations, hashes, and terminal result.
6. Report first divergence.

Replay must use the same Action Executor boundary as live operation.

## Pause And Resume Sequence

Pause:

- Finish current atomic runtime operation.
- Stop accepting new provider requests.
- Flush replay writer.
- Enter `PAUSED`.

Resume:

- Confirm provider availability if needed.
- Re-enter `RUNNING`.
- Continue from the next turn boundary.

The runtime should not pause halfway through a domain state mutation.

## Sequence Open Questions

- Should provider requests be synchronous first, or should async be
  required from the start?
- Should replay compare every observation or only hashes by default?
- Should the runtime allow speculative provider requests?
- How should real robot emergency stop integrate with `PAUSED` and
  `FAILED`?
