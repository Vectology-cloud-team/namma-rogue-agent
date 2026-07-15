# AI Development Loop

This document records the staged plan for using AI assistance inside the
GitHub pull request loop.

## Stage 1: Automated Architect Review

Stage 1 adds an automated architect-review workflow for pull requests.
The workflow runs the official `openai/codex-action@v1` action and posts
a single pull request comment with the review result.

Stage 1 is review-only:

- It does not edit files.
- It does not commit.
- It does not push.
- It does not merge.
- It does not approve or request changes through the GitHub review API.
- It does not implement auto-fix behavior.

The workflow uses prompt version `architect-review-v1`.

The review prompt is trusted only when it comes from the pull request
base SHA. The workflow checks out:

- `trusted-base/`: `${{ github.event.pull_request.base.sha }}`
- `review-target/`: `refs/pull/${{ github.event.pull_request.number }}/merge`

Codex receives the prompt from `trusted-base/` and reviews the repository
state in `review-target/`. A pull request can change its own copy of
`.github/codex/prompts/architect-review.md`, but that copy is not used
as the review prompt. If the trusted base prompt is missing, the workflow
fails closed instead of falling back to the pull request copy.

### Trigger

The workflow is triggered by `pull_request` events:

- `opened`
- `synchronize`
- `reopened`
- `ready_for_review`

The workflow intentionally does not use `pull_request_target`.

The review job only runs when all of these are true:

- The pull request is not a draft.
- The pull request branch is in this repository, not a fork.
- The author is not a bot.
- The author association is `OWNER`, `MEMBER`, or `COLLABORATOR`.
- The repository secret `OPENAI_API_KEY` is available.

Dependabot and other unapproved bot pull requests are excluded by the bot
filter.

### Checkout And Permissions

The review job checks out the pull request merge ref:

```yaml
ref: refs/pull/${{ github.event.pull_request.number }}/merge
fetch-depth: 0
persist-credentials: false
```

The job has only:

```yaml
permissions:
  contents: read
```

The Codex action runs with:

```yaml
permission-profile: ":read-only"
safety-strategy: drop-sudo
```

The workflow does not set an explicit Codex model or effort in Stage 1.
It uses the defaults provided by `openai/codex-action@v1`.

### Comment Posting

Comment posting is isolated in a second job. That job does not check out
the repository and does not receive `OPENAI_API_KEY`.

The sticky comment contains:

- marker: `<!-- namma-ai-architect-review -->`
- heading: `## Automated Architect Review`
- reviewed head SHA
- workflow run ID
- prompt version
- verdict
- Codex final message
- an explicit note that the review is AI-generated and does not replace
  human merge judgment

The workflow deduplicates comments by marker only. A later run for a new
head SHA updates the same marker-owned comment instead of creating
another one.

## Stage 2 Plan

Stage 2 is intentionally not implemented yet. Candidate Stage 2 features
may include:

- optional label-gated fix suggestions,
- separate human approval before any file write,
- separate human approval before any commit or push,
- stricter issue templates for AI review findings,
- metrics for review latency and false positives.

Stage 2 must not be added until Stage 1 has produced a real review on a
pull request and the workflow behavior has been inspected.

## Human Decisions

The following decisions remain human-owned:

- whether to merge a pull request,
- whether to accept or ignore an automated review finding,
- whether to request legal, security, or architecture review,
- whether to enable any future auto-fix workflow,
- whether to change the Codex model, effort, or cost controls,
- whether to grant broader repository permissions.

High-risk changes such as native ABI changes, GitHub Actions permission
changes, secret handling, source import, license decisions, and runtime
execution changes require human review even when the automated reviewer
returns `VERDICT: APPROVE`.

## Stop Methods

To stop the Stage 1 review loop:

- disable the `Architect Review` workflow in GitHub Actions,
- remove or rename `.github/workflows/architect-review.yml`,
- remove the `OPENAI_API_KEY` repository secret,
- convert a pull request back to draft,
- use a fork or bot account that is intentionally excluded.

Do not use `pull_request_target` as a workaround for skipped fork pull
requests.

## API Billing

The workflow uses `OPENAI_API_KEY`, so successful review runs may incur
OpenAI API usage. Billing depends on the defaults selected by
`openai/codex-action@v1` and the size of the pull request under review.

Stage 1 does not set an explicit model or effort. If cost, latency, or
review depth need tighter control, that should be a Stage 2 design
decision after observing real Stage 1 runs.
