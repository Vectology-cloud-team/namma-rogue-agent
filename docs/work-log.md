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

Next command:

```powershell
python scripts/check_markdown.py
```
