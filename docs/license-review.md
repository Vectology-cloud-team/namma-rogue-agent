# License Review Notes

This file tracks license evidence gathered during source selection and
source import. It does not approve legacy local modifications for direct
reuse.

## Review Policy

Before any additional Rogue source is copied into this repository,
inspect:

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
- Rogueforge `rogue5.4.4-src.tar.gz` `LICENSE.TXT`
- `phs/rogue` tag `v5.4.4` `LICENSE.TXT`
- source headers in local `.c` and `.h` files
- `vers.c`
- build files referencing distribution packaging

Required status wording:

```text
Pristine archive license evidence: PASS
Generated helper-file notices: PASS WITH NOTICE RETENTION
Repository inclusion: PHASE 5 PRISTINE BASELINE PRESENT WITH NOTICE RETENTION
Local modification reuse: UNVERIFIED
```

License evidence by origin:

Original Rogue-derived portions:

- `LICENSE.TXT` contains BSD-style redistribution and binary
  redistribution permissions for the Toy, Arnold, and Wichman portions.
- Most source headers refer to `LICENSE.TXT`.

Nicholas J. Kisseberth portions:

- `LICENSE.TXT` contains separate BSD-style terms for Nicholas J.
  Kisseberth portions.
- `state.c` and `mdport.c` are the main inspected files in this group.

David Burren `xcrypt.c` portions:

- `LICENSE.TXT` contains separate BSD-style terms for David Burren
  `xcrypt.c` portions.

Other third-party portions:

- Autoconf helper files such as `config.guess`, `config.sub`,
  `configure`, and `install-sh` contain their own generated-tool
  notices.
- No other third-party game-code origin has been approved.

Generated and helper-file notice classification:

| File | Copyright holder | License or exception | Required notice | Redistribution status | Modification status | Repository inclusion status |
| --- | --- | --- | --- | --- | --- | --- |
| `configure` | FSF | Autoconf generated-script permission | Keep generated-script notice | PASS | PASS | PRESENT WITH NOTICE RETENTION |
| `config.guess` | FSF | GPLv2-or-later with Autoconf exception | Keep GPL and exception notice | PASS WITH EXCEPTION | PASS WITH EXCEPTION | PRESENT WITH NOTICE RETENTION |
| `config.sub` | FSF | GPLv2-or-later with Autoconf exception | Keep GPL and exception notice | PASS WITH EXCEPTION | PASS WITH EXCEPTION | PRESENT WITH NOTICE RETENTION |
| `install-sh` | X Consortium; FSF changes | X Consortium notice; FSF changes public domain | Keep both notices | PASS | PASS | PRESENT WITH NOTICE RETENTION |

Details:

- `configure` states that the Free Software Foundation gives unlimited
  permission to copy, distribute, and modify the generated script.
- `config.guess` and `config.sub` include GPLv2-or-later terms and a
  special exception allowing distribution with programs that contain an
  Autoconf-generated configuration script under the same distribution
  terms as that program.
- `install-sh` contains the X Consortium permission notice and states
  that FSF changes to that file are public domain.

The Rogueforge archive contains no additional Automake helper files such
as `missing`, `depcomp`, `ltmain.sh`, or `aclocal.m4`.

Notice-retention policy:

- Preserve helper files exactly in the pristine upstream tree.
- Preserve all existing notices in both Phase 5 source trees.
- Keep future compatibility patches separate from the pristine upstream
  files.

Local additions:

- Logging additions, `/tmp/rogue_log.txt` usage, controller/viewer
  scripts, BAK/orig files, and 64x160 fragments are not yet tied to a
  reviewed license grant.
- Treat these as unapproved local additions until authorship and rights
  are confirmed.

Baseline investigation notes:

- The Rogueforge `rogue5.4.4-src.tar.gz` archive contains
  `LICENSE.TXT`.
- Its archive SHA-256 is
  `7d37a61fc098bda0e6fac30799da347294067e8e079e4b40d6c781468e08e8a1`.
- The `phs/rogue` tag `v5.4.4` baseline contains `LICENSE.TXT`.
- Its `LICENSE.TXT` SHA-256 is
  `92f8e05f4ae64d8320f2941f6c3f15687b96fb5452693996e5c53c80d38ecf07`.
- The copied local tree has the same `LICENSE.TXT` after text
  line-ending normalization.
- This is evidence that the license text is present, not completed
  project approval.
- Local modifications in `command.c`, `io.c`, `main.c`, `rip.c`, and
  `rogue.h` still need authorship and rights confirmation.

Current status:

```text
Pristine archive license evidence: PASS
Generated helper-file notices: PASS WITH NOTICE RETENTION
Repository inclusion: PHASE 5 PRISTINE BASELINE PRESENT WITH NOTICE RETENTION
Local modification reuse: UNVERIFIED
Commercial project adoption: not yet approved
```

Reason for blocking:

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
- Project approval is required before import, redistribution,
  modification, or commercial-use assumptions are made.

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
