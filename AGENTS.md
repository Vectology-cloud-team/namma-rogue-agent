# Agent Working Rules

This repository is preparing a deterministic Rogue environment for AI
evaluation. Keep game logic, environment control, AI planning, and
display concerns separated.

## Hard Rules

- Separate game logic from AI control.
- Do not embed project-specific LLM or NaMMA calls directly inside the Rogue engine.
- Do not make curses screen scraping the main AI-control interface.
- Keep human-readable ASCII output as a separate viewer.
- The same seed and the same action sequence must reproduce the same result.
- Do not break random-number reproducibility.
- Version every observation and action schema change.
- Do not convert free-form AI text directly into game commands.
- Validate all structured AI output before execution.
- Do not expose hidden game state through normal agent observations or
  legal-action lists.
- Add automated tests when adding new behavior.
- Avoid large, unrelated changes in one commit.
- Do not delete existing assets casually.
- Preserve legacy code and notes under `legacy/` until reviewed.
- Do not import source with unclear licensing or redistribution terms.
- Document assumptions when design decisions are based on incomplete information.
- Run available tests, lint, and build checks before committing.
- Do not commit secrets, API keys, credentials, or machine-local configuration.

## Design Bias

- Prefer a small, deterministic headless environment before adding AI.
- Prefer semantic actions over raw keypress actions.
- Prefer provider interfaces over coupling to one local inference server.
- Prefer replayable experiments over one-off terminal demos.

## Long-Running Task Rule

- Commit after each internally consistent milestone.
- Do not wait until the entire phase is complete.
- Before interruption or when remaining execution budget appears low,
  record completed work, current failures, and next command in
  `docs/work-log.md`.
- A new session must read `AGENTS.md`, `docs/work-log.md`, `git status`,
  and recent commits before continuing.
- Resume from repository state, not from conversation memory.
