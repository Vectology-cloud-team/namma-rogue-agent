#!/usr/bin/env python3
"""Validate the Stage 1 architect-review workflow safety properties."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
COLLECTOR_WORKFLOW_PATH = (
    REPO_ROOT / ".github" / "workflows" / "architect-review-collect.yml"
)
REVIEWER_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "architect-review.yml"
WORKFLOW_PATH = REVIEWER_WORKFLOW_PATH
PROMPT_PATH = REPO_ROOT / ".github" / "codex" / "prompts" / "architect-review.md"
POLICY_PATH = REPO_ROOT / ".github" / "codex" / "review-policy.yml"
DOC_PATH = REPO_ROOT / "docs" / "ai-development-loop.md"

EXPECTED_REPOSITORY = "Vectology-cloud-team/namma-rogue-agent"
COLLECTOR_WORKFLOW_NAME = "Architect Review Collect"
PROMPT_VERSION = "architect-review-v1"
FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
ACTION_USES_RE = re.compile(
    r"(?m)^\s*uses:\s+([^@\s]+)@([^\s#]+)(?:\s+#\s*([^\s]+))?\s*$"
)
GITHUB_SCRIPT_RESERVED_REDECLARATION_RE = re.compile(
    r"(?m)^\s*(?:const|let|var)\s+(?:core|github|context)\s*="
)
PINNED_ACTIONS = {
    "actions/checkout": {
        "sha": "93cb6efe18208431cddfb8368fd83d5badbf9bfd",
        "version": "v5",
    },
    "actions/upload-artifact": {
        "sha": "ea165f8d65b6e75b540449e92b4886f43607fa02",
        "version": "v4",
    },
    "openai/codex-action": {
        "sha": "52fe01ec70a42f454c9d2ebd47598f9fd6893d56",
        "version": "v1",
    },
}
REQUIRED_ACTIONS = {
    "actions/checkout",
    "actions/upload-artifact",
    "openai/codex-action",
}


@dataclass(frozen=True)
class CheckResult:
    label: str
    passed: bool
    detail: str = ""


def _contains(text: str, needle: str) -> bool:
    return needle in text


def _regex(text: str, pattern: str) -> bool:
    return re.search(pattern, text, flags=re.MULTILINE) is not None


def _job_section(text: str, job_name: str) -> str:
    marker = f"  {job_name}:"
    start = text.find(marker)
    if start == -1:
        return ""
    next_job = re.search(r"\n  [A-Za-z0-9_-]+:\n", text[start + len(marker) :])
    if next_job is None:
        return text[start:]
    return text[start : start + len(marker) + next_job.start()]


def _add(results: list[CheckResult], label: str, passed: bool, detail: str = "") -> None:
    results.append(CheckResult(label=label, passed=passed, detail=detail))


def action_uses(text: str) -> list[tuple[str, str, str | None]]:
    return [
        (match.group(1), match.group(2), match.group(3))
        for match in ACTION_USES_RE.finditer(text)
    ]


def all_workflow_text(collector_text: str, reviewer_text: str) -> str:
    return collector_text + "\n" + reviewer_text


def existing_comment_block(post_job: str) -> str:
    start = post_job.find("const existing")
    if start == -1:
        return ""
    end = post_job.find("if (existing)", start)
    if end == -1:
        return post_job[start:]
    return post_job[start:end]


def check_action_pinning(text: str) -> list[CheckResult]:
    results: list[CheckResult] = []
    uses_entries = action_uses(text)
    _add(
        results,
        "all actions use full commit SHAs",
        bool(uses_entries)
        and all(FULL_SHA_RE.fullmatch(ref) for _, ref, _ in uses_entries),
    )
    _add(
        results,
        "only allowed actions are used",
        all(action in PINNED_ACTIONS for action, _, _ in uses_entries),
    )
    for action, expected in PINNED_ACTIONS.items():
        matching = [entry for entry in uses_entries if entry[0] == action]
        if action in REQUIRED_ACTIONS:
            _add(results, f"{action} action is used", bool(matching))
        _add(
            results,
            f"{action} is pinned to reviewed SHA",
            action not in REQUIRED_ACTIONS
            or (bool(matching) and all(entry[1] == expected["sha"] for entry in matching)),
        )
        _add(
            results,
            f"{action} keeps version comment",
            action not in REQUIRED_ACTIONS
            or (bool(matching) and all(entry[2] == expected["version"] for entry in matching)),
        )
    return results


def check_no_dangerous_automation(text: str) -> list[CheckResult]:
    results: list[CheckResult] = []
    _add(results, "does not use pull_request_target", "pull_request_target" not in text)
    _add(results, "does not push to main", not _regex(text, r"(?m)^\s*push:\s*$"))
    _add(results, "does not run git push", "git push" not in text)
    _add(results, "does not run git merge", "git merge" not in text)
    _add(
        results,
        "does not force push",
        "force-with-lease" not in text and "force-push" not in text,
    )
    return results


def check_collector_text(text: str) -> list[CheckResult]:
    results: list[CheckResult] = []
    collect_job = _job_section(text, "collect")

    _add(results, "collector workflow name exists", f"name: {COLLECTOR_WORKFLOW_NAME}" in text)
    _add(results, "collector uses pull_request trigger", "pull_request:" in text)
    for event_type in ("opened", "synchronize", "reopened", "ready_for_review"):
        _add(results, f"collector includes {event_type} event", f"- {event_type}" in text)
    _add(results, "collector has PR concurrency group", "architect-review-collect-${{ github.event.pull_request.number }}" in text)
    _add(results, "collector job exists", bool(collect_job))
    _add(results, "collector has only contents read permission", _regex(collect_job, r"permissions:\n\s+contents: read"))
    _add(results, "collector has no write permission", ": write" not in collect_job)
    _add(results, "collector has no secrets references", "secrets." not in collect_job)
    _add(results, "collector has no OpenAI API key", "OPENAI_API_KEY" not in collect_job)
    _add(results, "collector does not run Codex action", "openai/codex-action" not in collect_job)
    _add(results, "collector does not run repository scripts", " scripts/" not in collect_job and " scripts\\" not in collect_job)
    _add(results, "collector does not run tests", "unittest" not in collect_job and "pytest" not in collect_job)
    _add(results, "collector checks out PR merge ref", "ref: refs/pull/${{ github.event.pull_request.number }}/merge" in collect_job)
    _add(results, "collector checkout does not persist credentials", "persist-credentials: false" in collect_job)
    _add(results, "collector writes manifest", '"manifest.json"' in collect_job)
    _add(results, "collector writes review diff", '"review.diff"' in collect_job)
    _add(results, "collector has max diff bytes", 'MAX_DIFF_BYTES: "200000"' in collect_job)
    _add(results, "collector has max changed files", 'MAX_CHANGED_FILES: "200"' in collect_job)
    _add(results, "collector has max artifact bytes", 'MAX_ARTIFACT_BYTES: "250000"' in collect_job)
    _add(results, "collector omits binary files", "binary_files_omitted" in collect_job)
    _add(results, "collector does not shell-expand PR title", "github.event.pull_request.title" not in collect_job)
    _add(results, "collector uploads review input artifact", "actions/upload-artifact@" in collect_job)
    return results


def check_reviewer_text(text: str) -> list[CheckResult]:
    results: list[CheckResult] = []
    review_job = _job_section(text, "review")
    post_job = _job_section(text, "post_feedback")
    existing_block = existing_comment_block(post_job)
    retry_script_text = load_text(REPO_ROOT / "scripts" / "architect_review_retry.py")

    _add(results, "reviewer uses workflow_run trigger", "workflow_run:" in text)
    _add(results, "reviewer watches collector workflow", f"- {COLLECTOR_WORKFLOW_NAME}" in text)
    _add(results, "reviewer checks collector success", "github.event.workflow_run.conclusion == 'success'" in text)
    _add(results, "reviewer checks workflow name", f"github.event.workflow_run.name == '{COLLECTOR_WORKFLOW_NAME}'" in text)
    _add(results, "reviewer checks source event type", "github.event.workflow_run.event == 'pull_request'" in text)
    _add(results, "reviewer checks workflow repository", "github.event.workflow_run.repository.full_name == github.repository" in text)
    _add(results, "reviewer checks expected repository", f"github.repository == '{EXPECTED_REPOSITORY}'" in text)
    _add(results, "review job exists", bool(review_job))
    _add(results, "post_feedback job exists", bool(post_job))
    _add(results, "reviewer can read actions artifacts", "actions: read" in review_job)
    _add(results, "reviewer can read contents", "contents: read" in review_job)
    _add(results, "reviewer can read pull requests", "pull-requests: read" in review_job)
    _add(results, "reviewer checks out trusted control plane", "path: reviewer-control" in review_job)
    _add(results, "reviewer loads trusted review policy", "architect_review_retry.py load-policy" in review_job)
    _add(results, "reviewer reads policy from reviewer control plane", "reviewer-control/.github/codex/review-policy.yml" in review_job)
    _add(results, "reviewer downloads collector artifact", "architect_review_retry.py download-artifact" in review_job)
    _add(results, "reviewer validates manifest schema", "EXPECTED_MANIFEST_KEYS" in retry_script_text and "schema_version" in retry_script_text)
    _add(results, "reviewer validates repository identity", "REPOSITORY_MISMATCH" in retry_script_text)
    _add(results, "reviewer rejects forks", "Skipping fork or external pull request." in retry_script_text)
    _add(results, "reviewer rejects bots", "Skipping bot-authored pull request." in retry_script_text)
    _add(results, "reviewer rejects drafts", "Skipping draft pull request." in retry_script_text)
    _add(results, "reviewer checks author association", "ALLOWED_AUTHOR_ASSOCIATIONS" in retry_script_text)
    _add(results, "reviewer checks current head SHA", 'manifest["head_sha"] != pull["head"]["sha"]' in retry_script_text)
    _add(results, "reviewer checks current base SHA", 'manifest["base_sha"] != pull["base"]["sha"]' in retry_script_text)
    _add(results, "reviewer validates live PR file list", "validate_live_pr_files" in retry_script_text and "iter_live_pr_files" in retry_script_text)
    _add(results, "reviewer refreshes review diff from GitHub", "application/vnd.github.v3.diff" in retry_script_text and "refresh_review_diff_from_github" in retry_script_text)
    _add(results, "reviewer fails stale artifact without comment", "STALE_ARTIFACT" in retry_script_text)
    _add(results, "reviewer validates artifact paths", "PATH_TRAVERSAL" in retry_script_text)
    _add(results, "reviewer validates artifact size", "MAX_ARTIFACT_BYTES" in retry_script_text)
    _add(results, "reviewer enforces policy diff budget", "budget.diff_bytes > policy.max_diff_bytes" in retry_script_text)
    _add(results, "reviewer enforces policy file budget", "budget.reviewed_files > policy.max_changed_files" in retry_script_text)
    _add(results, "reviewer enforces prompt budget", "prompt_bytes > max_prompt_bytes" in retry_script_text)
    _add(results, "reviewer applies exclude policy", "filter_unified_diff" in retry_script_text and "path_matches_exclude" in retry_script_text)
    _add(results, "reviewer writes policy job summary", "policy_summary" in retry_script_text and "review_input_summary" in retry_script_text)
    _add(
        results,
        "github-script does not redeclare injected identifiers",
        not GITHUB_SCRIPT_RESERVED_REDECLARATION_RE.search(review_job),
    )
    _add(results, "reviewer uses retry helper", "architect_review_retry.py" in review_job)
    _add(results, "reviewer validates input with retry helper", "architect_review_retry.py validate-review-input" in review_job)
    _add(results, "reviewer uses trusted base checkout", "ref: ${{ steps.validate.outputs.base_sha }}" in review_job)
    _add(results, "trusted prompt is verified", "architect_review_retry.py verify-prompt" in review_job)
    _add(results, "reviewer uses OpenAI API key", "OPENAI_API_KEY" in review_job and "openai-api-key: ${{ secrets.OPENAI_API_KEY }}" in review_job)
    _add(results, "Codex attempt 1 exists", "id: codex_attempt_1" in review_job)
    _add(results, "Codex attempt 2 exists", "id: codex_attempt_2" in review_job)
    _add(results, "Codex attempt 3 exists", "id: codex_attempt_3" in review_job)
    _add(results, "Codex failures continue for retry", "continue-on-error: true" in review_job)
    _add(results, "Codex failures are classified before retry", "classify-codex-attempt" in review_job and "codex_classify_1" in review_job)
    _add(results, "Codex retry conditions use classification", "steps.codex_classify_1.outputs.should_retry == 'true'" in review_job and "steps.codex_classify_2.outputs.should_retry == 'true'" in review_job)
    _add(results, "Codex retry waits are explicit", "sleep-before-retry --attempt 2" in review_job and "sleep-before-retry --attempt 3" in review_job)
    _add(results, "Codex result is finalized", "architect_review_retry.py finalize-codex" in review_job)
    _add(results, "uses official Codex action", "openai/codex-action@52fe01ec70a42f454c9d2ebd47598f9fd6893d56 # v1" in review_job)
    _add(results, "uses trusted base prompt file", "prompt-file: ${{ github.workspace }}/trusted-base/.github/codex/prompts/architect-review.md" in review_job)
    _add(results, "sets Codex model from policy", "model: ${{ steps.policy.outputs.model }}" in review_job)
    _add(results, "sets Codex effort from policy", "effort: ${{ steps.policy.outputs.effort }}" in review_job)
    _add(results, "uses read-only permission profile", 'permission-profile: ":read-only"' in review_job)
    _add(results, "uses drop-sudo safety strategy", "safety-strategy: drop-sudo" in review_job)
    _add(results, "post_feedback checks out trusted control plane", "path: reviewer-control" in post_job)
    _add(results, "post_feedback has no OpenAI API key", "OPENAI_API_KEY" not in post_job)
    _add(results, "post_feedback only runs after successful review job", "needs.review.result == 'success'" in post_job)
    _add(results, "post_feedback runs for review or policy skip comments", "needs.review.outputs.should_comment == 'true'" in post_job)
    _add(results, "post_feedback can write PR comments", _regex(post_job, r"permissions:\n\s+issues: write\n\s+pull-requests: write"))
    _add(results, "post_feedback uses retry helper", "architect_review_retry.py post-comment" in post_job)
    _add(results, "post_feedback validates live head before comment", "validate_comment_target" in retry_script_text and "pull request head changed before comment publication" in retry_script_text)
    _add(results, "comment marker exists", "<!-- namma-ai-architect-review -->" in retry_script_text)
    _add(results, "comment heading exists", "## Automated Architect Review" in retry_script_text)
    _add(results, "comment states AI review is not merge judgment", "does not replace human merge judgment" in retry_script_text)
    _add(results, "comment includes reviewed SHA", "Reviewed commit:" in retry_script_text)
    _add(results, "comment links workflow run", "actions/runs/{workflow_run_id}" in retry_script_text)
    _add(results, "comment includes prompt version", "Prompt version:" in retry_script_text)
    _add(results, "comment includes verdict", "Verdict:" in retry_script_text)
    _add(results, "comment includes policy metadata", "### Review Policy" in retry_script_text and "Review:" in retry_script_text)
    _add(results, "deduplicates by marker", "COMMENT_MARKER in comment" in retry_script_text)
    _add(results, "sticky comment ignores reviewed SHA for matching", "reviewedSha" not in existing_block)
    return results


def check_prompt_text(text: str) -> list[CheckResult]:
    results: list[CheckResult] = []
    _add(results, "prompt version exists", PROMPT_VERSION in text)
    _add(results, "prompt defines trust boundary", "## Trust Boundary" in text)
    _add(results, "prompt treats review input as untrusted", "review-input/review.diff" in text and "untrusted" in text)
    _add(results, "prompt forbids executing PR content", "Do not execute files" in text)
    _add(results, "prompt says read-only", "read-only review" in text)
    _add(results, "prompt forbids modifications", "Do not modify files" in text)
    for verdict in (
        "VERDICT: APPROVE",
        "VERDICT: CHANGES_REQUESTED",
        "VERDICT: HUMAN_DECISION_REQUIRED",
    ):
        _add(results, f"prompt includes {verdict}", verdict in text)
    for section in (
        "SUMMARY",
        "BLOCKING FINDINGS",
        "NON-BLOCKING FINDINGS",
        "REQUIRED TESTS",
        "SCOPE VIOLATIONS",
        "HUMAN DECISIONS",
    ):
        _add(results, f"prompt includes {section}", section in text)
    return results


def check_policy_text(text: str) -> list[CheckResult]:
    results: list[CheckResult] = []
    _add(results, "policy sets model", _regex(text, r"(?m)^model:\s*\S+"))
    _add(results, "policy sets reasoning effort", _regex(text, r"(?m)^\s+effort:\s*\S+"))
    for key in ("max_changed_files", "max_diff_bytes", "max_prompt_bytes"):
        _add(results, f"policy sets {key}", _regex(text, rf"(?m)^\s+{key}:\s*[1-9][0-9]*"))
    _add(results, "policy defines exclude list", "exclude:" in text and "- " in text)
    return results


def check_doc_text(text: str) -> list[CheckResult]:
    results: list[CheckResult] = []
    _add(results, "docs describe Stage 1", "Stage 1: Automated Architect Review" in text)
    _add(results, "docs describe bootstrap PR", "bootstrap pull request" in text and "canary pull request" in text)
    _add(results, "docs describe two-stage control plane", "unprivileged collector" in text and "privileged reviewer" in text)
    _add(results, "docs describe Stage 2", "Stage 2 Plan" in text)
    _add(results, "docs describe stop methods", "Stop Methods" in text)
    _add(results, "docs mention API billing", "API Billing" in text)
    _add(results, "docs state no pull_request_target", "Neither workflow uses `pull_request_target`" in text)
    _add(results, "docs state no auto-fix", "does not implement auto-fix behavior" in text)
    _add(results, "docs explain fail-closed prompt behavior", "fails closed" in text)
    _add(results, "docs explain sticky comment", "deduplicates comments by marker only" in text)
    _add(results, "docs mention full SHA action policy", "full commit SHAs" in text)
    _add(results, "docs describe review policy", "Stage 1.1-B: Reviewer Policy And Budget Control" in text)
    _add(results, "docs state policy is not Stage 2", "Policy retry and budget control are not Stage 2 automation" in text)
    _add(results, "docs describe budget skip", "Diff budget exceeded" in text and "Prompt budget exceeded" in text)
    return results


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def run_checks() -> list[CheckResult]:
    results: list[CheckResult] = []
    paths = (
        COLLECTOR_WORKFLOW_PATH,
        REVIEWER_WORKFLOW_PATH,
        PROMPT_PATH,
        POLICY_PATH,
        DOC_PATH,
    )
    for path in paths:
        _add(results, f"{path.relative_to(REPO_ROOT)} exists", path.exists())
    collector_text = load_text(COLLECTOR_WORKFLOW_PATH) if COLLECTOR_WORKFLOW_PATH.exists() else ""
    reviewer_text = load_text(REVIEWER_WORKFLOW_PATH) if REVIEWER_WORKFLOW_PATH.exists() else ""
    prompt_text = load_text(PROMPT_PATH) if PROMPT_PATH.exists() else ""
    policy_text = load_text(POLICY_PATH) if POLICY_PATH.exists() else ""
    doc_text = load_text(DOC_PATH) if DOC_PATH.exists() else ""

    combined_workflow_text = all_workflow_text(collector_text, reviewer_text)
    results.extend(check_no_dangerous_automation(combined_workflow_text))
    if combined_workflow_text:
        results.extend(check_action_pinning(combined_workflow_text))
    if collector_text:
        results.extend(check_collector_text(collector_text))
    if reviewer_text:
        results.extend(check_reviewer_text(reviewer_text))
    if prompt_text:
        results.extend(check_prompt_text(prompt_text))
    if policy_text:
        results.extend(check_policy_text(policy_text))
    if doc_text:
        results.extend(check_doc_text(doc_text))
    return results


def main() -> int:
    results = run_checks()
    failed = [result for result in results if not result.passed]
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        detail = f" - {result.detail}" if result.detail else ""
        print(f"{status}: {result.label}{detail}")
    if failed:
        print(f"{len(failed)} architect-review workflow checks failed.", file=sys.stderr)
        return 1
    print(f"{len(results)} architect-review workflow checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
