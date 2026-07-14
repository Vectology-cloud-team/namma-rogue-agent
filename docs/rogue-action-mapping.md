# Rogue Action Mapping

Phase 8 defines semantic Rogue actions for the Runtime boundary. It does not
make raw Rogue key codes the public API.

## Action Lifecycle

The Runtime distinguishes:

`RequestedAction`:

- produced by a DecisionProvider,
- may be invalid,
- belongs to the Runtime contract.

`ValidatedAction`:

- accepted or rejected by the DomainAdapter,
- must not reveal hidden state,
- may normalize direction or parameters.
- maps to the C ABI `namma_rogue_validation_status_t` values:
  `VALID`, `REJECTED_SCHEMA`, and `REJECTED_OBSERVABLE_RULE`.

`ExecutedAction`:

- only exists after validation accepted the request,
- is recorded in Replay Level 1,
- may still fail inside the domain.

`ActionResult`:

- records success, in-domain failure, terminal status, or error result,
- is returned to the Runtime.

## Semantic Rogue Actions

Draft action types:

- `MOVE`
- `WAIT`
- `SEARCH`
- `OPEN`
- `CLOSE`
- `PICKUP`
- `DROP`
- `EAT`
- `DRINK`
- `READ`
- `WIELD`
- `WEAR`
- `REMOVE`
- `THROW`
- `DESCEND`
- `ASCEND`
- `QUIT`

Draft directions:

- `N`
- `NE`
- `E`
- `SE`
- `S`
- `SW`
- `W`
- `NW`
- `NONE`

Phase 9 should begin with:

- `WAIT`
- `QUIT`

The Phase 9 real native bootstrap supports only `WAIT` and `QUIT`. `MOVE`
remains available in the fake backend for adapter-boundary tests but is not
advertised by `CtypesRogueNativeBackend`.

## Mapping To Existing Rogue Commands

| Semantic action | Rogue command path | Notes |
| --- | --- | --- |
| `MOVE N` | `k` then `command.c::do_move(-1, 0)` | Existing movement logic |
| `MOVE NE` | `u` then `do_move(-1, 1)` | Existing diagonal logic |
| `MOVE E` | `l` then `do_move(0, 1)` | Existing movement logic |
| `MOVE SE` | `n` then `do_move(1, 1)` | Existing diagonal logic |
| `MOVE S` | `j` then `do_move(1, 0)` | Existing movement logic |
| `MOVE SW` | `b` then `do_move(1, -1)` | Existing diagonal logic |
| `MOVE W` | `h` then `do_move(0, -1)` | Existing movement logic |
| `MOVE NW` | `y` then `do_move(-1, -1)` | Existing diagonal logic |
| `WAIT` | `.` | Rest command |
| `QUIT` | `Q` plus confirmation policy | Must not allow interactive prompt in ABI |

Future actions such as `DROP`, `THROW`, `READ`, and `ZAP` may require extra
parameters and multi-key command sequences. They are deliberately deferred.

## Validation Without Hidden Leakage

Validation may check:

- action type exists,
- direction is valid for actions requiring direction,
- required item slot or parameter is present,
- backend is not terminal or closed,
- command is supported by the current backend capability set.

Validation must not reveal:

- hidden traps,
- secret doors,
- off-screen monsters,
- unseen items,
- future random outcomes,
- whether an apparently legal move will later fail because of hidden state.

It is acceptable for a syntactically valid action to fail after execution.
For example, moving into a wall or trying an unavailable interaction can be an
executed in-domain failure.

Function-call status and action-validation status are separate. Native ABI
functions return `namma_rogue_status_t` for ABI call success or failure. The
validated action structure uses `namma_rogue_validation_status_t` for
observable validation results.

## Phase 8 Adapter Contract

The Phase 8 Python `RogueDomainAdapter` must:

- accept the Runtime `RequestedAction`,
- reject unsupported actions before backend application,
- delegate supported actions to `RogueNativeBackend`,
- preserve in-domain failure as an executed action,
- convert terminal success, loss, and abort into `EpisodeOutcome`,
- avoid exposing `RoguePrivilegedDebugState` in normal observations.
