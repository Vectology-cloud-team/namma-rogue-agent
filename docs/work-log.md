# Work Log

This log is for resumable long-running work. Do not record secrets,
tokens, credentials, or machine-local absolute paths here.

## Phase 7 Runtime Contract Skeleton

Status:

- Started from main after PR #6 merge.
- Scope is Runtime Contract skeleton only.
- RogueDomainAdapter, Rogue headless work, Local AI, and NaMMA are out
  of scope.
- Runtime package, Fake Domain, Fake DecisionProviders, Replay Level 1, and
  synchronous one-shot RuntimeOrchestrator are implemented.
- PR #7 review found that GitHub showed Python physical-line formatting
  hazards. Local and Git blob checks now verify tracked text files with
  `scripts/check_text_files.py`.
- Action lifecycle was tightened so validation rejection is not an
  ExecutedAction. Schema and observable-rule rejection fault the initial
  Runtime Profile; in-domain failure remains an executed action.
- Replay Level 1 records executed actions only.

Latest validation:

- `python -m unittest discover -s tests -p "test_*.py"`
- `python scripts/check_markdown.py`
- `python scripts/check_markdown.py --git-ref HEAD`
- `python scripts/check_text_files.py`
- `python scripts/check_text_files.py --git-ref HEAD`
- `python -m compileall runtime`
- `git diff --check`

Next command:

```powershell
git status
```

Open items:

- Re-review PR #7 after the new commit is pushed.
- Keep RogueDomainAdapter, Rogue headless work, Local AI, and NaMMA deferred
  until Phase 7 review is complete.

## Phase 8 Rogue Domain Adapter Boundary

Status:

- Started from `main` after PR #7 merge.
- Branch: `feature/rogue-domain-adapter-boundary`.
- Scope is RogueDomainAdapter boundary, Native ABI specification, and fake
  native backend tests only.
- Rogue 5.4.4 pristine and patched game code must remain unchanged in this
  phase.
- Real native loading, real reset, real step, curses removal, Local AI, NaMMA,
  and 64x160 work remain deferred.

Initial validation before Phase 8 edits:

- `python -m unittest discover -s tests -p "test_*.py"`: 50 tests passed,
  2 skipped.
- `python scripts/check_text_files.py`: passed.
- `python scripts/check_markdown.py`: passed.
- `git status`: clean on the new Phase 8 branch.

Read before starting:

- `AGENTS.md`
- `docs/work-log.md`
- `docs/runtime-architecture.md`
- `docs/initial-runtime-profile.md`
- `docs/runtime-contract.md`
- `docs/runtime-replay-level1.md`
- `docs/phase7-implementation.md`
- `runtime/README.md`
- Phase 7 runtime implementation and tests.
- Rogue 5.4.4 pristine and patched source trees.
- `patches/0001-ncurses-compatibility.patch`.

Current Phase 8 findings:

- `main.c::main()` owns process startup.
- `main.c::playit()` owns the main `while (playing) command()` loop.
- `command.c::command()` is the first practical one-action boundary
  candidate, but one command is not always one game turn.
- `io.c::readchar()` and `mdport.c::md_readchar()` are the main keyboard
  input boundary candidates.
- `move.c::do_move()` owns semantic player movement and should not be
  reimplemented in Python.
- Death, victory, quit, save, and signal paths currently terminate the
  process or block on interactive prompts.
- RNG state is primarily the global `seed` and `RN` macro, initialized from
  wall-clock time and PID unless controlled.
- Added `adapter/native/include/namma_rogue_api.h` as a specification header
  only. It does not connect to Rogue and does not load a shared library.
- Added `runtime/rogue/RogueDomainAdapter`, `RogueNativeBackend`, and
  `FakeRogueNativeBackend`.
- Verified the Runtime path through the Rogue adapter using Replay Level 1.
- Hidden fake backend state is present in `PrivilegedDebugState` but is not
  present in AgentObservation or DecisionRequest.

Phase 8 commits so far:

- `f2520f5 Document Rogue control flow and state boundaries`
- `41b189a Define versioned Rogue native C ABI`
- `41d8a9d Add RogueDomainAdapter and fake native backend`

PR #8 review-fix notes:

- The seven Rogue adapter Python files were verified as normal LF Git blobs
  and refreshed as new multi-line blobs with clearer module docstrings.
- `scripts/check_text_files.py` now flags larger Python files compressed into
  up to four physical lines and suspicious bytes-per-line density.
- Native ABI public status, action, direction, and terminal-kind types are now
  fixed-width `uint32_t` typedefs with macro values.
- Runtime error was removed from native terminal kinds; backend errors remain
  status-code or `DomainAdapterError` paths.
- Native pointer lifetimes and `struct_size` initialization rules are
  documented in the header and ABI document.

Final PR #8 physical-line review notes:

- Local `git show HEAD:<path>` byte inspection did not reproduce the
  GitHub-reported collapsed line counts. The reported 5-line, 2-line,
  10-line, and 1-line blobs were not present in local HEAD.
- The actionable local root cause was checker coverage: `.h`, `.c`, and
  `.cpp` files were not text-check targets, and Python collapsed-line checks
  were too permissive for large files with fewer than 10 physical lines.
- `scripts/check_text_files.py` now checks C-like sources, low-line large
  Python files, low-line large C-like files, multi-directive C lines,
  multi-import Python lines, class/def collisions, and docstring-code
  collisions.
- A regression test now commits a collapsed blob, rewrites the worktree to a
  normal source file, and verifies `--git-ref HEAD` still reads the committed
  collapsed blob rather than the worktree.

Next command:

```powershell
python -m unittest discover -s tests -p "test_*.py"
```
