# AI Development Loop

This document records the staged plan for using AI assistance inside the
GitHub pull request loop.

## Stage 1: Automated Architect Review

Stage 1 adds an automated architect-review control plane for pull
requests. It is split into an unprivileged collector and a privileged
reviewer. The reviewer runs the official `openai/codex-action@v1`
action and posts a single sticky pull request comment with the review
result.

Stage 1 is review-only:

- It does not edit files.
- It does not commit.
- It does not push.
- It does not merge.
- It does not approve or request changes through the GitHub review API.
- It does not implement auto-fix behavior.

The workflow uses prompt version `architect-review-v1`.

PR #10 is the Stage 1 control-plane bootstrap pull request. Because the
privileged reviewer workflow and trusted prompt do not exist on the
default branch until this PR is merged, PR #10 must be reviewed and
merged by humans. The bootstrap behavior must not be weakened by adding
a fallback to a pull-request-controlled prompt. After PR #10 is merged,
run a separate canary pull request to verify the end-to-end AI review
loop.

The review prompt is trusted only when it comes from the default branch
or the pull request base SHA validated by the privileged reviewer. The
Stage 1 control plane is split as follows:

- `.github/workflows/architect-review-collect.yml`: unprivileged
  collector triggered by `pull_request`
- `.github/workflows/architect-review.yml`: privileged reviewer
  triggered by `workflow_run`

The collector checks out the pull request merge ref only to produce
`manifest.json` and `review.diff`. It does not run Codex, does not use
`OPENAI_API_KEY`, does not run repository scripts or tests, and does not
have write permissions.

The reviewer downloads the collector artifact, validates the manifest,
checks the current pull request state through the GitHub API, and then
loads the trusted prompt from the validated base SHA. Codex reviews the
diff artifact as untrusted data. A pull request can change its own copy
of `.github/codex/prompts/architect-review.md`, workflow files, or other
configuration, but those copies are not used as trusted reviewer policy.
If the trusted base prompt is missing, the reviewer fails closed instead
of falling back to the pull request copy.

### Trigger

The collector workflow is triggered by `pull_request` events:

- `opened`
- `synchronize`
- `reopened`
- `ready_for_review`

The reviewer workflow is triggered by `workflow_run` completion from the
collector workflow. Neither workflow uses `pull_request_target`.

The privileged reviewer only proceeds when all of these are true:

- The collector workflow concluded successfully.
- The completed workflow name exactly matches `Architect Review Collect`.
- The original event was `pull_request`.
- The repository identity matches `Vectology-cloud-team/namma-rogue-agent`.
- The pull request is not a draft.
- The pull request branch is in this repository, not a fork.
- The author is not a bot.
- The author association is `OWNER`, `MEMBER`, or `COLLABORATOR`.
- The current pull request head SHA matches the artifact manifest.
- The repository secret `OPENAI_API_KEY` is available.

Dependabot and other unapproved bot pull requests are excluded by the bot
filter.

### Artifact Limits

The collector artifact contains:

- `manifest.json`
- `review.diff`

The collector enforces:

- maximum diff bytes,
- maximum changed file count,
- maximum artifact bytes,
- binary file omission from the review diff.

The reviewer validates the manifest schema, exact artifact file names,
artifact sizes, repository identity, collector workflow identity, pull
request number, and current head SHA before running Codex. A stale
artifact is skipped without posting a comment.

### Checkout And Permissions

The collector checks out the pull request merge ref:

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

The privileged review job can read actions artifacts, read contents, and
read pull request state. Comment posting is isolated in a separate job
with pull request comment write permissions and no `OPENAI_API_KEY`.

The Codex action runs with:

```yaml
permission-profile: ":read-only"
safety-strategy: drop-sudo
```

The workflow does not set an explicit Codex model or effort in Stage 1.
It uses the defaults provided by `openai/codex-action@v1`.

All third-party Actions are pinned to full commit SHAs with a human
version comment. Repository settings should enable the equivalent of
`Require actions to be pinned to a full-length commit SHA` when
available.

### Comment Posting

Comment posting is isolated in a second reviewer job. That job does not
check out the repository and does not receive `OPENAI_API_KEY`.

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

## Stage 1.1: Failure Classification And Retry Control

Stage 1.1 keeps the Stage 1 trust boundary intact and adds failure
classification for the privileged reviewer. The collector remains
unprivileged and unchanged.

Reviewer failures are grouped into three classes:

- `RETRYABLE`: temporary external failures that may recover on retry,
  such as OpenAI timeouts, OpenAI rate limits, OpenAI 5xx responses,
  GitHub API 429 or 5xx responses, transient network errors, transient
  artifact download failures, and temporary service unavailability.
- `FATAL`: configuration, validation, permission, or trust-boundary
  failures that should not be retried, such as a missing trusted prompt,
  invalid manifest data, repository or SHA mismatches, stale artifacts,
  path traversal, permission errors, workflow configuration errors,
  unapproved Actions, or Action SHA pinning violations.
- `SUCCESS`: a completed AI review. `APPROVED`, `CHANGES_REQUESTED`,
  and `NEEDS_HUMAN` are review outcomes, not GitHub Actions failures.

Only `RETRYABLE` failures are retried automatically. The reviewer makes
at most three attempts for retryable operations. The current workflow
therefore waits 30 seconds before attempt 2 and 60 seconds before
attempt 3. The shared delay table also records 120 seconds as the next
backoff slot if a later policy increases the attempt count. If all
attempts fail, the workflow stops and writes a job summary with the
failure class, failure code, operation, attempt count, reviewed pull
request number, reviewed head SHA, and a sanitized error summary.
If the Codex Action fails after preflight validation but returns no
failure details, the reviewer treats that as a retryable provider/action
failure rather than as a validated AI review result.

`FATAL` failures stop immediately without retry. They do not post a
misleading AI review comment. A stale artifact is treated as a fatal
validation result for that run so an old review cannot update the sticky
comment for a newer head SHA.

Infrastructure failure reporting is kept separate from the AI review
sticky comment. The reviewer does not overwrite an existing AI review
comment with an infrastructure failure. Human follow-up should use the
job summary and workflow logs.

Retry is not an automatic repair loop. It does not edit files, commit,
push, merge, approve, label, or make false-positive decisions. Model,
reasoning effort, and cost controls remain outside Stage 1.1.

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
- disable the `Architect Review Collect` workflow in GitHub Actions,
- remove or rename `.github/workflows/architect-review.yml`,
- remove or rename `.github/workflows/architect-review-collect.yml`,
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
