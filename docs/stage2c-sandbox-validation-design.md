# Stage 2C Sandbox Validation Design

This document defines the Stage 2C sandbox validation design. PR #25
added the design-only baseline. PR #26 adds Stage 2C-A preflight
runtime only. PR #31 adds Stage 2C-B1 ephemeral sandbox patch apply.
Stage 2C-B1 still does not run recommended tests, write a repository
branch, create a branch, commit, push, update a pull request, or merge.

Stage 2C is the first stage that may apply an approved fix proposal, but
only inside an ephemeral sandbox working tree. It still stops before any
persistent repository change.

## Position In The Loop

The completed stages before Stage 2C are:

- Stage 1: AI review
- Stage 2A: fix proposal generation
- Stage 2B: human approval record creation

Stage 2C-A takes these inputs and stops at preflight:

```text
Validated Fix Proposal
+ Valid Approval Record
+ current pull request HEAD match
+ live proposal, approval, and validation labels
    |
    v
Preflight Result
    |
    v
Sticky Comment
    |
    v
Stop
```

Stage 2C-B is split into two runtime stages:

- Stage 2C-B1: ephemeral sandbox patch apply and diff verification,
- Stage 2C-B2: approved trusted test execution in the same ephemeral sandbox model.

Stage 2C-B1 has this boundary:

```text
Validated Fix Proposal
+ Valid Approval Record
+ PRECHECK_PASSED result
+ current pull request HEAD match
+ live proposal, approval, validation, and apply labels
    |
    v
Ephemeral Sandbox Checkout
    |
    v
git apply --check
    |
    v
Patch Apply
    |
    v
Changed File And Diff Binding
    |
    v
Sandbox Apply Result
    |
    v
Stop
```

Stage 2C-A does not checkout source, run patch applicability checks,
apply patches, or run tests. Stage 2C-B1 checks out only an ephemeral
sandbox worktree and applies the patch there. Stage 2C-B1 does not run
tests. Stage 2C does not commit, push, update a pull request branch,
create a branch, merge, approve a pull request, publish a package,
deploy, or write through the GitHub Contents API.

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

Stage 2C-B1 additionally requires:

- preflight validation ID,
- preflight result hash,
- apply request actor,
- apply request actor repository permission,
- patch file hash,
- planned test plan hash,
- exact checkout SHA.

Artifacts and comments are not trusted by themselves. Each input must be
validated against live pull request state and default-branch policy.

## Live Gate

Artifact presence alone must not start Stage 2C. Before any sandbox is
created, Stage 2C-A re-checks these preflight gates:

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
- `ai-fix-apply-sandbox` label is present for Stage 2C-B1,
- approval actor currently has repository `admin` or `maintain`,
- validation request actor currently has repository `admin` or
  `maintain`,
- apply request actor currently has repository `admin` or `maintain`,
- trusted policy hash matches,
- proposal schema validation succeeds,
- approval schema validation succeeds,
- result schema version is trusted,
- protected path checks pass,
- patch target blob SHA checks pass,
- requested test IDs are listed in trusted policy,
- proposal artifact and approval artifact provenance match,
- Stage 1 finding IDs match the proposal findings addressed.

Any failed gate prevents sandbox creation. Stage 2C-A records
`PRECHECK_PASSED` only when these gates pass. Missing, expired, or
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

The Stage 2C-A collector starts only when `ai-fix-validate` is added.
It does not process `ai-fix-proposal`, `ai-fix-approved`, unrelated
labels, label removal, or pull request `synchronize` events. The
validator still requires all three live labels as a gate.

Stage 2C-B1 starts only when a human adds:

```text
ai-fix-apply-sandbox
```

Adding `ai-fix-validate` must not automatically start patch apply. The
Stage 2C-B1 validator still requires all four live labels as a gate.

| Label | Starts Collector | Live Gate References | Actor Requirement | Removal | HEAD Change |
| --- | --- | --- | --- | --- | --- |
| `ai-fix-proposal` | Stage 2A only | Stage 2A, Stage 2C-A, Stage 2C-B1 | trusted PR author | no collector work | stale proposal |
| `ai-fix-approved` | Stage 2B only | Stage 2B, Stage 2C-A, Stage 2C-B1 | repo `admin` or `maintain` | no collector work | stale approval |
| `ai-fix-validate` | Stage 2C-A only | Stage 2C-A, Stage 2C-B1 | repo `admin` or `maintain` | no collector work | stale preflight |
| `ai-fix-apply-sandbox` | Stage 2C-B1 only | Stage 2C-B1 | repo `admin` or `maintain` | no collector work | stale sandbox apply |

The sandbox validator accepts workflow runs only from `Sandbox
Validation Request Collector`. A manifest `request_stage` of
`SANDBOX_VALIDATION_REQUEST` is required, but the manifest stage value
does not authenticate the artifact without the trusted workflow_run
source and artifact provenance.

## Sandbox Model

Stage 2C-A deliberately does not create the sandbox. Its preflight model
is:

1. Read the trusted validation request artifact.
2. Re-read the live pull request, labels, and HEAD.
3. Select and revalidate the latest matching fix proposal artifact.
4. Select and revalidate the latest matching approval record artifact.
5. Re-check approval and validation actors' repository permissions.
6. Verify target blob SHAs through GitHub read APIs.
7. Validate patch metadata without applying the patch.
8. Validate `tests_recommended` as trusted test IDs only.
9. Re-read the live pull request HEAD before result generation.
10. Write a preflight result artifact and sticky comment.

Stage 2C-B1 uses this sandbox model:

1. Verify a matching `PRECHECK_PASSED` preflight result.
2. Checkout the current pull request HEAD as detached HEAD.
2. Confirm the sandbox working tree is clean.
3. Reject submodules, or allow them only through explicit trusted policy.
4. Inspect symlinks and reject any target escape risk.
5. Confirm each patch target file blob SHA.
6. Materialize the patch under runner temporary storage.
7. Run fixed `git apply --check` argv in the sandbox.
8. Apply the patch in the sandbox with fixed argv.
9. Re-enumerate changed files.
10. Confirm changed files exactly match proposal files.
11. Re-run protected path checks.
12. Reject unexpected file creation, deletion, rename, or mode change.
13. Verify final diff binding.
14. Generate the apply result artifact.
15. Destroy the sandbox.

The sandbox is disposable. Its modified working tree is expected after a
successful apply, but those modifications must not persist outside the
job.

Stage 2C-B1 does not execute trusted test command mappings. That belongs
to Stage 2C-B2.

## Stage 2C-B1 Patch Apply Runtime

The fixed apply commands are:

```text
git apply --check --verbose --recount --whitespace=error-all <fixed patch path>
git apply --verbose --recount --whitespace=error-all <fixed patch path>
```

The proposal cannot add options. `--unsafe-paths`, `--3way`, `--reject`,
`--index`, `--cached`, path includes/excludes, fuzzy fallback, `patch`,
`git am`, and manual file rewrite fallbacks are forbidden.

Stage 2C-B1 records:

- apply request actor and repository permission,
- preflight validation ID and preflight result hash,
- exact checkout SHA,
- detached HEAD state,
- credential persistence check,
- patch file hash,
- `git apply --check` result,
- patch apply result,
- expected and actual changed files,
- resulting file hashes,
- final diff binding,
- planned test IDs,
- `tests_executed` as empty,
- sandbox cleanup and destruction status.

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
content can request trusted test IDs only. Human-facing explanation
belongs in `tests_rationale`, which is never used as execution input.
Trusted default-branch policy maps the IDs to fixed command argv arrays.

Stage 2A proposal artifacts that contain free-form `tests_recommended`
strings are not executable Stage 2C inputs. Stage 2C must fail closed
instead of translating natural language, interpreting shell text, or
falling back to a broader alias allowlist. Stage 2C must create
`tests_requested` from the trusted ID set, not from rationale text.
In the validation result schema, each requested test is represented as a
test evidence record containing the trusted test ID, requested flag,
executed flag, status, exit code, duration, and bounded log excerpt.
This prevents a successful validation from relying only on a standalone
boolean claim that requested tests were executed.

Initial trusted test IDs:

- `unit`,
- `stage2c-targeted`,
- `workflow-checkers`,
- `compileall`,
- `stage2c-b1-clamp`.

Each ID must also exist in the trusted sandbox-test command registry.
The registry maps IDs to fixed `python -m unittest <trusted module>`
argv arrays. It must not contain natural-language aliases.

Stage 2C-A and Stage 2C-B1 only validate or carry these IDs. They do
not execute any test command. Stage 2C-B2 is the first stage that may
execute trusted test IDs.

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

`PRECHECK_PASSED`:

- Stage 2C-A live gate passed,
- proposal and approval artifacts validated,
- target blob metadata matches,
- patch metadata is acceptable,
- tests are validated as trusted IDs,
- no checkout, patch applicability check, patch apply, or test execution
  occurred.

`SUCCESS`:

- patch applied,
- expected files only changed,
- all required tests passed.

`PATCH_REJECTED`:

- patch applicability check failed,
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
- `sandbox_checkout_performed`: is `false` for Stage 2C-A and `true`
  for Stage 2C-B1,
- `patch_check_performed`: is `false` for Stage 2C-A and `true` for
  Stage 2C-B1,
- `patch_applied`: is `false` for Stage 2C-A and `true` for
  Stage 2C-B1 success,
- `test_execution_performed`: is `false` for Stage 2C-A and
  Stage 2C-B1.

This avoids treating expected sandbox modifications as persistent
repository writes.

The result also records proposal artifact provenance, approval artifact
provenance, schema versions, approval actor repository permission, and
the test plan hash so the validation can be audited without trusting a
comment body. Artifact provenance includes the repository, pull request
number, workflow run, and head SHA so proposal and approval artifacts
remain bound to the reviewed PR.

The result also records:

- whether all requested trusted test IDs were executed,
- whether actual changed files matched expected files.

The schema draft includes status-conditional invariants. `SUCCESS`
requires patch checks, patch apply, protected path checks, and blob SHA
checks to pass; all requested trusted test IDs to be executed; all
recorded test results to pass; actual changed files to match expected
files; no persistent repository modification; no commit, push, or merge;
and sandbox destruction to be reported. `PRECHECK_PASSED` requires
`phase: PREFLIGHT`, skipped patch check, skipped patch apply, no
executed tests, no sandbox checkout, no persistent write, no commit, no
push, and no merge. `APPLY_PASSED` requires `phase: SANDBOX_APPLY`,
exact checkout, fixed `git apply --check`, fixed `git apply`, final diff
binding, sandbox cleanup, no test execution, no persistent write, no
commit, no push, and no merge. Non-success terminal statuses must carry
a matching `failure_class`.

## Validation ID

`validation_id` should be a deterministic hash prefix derived from:

- proposal ID,
- proposal hash,
- approval ID,
- approval record hash,
- head SHA,
- policy hash,
- test plan,
- for Stage 2C-B1, preflight validation ID and hash, apply request
  actor, and patch file hash.

`started_at` and `completed_at` must not be part of the validation ID.
The same proposal, approval record, HEAD, policy, test plan, preflight
result, apply request actor, and patch hash should produce the same
Stage 2C-B1 apply ID.

## Artifact Design

Stage 2C-A uploads a `sandbox-validation-preflight` artifact. Stage
2C-B1 uploads a `sandbox-apply-result` artifact.

Allowed artifact contents:

- result JSON,
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

Stage 2C-B1 uses a separate sticky comment marker:

```html
<!-- namma-ai-sandbox-apply -->
```

The Stage 2C-B1 comment displays apply ID, proposal ID, approval ID,
preflight validation ID, HEAD SHA, requester, checkout SHA, detached HEAD
status, patch check, patch apply, changed files, diff binding, planned
tests, and explicit `No` values for test execution, persistent
repository modification, commit, push, and merge.

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

The Stage 2C static checkers verify:

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
- `ai-fix-validate` is required for preflight,
- `ai-fix-apply-sandbox` is required for Stage 2C-B1,
- exact SHA checkout for Stage 2C-B1,
- `persist-credentials: false`,
- fixed `git apply` argv,
- no recommended test execution in Stage 2C-B1.

`scripts/check_sandbox_validation_workflow.py` validates Stage 2C-A.
`scripts/check_sandbox_apply_workflow.py` validates Stage 2C-B1.
`scripts/check_sandbox_test_workflow.py` validates Stage 2C-B2.

## Unit Test Matrix

Runtime implementation should add these tests.

Normal cases:

- valid proposal, valid approval, valid labels, same HEAD,
- patch check and apply succeed for Stage 2C-B1,
- allowed tests succeed for Stage 2C-B2,
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

## Non-Goals After PR #31

PR #31 still did not implement:

- Stage 2C-B2 test execution runtime,
- repository write,
- commit automation,
- push automation,
- merge automation,
- workflow permission changes,
- secret changes,
- Stage 2C E2E.

## Stage 2C-B2 Sandbox Tests

Stage 2C-B2 is the first runtime that executes approved recommended
tests. It reuses the same trust chain as Stage 2C-B1:

```text
Proposal artifact
+ Approval record artifact
+ Preflight result artifact
+ Sandbox apply result artifact
+ live labels and current HEAD
-> exact detached sandbox checkout
-> approved patch apply
-> approved tests only
-> sandbox test result artifact
-> sticky comment
-> sandbox destruction
```

The trigger label is:

```text
ai-fix-test-sandbox
```

The live gate requires all previous labels plus this label:

- `ai-fix-proposal`,
- `ai-fix-approved`,
- `ai-fix-validate`,
- `ai-fix-apply-sandbox`,
- `ai-fix-test-sandbox`.

Adding `ai-fix-apply-sandbox` still starts only Stage 2C-B1. Stage
2C-B2 starts only when `ai-fix-test-sandbox` is added.

### Command Model

Stage 2C-B2 never treats `tests_recommended` as shell text. The
proposal supplies only trusted test IDs. Human-facing rationale stays in
`tests_rationale`, and Stage 2C-B2 ignores that field when building
commands. The trusted `.github/codex/sandbox-test-policy.yml` maps
simple trusted IDs to fixed argv arrays.

Initial executable allowance is intentionally narrow:

- `python3`,
- `python`,
- `-m unittest`.

The runtime rejects shell strings, `shell=true`, inline Python code,
path traversal, absolute paths, wildcards, command separators, package
installers, Git commands, network download tools, and unknown runners.
The test process receives only allowlisted environment variables and a
trusted fixed `PYTHONPATH` when a trusted support module is required.
The process that spawns untrusted sandbox tests must not receive
`GITHUB_TOKEN` or other repository credentials. Live HEAD checks are
performed before sandbox checkout and again before sticky comment
publication by trusted workflow steps that do not execute PR code.
Trusted support tests execute with the trusted support directory as the
process working directory and the sandbox worktree appended after that
directory in `PYTHONPATH`, so a PR cannot shadow a trusted support test
module by adding a same-named file at repository root.

### Runtime Limits

The sandbox test policy defines:

- command timeout: 120 seconds,
- total timeout: 300 seconds,
- stdout limit: 1 MiB per command,
- stderr limit: 1 MiB per command,
- `network_isolation_enforced: false`.

The workflow does not claim network isolation when it cannot enforce it
on GitHub-hosted runners. Instead it avoids package installation,
network download tools, external tokens, and arbitrary executables.

### Result Artifact

Stage 2C-B2 writes `sandbox-test-result.schema.json` artifacts with
phase `SANDBOX_TEST`. Status values include:

- `TESTS_PASSED`,
- `TESTS_FAILED`,
- `TESTS_TIMEOUT`,
- `TEST_COMMAND_REJECTED`,
- `TEST_ENVIRONMENT_REJECTED`,
- `TEST_OUTPUT_LIMIT`,
- `ARTIFACT_INVALID`,
- `BINDING_MISMATCH`,
- `PATCH_APPLY_FAILED`,
- `INTERNAL_ERROR`.

The result records proposal, approval, preflight, and apply bindings,
test commands, exit codes, durations, stdout and stderr hashes,
truncation flags, generated-file checks, cleanup state, and explicit
`false` values for persistent repository modification, commit, push,
and merge.

The sticky comment marker is:

```html
<!-- namma-ai-sandbox-test -->
```

The comment displays the status and high-level evidence only. Full
stdout and stderr are stored in the short-lived artifact, subject to
byte limits, and are not copied into the pull request comment.

## Non-Goals After Stage 2C-B2

Stage 2C-B2 still does not implement:

- repository branch modification,
- PR branch update,
- commit automation,
- push automation,
- merge automation,
- code suggestion APIs,
- test failure repair,
- proposal regeneration,
- approval regeneration,
- package installation,
- Stage 2D,
- Stage 3.
