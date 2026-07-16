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

The review policy is trusted only when it comes from
`.github/codex/review-policy.yml` in the reviewer control plane. Pull
requests may change their own copy of the policy file, but that copy is
reviewed as ordinary PR content and is not used to configure the
privileged reviewer for the same run.

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

The Codex model, reasoning effort, prompt budget, diff budget, and
exclude rules are loaded from the trusted review policy. The workflow
does not hard-code model or effort values in the Codex Action steps.

All third-party Actions are pinned to full commit SHAs with a human
version comment. Repository settings should enable the equivalent of
`Require actions to be pinned to a full-length commit SHA` when
available.

### Comment Posting

Comment posting is isolated in a second reviewer job. That job checks
out only the trusted reviewer control plane, does not run PR-provided
scripts, and does not receive `OPENAI_API_KEY`.

The sticky comment contains:

- marker: `<!-- namma-ai-architect-review -->`
- heading: `## Automated Architect Review`
- reviewed head SHA
- workflow run ID
- prompt version
- review policy version
- model and reasoning effort
- reviewed file count, excluded file count, diff bytes, and prompt bytes
- review status
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
comment for a newer head SHA. The comment-posting job also fetches the
live pull request immediately before creating or updating the sticky
comment and fails closed if the head SHA no longer matches the reviewed
SHA.

The privileged reviewer verifies the artifact metadata against the live
pull request before checking out the trusted prompt. The base repository,
head repository, base SHA, and head SHA must match the live PR. The
live changed-file list must also match the manifest, and files without
reviewable text patches cause a fail-closed result. The review diff is
then refreshed from the GitHub API and replaces the collector-provided
`review.diff`, so untrusted artifact contents cannot select the prompt
base or forge the reviewed diff.

Infrastructure failure reporting is kept separate from the AI review
sticky comment. The reviewer does not overwrite an existing AI review
comment with an infrastructure failure. Human follow-up should use the
job summary and workflow logs.

Retry is not an automatic repair loop. It does not edit files, commit,
push, merge, approve, label, or make false-positive decisions. Model,
reasoning effort, and budget controls are handled separately by
Stage 1.1-B.

## Stage 1.1-B: Reviewer Policy And Budget Control

Stage 1.1-B introduces a trusted review policy layer for the privileged
reviewer. The policy file is:

```text
.github/codex/review-policy.yml
```

The policy controls:

- Codex model,
- reasoning effort,
- maximum reviewed file count,
- maximum review diff bytes,
- maximum trusted prompt bytes,
- maximum artifact bytes,
- file exclude patterns.

The reviewer loads this policy before downloading the collector
artifact. Missing or malformed policy fields fail fast. The required
policy fields include `model`, `reasoning.effort`,
`limits.max_changed_files`, `limits.max_diff_bytes`, and
`limits.max_prompt_bytes`.

The collector remains unprivileged. It still does not run Codex, does
not use `OPENAI_API_KEY`, and does not execute PR-provided scripts. Its
artifact-size checks are transport safety caps. The privileged reviewer
uses the trusted policy as the review budget and refreshes the live diff
from GitHub before applying policy limits.

If the reviewable file count or filtered diff size exceeds policy
budget, the reviewer skips the AI review. The workflow succeeds, and
the sticky comment records that the review was skipped with the reason
`Diff budget exceeded`. If all changed files are excluded by policy, the
review is also skipped and reported in the sticky comment.

The collector still has transport safety caps for artifact creation. If
an input is too large for the collector to safely package, the collector
may fail before the privileged reviewer can post a policy-skip comment.
The policy skip behavior applies after the reviewer has successfully
downloaded and validated the collector artifact.

If the trusted prompt exceeds `limits.max_prompt_bytes`, the reviewer
does not truncate trust-boundary instructions and does not fall back to
the PR copy. It skips the AI review and reports `Prompt budget exceeded`
in the sticky comment and job summary.

The job summary reports the review policy and input metrics without
printing the full prompt or diff. The sticky comment records the policy
version, model, reasoning effort, file counts, diff bytes, prompt bytes,
and review status so later readers can see which settings were used.

Policy retry and budget control are not Stage 2 automation. They do not
edit files, commit, push, merge, label, approve, or block merges.

## Stage 2A: Fix Proposal Generator

Stage 2A implements the proposal-generation part of the Stage 2 design.
It is label-gated by `ai-fix-proposal` and still preserves the Stage 1
trust boundary: an unprivileged collector records the request, and a
privileged default-branch generator validates all gates before using
Codex.

The design is recorded in:

```text
docs/stage2-fix-proposal-design.md
```

Stage 2 remains split into:

- `Stage 2A: Fix Proposal`, where AI may generate a structured proposal
  without changing repository files,
- `Stage 2B: Human Approval`, where a human explicitly approves a
  proposal without commit or push,
- `Stage 2C: Sandboxed Apply`, where an approved proposal may later be
  applied in isolation, still without production branch commit or push.

The trusted fix policy draft is `.github/codex/fix-policy.yml`, and the
proposal contract is
`.github/codex/schemas/fix-proposal.schema.json`.

Stage 2 proposal generation is label-gated by `ai-fix-proposal`. That
label permits only proposal generation. A separate `ai-fix-approved`
label is required before any future sandbox apply, and even that label
does not permit commit, push, merge, or production branch writes.

Stage 2A may generate a verified JSON proposal, save it as an artifact,
and post or update a separate sticky comment with marker
`<!-- namma-ai-fix-proposal -->`. It does not apply patches, modify the
working tree, run recommended tests, commit, push, create branches, open
pull requests, merge, or use GitHub code suggestions.

Stage 2B may consume the `ai-fix-approved` label only to create a
trusted approval record artifact and a separate sticky comment with
marker `<!-- namma-ai-approval -->`. Approval is valid only when the
current pull request head SHA, repository, pull request number, proposal
ID, proposal hash, trusted policy hash, proposal artifact, live
`ai-fix-proposal` label, and verified `OWNER` or `MEMBER` label actor all
match. The label alone is never sufficient.

Stage 2B does not apply patches, modify the working tree, run
recommended tests, commit, push, create branches, open pull requests,
merge, or use GitHub code suggestions. Stage 2C sandbox apply is still
not implemented.

## Human Decisions

The following decisions remain human-owned:

- whether to merge a pull request,
- whether to accept or ignore an automated review finding,
- whether to request legal, security, or architecture review,
- whether to enable any future auto-fix workflow,
- whether to change the trusted review policy,
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
OpenAI API usage. Billing depends on the trusted review policy and the
size of the pull request under review.

The job summary and sticky comment report the selected model, reasoning
effort, reviewed file count, diff bytes, and prompt bytes. Oversized
reviews are skipped instead of being sent to Codex.
