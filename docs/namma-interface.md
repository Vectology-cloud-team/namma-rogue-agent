# NaMMA Interface

NaMMA should be exposed through the same application-level provider
interface as other local AI backends. Ethernet and OCuLink should differ
below that interface, not in agent planning logic.

NaMMA receives normal `AgentObservation` and planner context. It must not
receive `PrivilegedDebugState` or hidden engine state.

## Common Request

The common request should include:

- request ID,
- schema version,
- model or accelerator identifier,
- prompt or structured task,
- compact observation summary,
- legal action summary,
- inference parameters,
- timeout budget,
- replay metadata.

## Common Response

The common response should include:

- request ID,
- schema version,
- status,
- plan or semantic action,
- confidence or diagnostics when available,
- token or cycle accounting when available,
- latency,
- error information.

## Ethernet Candidates

Candidate protocols:

- HTTP JSON,
- OpenAI-compatible API,
- custom REST API,
- gRPC,
- custom TCP binary protocol.

Recommendation for first integration: start with HTTP JSON or an
OpenAI-compatible API so that the agent can share tooling with
`llama.cpp` and other local providers.

## OCuLink / PCI Express Direction

OCuLink should be treated as a PCI Express connection. Future design should consider:

- PCIe BAR mapping,
- DMA,
- request ring,
- completion ring,
- doorbell,
- interrupt,
- polling mode,
- shared buffers,
- memory ownership,
- timeout and reset behavior.

No OCuLink driver implementation is planned in the initial phase.

## Open Questions

- What is the smallest NaMMA request that can produce useful plans?
- Should NaMMA receive full observations or compressed tactical summaries?
- What latency target is acceptable per planning request?
- How will hardware errors be surfaced to the agent?
- Can Ethernet and OCuLink share exactly the same serialization format?
