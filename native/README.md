# Native Bootstrap

This directory contains the Phase 9A native ABI bootstrap stub for the Rogue
runtime boundary. It is a ctypes-to-C connection proof, not a link to the
Rogue 5.4.4 game code.

The bootstrap library implements the `namma_rogue_*` C ABI declared in:

```text
adapter/native/include/namma_rogue_api.h
```

It is intentionally minimal:

- create and destroy an opaque native handle,
- reset the native handle,
- observe `recent_message`, `terminal`, and `turn`,
- report source identity,
- report terminal status,
- validate and apply `WAIT` and `QUIT` stub actions.

It does not:

- modify Rogue 5.4.4 source,
- call Rogue 5.4.4 `command()`, `playit()`, or `readchar()`,
- implement headless Rogue,
- implement `step()`,
- execute Rogue combat, inventory, monsters, or map generation,
- connect Local AI or NaMMA.

## Linux Build

Ubuntu 24.04 example:

```sh
cc -shared -fPIC -Wall -Wextra -Werror \
  -Iadapter/native/include \
  native/rogue_native_bootstrap.c \
  -o build/libnamma_rogue_bootstrap.so
```

The Python backend loads the resulting library with
`runtime.rogue.CtypesRogueNativeBackend`.

## Handle Release

`namma_rogue_destroy()` releases the opaque handle and returns `void`. It has
no recoverable failure status and must not be called twice for the same active
handle.

The diagnostic wrappers `rogue_destroy()` and `rogue_close()` both delegate to
`namma_rogue_destroy()`. Use only one spelling for a given handle. The Python
backend uses `namma_rogue_destroy()` only; the wrappers are diagnostic
compatibility exports and future deletion candidates.

## Diagnostic Checksum

The stub debug checksum is a deterministic XOR-based diagnostic value. It only
proves that deterministic values can cross the ABI. A Rogue-backed
implementation must replace it with a canonical state digest such as SHA-256
or an equivalently specified algorithm.
