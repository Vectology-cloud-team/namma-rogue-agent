# License Review Notes

This file tracks license evidence gathered during source selection. It
is not legal advice and does not grant repository inclusion.

## Review Policy

Before any Rogue source is copied into this repository, inspect:

- `LICENSE`
- `COPYING`
- `README`
- source headers
- distribution-site license notes
- provenance of local modifications

If a candidate's license cannot be verified, record:

```text
License status: Unverified
Repository inclusion: Prohibited until verified
```

## Local Rogue 5.4.4 / rogueforge 09/05/07 Tree

Evidence inspected:

- `%USERPROFILE%\Downloads\rogue\LICENSE.TXT`
- source headers in local `.c` and `.h` files
- `vers.c`
- build files referencing distribution packaging

License evidence:

- `LICENSE.TXT` contains BSD-style redistribution and binary
  redistribution permissions for the Toy, Arnold, and Wichman portions.
- `LICENSE.TXT` contains separate BSD-style terms for Nicholas J.
  Kisseberth portions.
- `LICENSE.TXT` contains separate BSD-style terms for David Burren
  `xcrypt.c` portions.
- Most source headers refer to `LICENSE.TXT`.

Current status:

```text
License status: Partially verified upstream text, local provenance unverified
Repository inclusion: Prohibited until verified
```

Reason for blocking:

- The exact upstream archive has not been verified.
- Local modifications, including logging hooks and possible screen-size
  changes, have not been attributed.
- Loose adjacent fragments may not be covered by the same complete
  source tree.

## NetBSD `games/rogue`

Evidence inspected:

- selected source headers from NetBSD `src/games/rogue`
- NetBSD repository path:
  https://github.com/NetBSD/src/tree/trunk/games/rogue

License evidence:

- Headers include Regents of the University of California BSD-style
  redistribution text.
- The same inspected files also retain older Rogue text that restricts
  trading, sale, or use for personal gain or profit.

Current status:

```text
License status: Ambiguous
Repository inclusion: Prohibited until reviewed
```

Reason for blocking:

- The old restriction text may conflict with the intended project use.
- A legal review is required before import, redistribution, modification,
  or commercial use assumptions are made.

## Berkeley Rogue 4.22

Evidence inspected:

- no exact source tree
- local file tag `@(#)main.c 4.22 (Berkeley) 02/05/99`

Current status:

```text
License status: Unverified
Repository inclusion: Prohibited until verified
```

Reason for blocking:

- The exact source tree has not been found.
- The found `4.22` evidence may be a file revision tag rather than a
  game release.
- No matching license file has been inspected for a standalone Rogue
  4.22 distribution.

## Rogue 3.x Restoration Or Port

Current status:

```text
License status: Unverified
Repository inclusion: Prohibited until verified
```

Reason for blocking:

- No concrete source tree has been located or inspected.

## Modern Linux-Preserved Rogue Project

Current status:

```text
License status: Unverified
Repository inclusion: Prohibited until verified
```

Reason for blocking:

- No concrete project other than NetBSD has been inspected enough to
  become a candidate.
