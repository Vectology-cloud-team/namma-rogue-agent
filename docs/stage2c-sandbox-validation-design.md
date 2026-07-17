# Stage 2C Sandbox Validation Design

This document defines the future Stage 2C sandbox validation design.
It is design-only. It does not add a workflow, patch runtime, test
runner, repository writer, branch creator, commit path, push path, or
merge path.

Stage 2C is the first stage that may apply an approved fix proposal, but
only inside an ephemeral sandbox working tree. It still stops before any
persistent repository change.

## Position In The Loop

The completed stages before Stage 2C are:

- Stage 1: AI review
- Stage 2A: fix proposal generation
- Stage 2B: human approval record creation

Future Stage 2C takes these inputs:

```text
Validated Fix Proposal
+ Valid Approval Record
+ current pull request HEAD match
+ live approval labels
    |
    v
Ephemeral Sandbox Checkout
    |
    v
Patch Apply
    |
    v
Recommended Tests
    |
    v
Validation Report
    |
    v
Stop
```

Stage 2C does not commit, push, update a pull request branch, create a
branch, merge, approve a pull request, publish a package, deploy, or
write through the GitHub Contents API.

## Safety Boundary

The only place where Stage 2C may apply a patch is a temporary sandbox
working tree. The sandbox is discarded at workflow completion.

Forbidden persistent actions:

- modifying the main working tree,
- modifying the pull request branch directly,
- writing through the GitHub Contents API,
- `git commit`,
- `git push`,
- branch creation,
- pull request update,
- merge,
- release,
- package publish,
- deployment,
- external system modification.

If a future implementation cannot prove that an operation is limited to
the sandbox, it must fail closed before patch application.

## Inputs

Stage 2C requires these validated inputs:

- repository,
- pull request number,
- base SHA,
- head SHA,
- proposal ID,
- proposal hash,
- approval ID,
- approval record hash,
- approved by,
- approved at,
- approved-by repository permission,
- proposal artifact provenance,
- approval artifact provenance,
- policy hash,
- schema versions,
- requested test list,
- patch content,
- target file blob SHAs.

Artifacts and comments are not trusted by themselves. Each input must be
validated against live pull request state and default-branch policy.

## Live Gate

Artifact presence alone must not start Stage 2C. Before creating a
sandbox, the future validator must re-check all of these:

- the pull request is open,
- current HEAD equals the approval record `head_sha`,
- current HEAD equals the proposal `head_sha`,
- proposal ID and proposal hash match,
- proposal content hash recomputation matches,
- approval record hash matches,
- approval record status is `APPROVED`,
- `ai-fix-proposal` label is present,
- `ai-fix-approved` label is present,
- `ai-fix-validate` label is present,
- approval actor currently has repository `admin` or `maintain`,
- trusted policy hash matches,
- proposal schema validation succeeds,
- approval schema validation succeeds,
- result schema version is trusted,
- protected path checks pass,
- patch target blob SHA checks pass,
- proposal artifact and approval artifact provenance match,
- Stage 1 finding IDs match the proposal findings addressed.

Any failed gate prevents sandbox creation. Missing, expired, or
temporarily unavailable candidate artifacts may be skipped only before
their contents are trusted. Once an artifact is downloaded and parsed,
hash, provenance, schema, repository, pull request, HEAD, policy, or
content mismatch is fatal and must not silently fall back to an older
artifact.

## Approval Record Selection

Multiple approval records can exist for the same proposal because each
label event has its own `approved_at` and therefore its own approval ID.
Stage 2C must not depend on approval ID stability across repeated
approvals.

The selector should consider approval records that match:

- proposal ID,
- proposal hash,
- repository,
- pull request number,
- head SHA,
- policy hash,
- status `APPROVED`,
- trusted provenance,
- schema validation,
- live `ai-fix-approved` label,
- current actor permission re-check.

Among matching records, the newest valid `approved_at` should be used.
If the newest candidate artifact is missing or expired, the selector may
try the next candidate. If the newest candidate is downloaded and then
fails content validation, provenance validation, hash validation, or
schema validation, selection must fail closed instead of falling back.

## Workflow Separation

Future Stage 2C should use three separated workflow roles:

1. Sandbox Validation Request Collector
   - triggered by pull request label events,
   - secrets disabled,
   - write permissions disabled,
   - records untrusted request metadata only.

2. Sandbox Validator
   - triggered by `workflow_run`,
   - runs from default-branch trusted workflow and policy,
   - validates proposal and approval artifacts,
   - creates the sandbox checkout,
   - applies the patch in the sandbox only,
   - runs trusted test commands,
   - writes validation result artifacts,
   - has no persistent repository write permission.

3. Result Commenter
   - consumes only the validation result artifact,
   - posts or updates the Stage 2C sticky comment,
   - receives only the minimal comment permission.

The collector and validator must not be the same job. The validator
must not run pull-request-controlled workflows, policy, schema, prompts,
or scripts as trusted control-plane logic.

## Trigger Label

Stage 2C should require a separate human trigger label:

```text
ai-fix-validate
```

Required live labels:

- `ai-fix-proposal`,
- `ai-fix-approved`,
- `ai-fix-validate`.

Adding `ai-fix-approved` must not automatically start Stage 2C. This
keeps "approval recorded" separate from "run sandbox validation".

## Sandbox Model

The initial sandbox model should be:

1. Checkout the current pull request HEAD as detached HEAD.
2. Confirm the sandbox working tree is clean.
3. Reject submodules, or allow them only through explicit trusted policy.
4. Inspect symlinks and reject any target escape risk.
5. Confirm each patch target file blob SHA.
6. Run `git apply --check` in the sandbox.
7. Apply the patch in the sandbox.
8. Re-enumerate changed files.
9. Confirm changed files exactly match proposal files.
10. Re-run protected path checks.
11. Reject unexpected file creation, deletion, rename, or mode change.
12. Run trusted test command mappings.
13. Generate the validation result artifact.
14. Destroy the sandbox.

The sandbox is disposable. Its modified working tree is expected after a
successful apply, but those modifications must not persist outside the
job.

## Patch Apply Restrictions

The initial Stage 2C runtime must reject:

- absolute paths,
- `..` path traversal,
- `.git` paths,
- workflow changes,
- policy changes,
- schema changes,
- prompt changes,
- symlink target escape,
- binary patches,
- submodule changes,
- file mode changes,
- rename,
- delete,
- files not listed in the proposal,
- blob SHA mismatch,
- oversized patch,
- oversized target file,
- generated artifacts stored in the repository.

Rename and delete may be reconsidered in a later design, but the initial
runtime should forbid both.

## Test Execution Model

`tests_recommended` must never be passed directly to a shell. Proposal
content can request test IDs only. Trusted policy maps those IDs to
fixed command argv arrays.

Example test IDs:

- `unit`,
- `approval-targeted`,
- `workflow-checker`,
- `compileall`.

The future runner should execute commands with shell-free semantics,
equivalent to `shell=False`.

Forbidden test execution behavior:

- running free-form proposal shell text,
- `eval`,
- `bash -c` with AI or PR strings,
- command substitution,
- pipes,
- redirection,
- network download,
- `curl` or `wget`,
- package install,
- privileged Docker,
- `sudo`,
- secret access.

Test output is evidence only. Test success must not trigger commit,
push, branch update, or merge.

## Network And Secrets

The sandbox validator should run with:

- no repository secrets,
- no `OPENAI_API_KEY`,
- no `contents: write`,
- no `pull-requests: write`,
- no `issues: write`,
- no package installation,
- no intentional external network access except checkout and artifact
  retrieval.

GitHub-hosted runners do not provide a simple complete network-disable
primitive for arbitrary test code. The design must acknowledge this
limit. If stronger isolation is required, the project should use a
locked-down self-hosted runner or a dedicated sandbox service before
allowing high-risk tests.

## Result Classification

Stage 2C result status is separate from workflow infrastructure status.

`SUCCESS`:

- patch applied,
- expected files only changed,
- all required tests passed.

`PATCH_REJECTED`:

- `git apply --check` failed,
- blob SHA mismatch,
- path or policy violation.

`TEST_FAILED`:

- patch applied,
- allowed test command failed.

`STALE`:

- current HEAD mismatch,
- proposal or approval targets an old HEAD.

`FATAL`:

- provenance mismatch,
- hash mismatch,
- schema mismatch,
- actor authorization failure,
- malformed artifact,
- trust boundary violation.

`INFRA_ERROR`:

- runner failure,
- transient artifact retrieval failure,
- transient GitHub API failure.

AI review verdicts must not be confused with Stage 2C execution status.

## Result Schema

The schema draft is:

```text
.github/codex/schemas/sandbox-validation-result.schema.json
```

The result separates persistent repository state from sandbox state:

- `persistent_repository_modified`: must be `false`,
- `sandbox_worktree_modified`: may be `true` after patch apply.

This avoids treating expected sandbox modifications as persistent
repository writes.

The result also records proposal artifact provenance, approval artifact
provenance, schema versions, approval actor repository permission, and
the test plan hash so the validation can be audited without trusting a
comment body.

## Validation ID

`validation_id` should be a deterministic hash prefix derived from:

- proposal ID,
- proposal hash,
- approval ID,
- approval record hash,
- head SHA,
- policy hash,
- test plan.

`started_at` and `completed_at` must not be part of the validation ID.
The same proposal, approval record, HEAD, policy, and test plan should
produce the same ID.

## Artifact Design

Future Stage 2C should upload a `sandbox-validation-result` artifact.

Allowed artifact contents:

- result JSON,
- bounded test logs,
- bounded patch apply logs,
- changed file manifest,
- file hashes.

Forbidden artifact contents:

- secrets,
- environment dumps,
- Git credentials,
- full home directory,
- `.git` credentials,
- arbitrary repository archive,
- untrusted binary output.

Logs need size limits, redaction, and retention policy. The result JSON
should remain small enough to render in the sticky comment summary.

## Sticky Comment

Stage 2C uses a separate sticky comment marker:

```html
<!-- namma-ai-sandbox-validation -->
```

The comment should display:

- validation ID,
- proposal ID,
- approval ID,
- HEAD SHA,
- patch check result,
- patch apply result,
- tests result,
- status,
- `Persistent Repository Modified: No`,
- `Commit Created: No`,
- `Push Performed: No`,
- `Merge Performed: No`.

This comment is separate from Stage 2A proposal comments and Stage 2B
approval comments.

## Concurrency

The future workflow should prevent duplicate validations for the same:

```text
repository + pull request number + head SHA + proposal ID
```

When a new HEAD appears, old validation runs may be cancelled. If they
are not cancelled, they must re-check live HEAD before publishing a
result and report `STALE` rather than updating the current validation
state as successful.

## Fork Policy

Initial Stage 2C runtime should reject fork pull requests. Reasons:

- untrusted code execution,
- network exfiltration risk,
- artifact provenance risk,
- token exposure risk,
- checkout behavior differences.

Only same-repository branches should be eligible until the sandbox
isolation model is stronger.

## Threat Model

| Threat | Stage 2C mitigation |
| --- | --- |
| Malicious PR changes | Treat PR content as untrusted and use default-branch policy. |
| Malicious patch text | Validate paths, blob SHAs, protected paths, and patch size before sandbox apply. |
| Artifact substitution | Bind artifact provenance to workflow run, repository, PR, and SHA. |
| Artifact replay | Require live HEAD, labels, proposal hash, approval hash, and policy hash. |
| Stale approval replay | Reject mismatched current HEAD and re-check actor permission. |
| Approval actor revocation | Re-query repository permission before sandbox creation. |
| Label race | Re-read live labels immediately before sandbox creation. |
| HEAD race | Re-read live PR head before sandbox creation and before result posting. |
| TOCTOU between validation and checkout | Checkout exact approved head SHA and confirm it still matches live PR. |
| Symlink attack | Reject symlink target escape before and after apply. |
| Path traversal | Reject absolute paths, backslashes, and `..`. |
| Test command injection | Use trusted test IDs mapped to fixed argv commands. |
| Test code exfiltration | Avoid secrets and limit network; document hosted-runner limits. |
| Excessive log output | Enforce log byte limits and redaction. |
| Fork PR | Reject fork PRs in the initial runtime. |
| Compromised dependency | Forbid package install and prefer existing checked-in test tools. |
| Runner persistence assumptions | Treat runner as disposable and do not persist sandbox state. |
| Artifact expiration | Skip missing or expired candidates before trust; fail closed after parse mismatch. |
| Duplicate workflow runs | Use concurrency and live stale checks. |
| Concurrent validation runs | Use repository, PR, head SHA, and proposal ID concurrency key. |

## Static Checker Plan

The future static checker should verify:

- no `contents: write`,
- no commit, push, or merge path,
- no unrestricted shell execution,
- no PR-side workflow, policy, schema, or prompt fallback,
- no secrets in sandbox jobs,
- no `OPENAI_API_KEY`,
- test IDs only,
- trusted command mapping,
- fork rejection,
- symlink and path traversal rejection,
- protected path rejection,
- artifact provenance validation,
- proposal and approval live gates,
- current HEAD revalidation,
- persistent repository writes forbidden,
- `ai-fix-approved` alone does not start Stage 2C,
- `ai-fix-validate` is required.

## Unit Test Matrix

Runtime implementation should add these tests.

Normal cases:

- valid proposal, valid approval, valid labels, same HEAD,
- patch check and apply succeed,
- allowed tests succeed,
- deterministic validation ID,
- one sticky comment.

Rejection cases:

- missing proposal label,
- missing approval label,
- missing validate label,
- stale HEAD,
- proposal hash mismatch,
- approval hash mismatch,
- actor permission revoked,
- fork PR,
- protected path,
- path traversal,
- symlink escape,
- binary patch,
- unexpected changed file,
- blob SHA mismatch,
- arbitrary shell command,
- network command,
- secret access attempt,
- duplicate or concurrent run,
- artifact replay.

Result cases:

- `PATCH_REJECTED`,
- `TEST_FAILED`,
- `STALE`,
- `FATAL`,
- `INFRA_ERROR`.

## Non-Goals For PR #25

PR #25 does not implement:

- executable Stage 2C workflow,
- patch apply runtime,
- test execution runtime,
- repository write,
- commit automation,
- push automation,
- merge automation,
- workflow permission changes,
- secret changes,
- label E2E,
- Stage 2C E2E.
