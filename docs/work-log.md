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
