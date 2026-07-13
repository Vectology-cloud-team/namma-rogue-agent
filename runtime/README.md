# Runtime Reference Implementation

This package is the Phase 7 Python reference implementation of the
NaMMA Runtime Contract.

It is intentionally independent from Rogue 5.4.4.

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
