# Runtime Reference Implementation

This package contains the Python reference implementation of the NaMMA
Runtime Contract.

The Phase 7 core runtime remains domain-independent. Phase 8 adds a Rogue
adapter skeleton that is exercised only through a Fake Rogue Native Backend.
Phase 9 adds a ctypes-backed native bootstrap backend while keeping Rogue
gameplay, headless control, and AI integration out of scope.

Implemented in Phase 7:

- RuntimeState and EpisodeOutcome.
- DomainAdapter Protocol.
- DecisionProvider Protocol.
- Action and observation dataclasses.
- DeterminismContext.
- Replay Level 1 in-memory recording.
- Fake Domain.
- Fake DecisionProviders.
- Synchronous Runtime Orchestrator.

Action lifecycle rules:

- A RequestedAction becomes an ExecutedAction only after validation accepts it.
- Schema and observable-rule validation rejection fault the Phase 7 Runtime.
- Rejected actions are not written to Replay Level 1.
- In-domain action failure is still an executed action and is recorded.
- RuntimeOrchestrator instances are one-shot in Phase 7.

Not implemented in Phase 7:

- RogueDomainAdapter.
- Rogue reset or step.
- Curses separation.
- Local AI.
- NaMMA.
- Ethernet, OCuLink, or PCIe.
- GUI or viewer.
- Multi-agent, async, streaming, or batch execution.

Added in Phase 8:

- `runtime.rogue.RogueDomainAdapter`.
- `runtime.rogue.RogueNativeBackend` Protocol.
- `runtime.rogue.FakeRogueNativeBackend`.
- Rogue-specific semantic action and observation models.
- Replay Level 1 tests through the Rogue adapter path.

Phase 8 Rogue contract choices:

- only the Fake Rogue Native Backend is implemented,
- the real C backend is not implemented,
- reset returns reset status only,
- the adapter explicitly observes and reads source identity after reset,
- native observation carries one recent message,
- available action types are adapter-supplied static capability data,
- the native ABI is host in-process only and is separate from any future
  NaMMA transport.

Still not implemented at the end of Phase 8:

- real Rogue native backend loading,
- Rogue reset or step in C,
- curses separation,
- `ctypes.CDLL` integration,
- Local AI,
- NaMMA.

Added in Phase 9:

- `runtime.rogue.CtypesRogueNativeBackend`,
- a native C bootstrap library loaded through ctypes,
- ABI version checks with major rejection and minor compatibility,
- distinct native load, ABI, symbol, lifecycle, observe, action, and close
  errors,
- real native `WAIT` and `QUIT` bootstrap tests.

Still not implemented after Phase 9 bootstrap:

- Rogue game-code modification,
- headless Rogue,
- `step()`,
- `MOVE`,
- inventory, combat, map, monster, or item extraction,
- Local AI,
- NaMMA.
