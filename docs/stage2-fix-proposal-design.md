# Stage 2 Fix Proposal Design

This document defines the Stage 2 guarded AI fix suggestion flow. It is
only a design and contract document. The repository does not yet contain
workflow code that generates, posts, applies, commits, pushes, or merges
AI fixes.

Stage 2 must preserve the Stage 1 trust boundary: pull request content,
review artifacts, proposal comments, and generated patches are
untrusted inputs unless they are validated against trusted policy from
the default-branch control plane.

## Non-Goals

PR #15 does not implement:

- repository file modification by AI,
- commits,
- pushes,
- branch creation,
- pull request creation,
- merges,
- shell command execution,
- test command execution,
- GitHub code suggestion posting,
- new write processing with repository secrets,
- Stage 2 workflow runtime wiring.

The only added artifacts are design documentation, a proposal schema, a
trusted fix policy draft, static validation, and tests.

## Stage Split

```text
Stage 2A: Fix Proposal
AI may generate a structured fix proposal.
The repository is not modified.

Stage 2B: Human Approval
A human reviews the proposal and explicitly approves it.
The repository is still not modified.

Stage 2C: Sandboxed Apply
An approved proposal may be applied inside an isolated sandbox.
The production branch is not committed or pushed.
```

Future commit or push behavior is out of Stage 2 scope. Any workflow
that writes commits, pushes branches, or merges pull requests belongs to
a later Stage 3 design.

## Label Gate

Stage 2A is closed by default. Proposal generation is eligible only when
the pull request has the trusted policy label:

```text
ai-fix-proposal
```

The label only permits fix proposal generation. It does not permit file
modification, patch application, commit, push, merge, approval, or
branch creation.

The proposal generator must not run when any of these are true:

- the label is absent,
- the pull request is draft,
- the pull request comes from a fork,
- the author is a bot,
- the author association is not `OWNER`, `MEMBER`, or `COLLABORATOR`,
- the head SHA is stale,
- the Stage 1 AI review did not finish successfully,
- the Stage 1 review has no blocking finding to address,
- the Stage 1 reviewed SHA differs from the current head SHA.

The label name is stored in `.github/codex/fix-policy.yml` so the future
runtime can read it from trusted control-plane state.

## Human Approval Gate

Stage 2B requires a separate explicit approval label:

```text
ai-fix-approved
```

The approval label is distinct from `ai-fix-proposal`. Approval is valid
only when all of these are true:

- `ai-fix-proposal` is still present,
- `ai-fix-approved` was applied by an `OWNER` or `MEMBER`,
- a trusted approval record exists for the label event,
- the latest proposal targets the current head SHA,
- the head SHA did not change after proposal generation,
- the approval record names the current proposal ID,
- the approval record includes the current head SHA,
- the approval record stores the proposal content hash,
- the approval record's hash matches the current proposal content,
- the proposal ID is unique for the reviewed head SHA.

`ai-fix-approved` only permits a future Stage 2C sandbox apply attempt.
It does not permit commit, push, merge, or production branch writes.

The label alone is not the approval binding. It is only the human intent
signal. A future verifier must bind that label event to a trusted
approval record captured from trusted proposal metadata, such as an
auditable proposal record or structured approval comment. That record
must include the proposal ID, target head SHA, proposal content hash,
approver identity, and approver association. If the binding record is
missing, ambiguous, stale, or has a mismatched hash, approval is invalid.

## Proposal Schema

Fix proposals use JSON. The schema declares the proposal shape and the
schema-expressible safety constraints:

```text
.github/codex/schemas/fix-proposal.schema.json
```

The schema is not sufficient as the trusted Stage 2 gate by itself. The
normative validator is the policy-aware validation layer represented in
this PR by `scripts/check_fix_proposal_design.py` and, in a future
runtime, by equivalent trusted control-plane code. That validator must
combine the schema, `.github/codex/fix-policy.yml`, patch parsing, target
blob checks, proposal hash checks, approval binding checks, and live PR
head checks before any sandbox apply attempt.

Each proposal records:

- `schema_version`,
- `proposal_id`,
- repository and pull request number,
- full `base_sha` and `head_sha`,
- source Stage 1 review comment ID,
- review timestamp,
- generator model, reasoning effort, and policy version,
- summary,
- findings addressed,
- changes,
- recommended tests,
- risks,
- `human_approval_required: true`.

Stage 2 initial design allows only:

```text
operation: modify
```

Create, delete, rename, binary patch, symlink, submodule, and file mode
changes are forbidden.

## Trusted Fix Policy

The trusted policy draft is:

```text
.github/codex/fix-policy.yml
```

The policy defines:

- proposal label,
- approval label,
- maximum changed files,
- maximum total patch bytes,
- maximum per-file patch bytes,
- allowed operations,
- protected paths.

The future Stage 2 runtime must read this policy from the default branch
or another explicitly trusted control-plane checkout. A pull request's
copy of this policy is review input only and must not configure that
same run.

## Protected Paths

The initial policy protects:

- `.git/**`,
- `.github/workflows/**`,
- `.github/actions/**`,
- `.github/codex/prompts/**`,
- `.github/codex/review-policy.yml`,
- `.github/codex/fix-policy.yml`,
- `.github/codex/schemas/**`,
- secret, credential, token, key, and certificate-like paths.

Proposal paths use repository-relative forward-slash paths only.
Backslashes, absolute paths, `..` path traversal, duplicate paths, and
mismatches between `changes.path` and the paths inside the unified diff
must be rejected.

## Proposal Lifecycle

```text
NOT_REQUESTED
    |
    | ai-fix-proposal label
    v
PROPOSAL_REQUESTED
    |
    | proposal generation succeeds
    v
PROPOSAL_READY
    |
    | ai-fix-approved label + trusted approval record
    | + proposal ID + head SHA + proposal hash match
    v
APPROVED_FOR_SANDBOX
    |
    | head SHA changes
    v
STALE
```

Forbidden transitions:

```text
PROPOSAL_READY -> repository commit is forbidden
PROPOSAL_READY -> push is forbidden
PROPOSAL_READY -> merge is forbidden
```

head SHA changes invalidate proposal and approval. A stale proposal must
not be applied, even in a sandbox, until a fresh proposal is generated
for the new head SHA and approved again.

## Patch Integrity

Each change records `original_blob_sha` for the target file. The future
sandbox apply step must compare that value with the actual target blob
before applying a patch. This prevents a proposal generated for one file
revision from being applied to another.

The proposal content hash is computed over the canonical JSON proposal.
Human approval must bind to the proposal ID, content hash, and head SHA
through a trusted approval record. Editing a proposal comment invalidates
approval unless the recomputed hash still matches the approval record.

Recommended tests are informational strings. They are not shell commands
to execute automatically. A future sandbox must validate any command
policy separately before running tests.

## GitHub Display Design

Future fix proposals use a separate sticky comment from the Stage 1
review comment.

Marker:

```html
<!-- namma-ai-fix-proposal -->
```

The comment should display:

- proposal ID,
- target head SHA,
- findings addressed,
- target files,
- patch summary,
- risks,
- recommended tests,
- proposal status,
- human approval required,
- approval binding status,
- a clear note that no file modification, commit, or push has occurred.

PR #15 does not implement comment posting. It only defines this marker
and display contract.

## Threat Model

| Threat | Mitigation |
| --- | --- |
| PR body or diff prompt injection | Treat review input and proposal input as untrusted. Trusted prompt and policy must come from default-branch control plane. |
| AI tries to modify workflow or prompt files | Protected paths reject `.github/workflows/**`, `.github/actions/**`, and `.github/codex/prompts/**`. |
| Stale proposal apply | Proposal and approval bind to full head SHA. Head SHA changes invalidate both. |
| Label permission confusion | `ai-fix-proposal` allows proposal generation only. `ai-fix-approved` is only an intent signal and must be paired with a trusted approval record. |
| Proposal tampering | Approval binds to proposal ID, proposal content hash, head SHA, approver identity, and approver association through the trusted approval record. |
| Patch path traversal | Absolute paths, `..`, and protected paths are rejected before any apply step exists. |
| Patch and target blob mismatch | `original_blob_sha` is required and must match the target blob before sandbox apply. |
| Duplicate or old approval reuse | Approval must name current proposal ID, hash, and head SHA in the trusted approval record. |
| Oversized patch resource use | Fix policy limits total patch bytes, per-file patch bytes, and changed file count. |
| AI includes unrequested changes | Proposal must address explicit Stage 1 findings and list every target path and rationale. |
| Recommended tests executed as shell without validation | Test recommendations are data only. Stage 2 design does not execute shell commands. |
| Proposal comment command injection | Proposal comments are display artifacts and are never interpreted as commands. |
| Fork or external contributor privilege escalation | Forks, bots, and untrusted author associations are ineligible for proposal generation. |

## Static Validation

`scripts/check_fix_proposal_design.py` validates the design artifacts and
sample proposal objects. It is read-only and does not call GitHub,
execute shell commands, apply patches, commit, push, or merge.

The tests in `tests/test_fix_proposal_design.py` verify the schema,
policy, proposal validation rules, stale approval invalidation, and the
absence of Stage 2 workflow wiring.
