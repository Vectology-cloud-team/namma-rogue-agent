# Native Bootstrap

This directory contains the Phase 9 native-library bootstrap for the Rogue
runtime boundary.

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
- validate and apply `WAIT` and `QUIT`.

It does not:

- modify Rogue 5.4.4 source,
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
