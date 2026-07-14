# Native Backend Bootstrap

Phase 9 adds the first real native-library connection for the Rogue runtime
boundary. It replaces the Python-only fake native backend with a ctypes-loaded
C library for the smallest lifecycle path.

## Scope

Implemented:

- `runtime/rogue/native_backend.py`
- `native/rogue_native_bootstrap.c`
- tests that build and load the native library when a C compiler is available
- Runtime -> RogueDomainAdapter -> CtypesRogueNativeBackend -> C ABI tests

Not implemented:

- Rogue 5.4.4 game-code modification
- headless Rogue
- `step()`
- `MOVE`
- inventory, combat, monsters, items, or visible map extraction
- Replay Level 2 or Level 3
- Local AI, LLM, NaMMA, Ethernet, OCuLink, or PCIe

## Native Library Contract

The bootstrap library implements the existing `namma_rogue_*` ABI names:

- `namma_rogue_abi_version`
- `namma_rogue_create`
- `namma_rogue_reset`
- `namma_rogue_observe`
- `namma_rogue_validate_action`
- `namma_rogue_apply_action`
- `namma_rogue_terminal_status`
- `namma_rogue_debug_state`
- `namma_rogue_source_identity`
- `namma_rogue_destroy`

Compatibility wrappers named `rogue_create`, `rogue_destroy`, `rogue_reset`,
`rogue_observe`, `rogue_terminal_status`, `rogue_source_identity`, and
`rogue_close` are exported by the bootstrap C file for early diagnostics, but
the Python backend uses the `namma_rogue_*` ABI.

## ABI Versioning

The Phase 9 bootstrap uses ABI major `0` and minor `2`.

The Python backend rejects:

- libraries whose ABI major differs,
- libraries whose ABI minor is older than the required bootstrap minor.

Newer minor versions are accepted within the same major version.

## Observation

The bootstrap observation intentionally exposes only:

- `recent_message`
- `terminal`
- `terminal_reason`
- `turn`

The C ABI struct still contains placeholders inherited from the Phase 8
contract, such as player position, HP, and visible cells, but the bootstrap
library returns neutral values and an empty visible-cell array. Real Rogue map,
inventory, monster, item, and status extraction remain future work.

## Actions

Supported through the real native backend:

- `WAIT`
- `QUIT`

`MOVE` remains intentionally unsupported in Phase 9 bootstrap. The fake
backend may still exercise `MOVE` for adapter-boundary tests, but the real
ctypes backend advertises only `WAIT` and `QUIT` through its
`RogueNativeConfig`.

## Errors

The Python backend distinguishes:

- library load failure,
- ABI version mismatch,
- missing native symbol,
- create failure,
- reset failure,
- observe failure,
- source identity failure,
- terminal status failure,
- action failure,
- close failure.

These are all `DomainAdapterError` subclasses so the Runtime can fault safely
without treating native backend failures as Rogue domain terminal outcomes.

## Build

Ubuntu 24.04 example:

```sh
cc -shared -fPIC -Wall -Wextra -Werror \
  -Iadapter/native/include \
  native/rogue_native_bootstrap.c \
  -o build/libnamma_rogue_bootstrap.so
```

The tests compile an equivalent temporary shared library when `gcc` or `cc` is
available.

## Boundary

This PR is a safe connection bootstrap. It proves that Runtime can call a real
native library through the Rogue ABI. It does not yet prove that Rogue gameplay
can be controlled by an AI.
