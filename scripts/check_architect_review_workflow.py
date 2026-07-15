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
DOC_PATH = REPO_ROOT / "docs" / "ai-development-loop.md"

EXPECTED_REPOSITORY = "Vectology-cloud-team/namma-rogue-agent"
COLLECTOR_WORKFLOW_NAME = "Architect Review Collect"
PROMPT_VERSION = "architect-review-v1"
FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
ACTION_USES_RE = re.compile(
    r"(?m)^\s*uses:\s+([^@\s]+)@([^\s#]+)(?:\s+#\s*([^\s]+))?\s*$"
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
    "actions/download-artifact": {
        "sha": "634f93cb2916e3fdff6788551b99b062d0335ce0",
        "version": "v5",
    },
    "openai/codex-action": {
        "sha": "52fe01ec70a42f454c9d2ebd47598f9fd6893d56",
        "version": "v1",
    },
    "actions/github-script": {
        "sha": "f28e40c7f34bde8b3046d885e986cb6290c5673b",
        "version": "v7",
    },
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
        _add(results, f"{action} action is used", bool(matching))
        _add(
            results,
            f"{action} is pinned to reviewed SHA",
            bool(matching) and all(entry[1] == expected["sha"] for entry in matching),
        )
        _add(
            results,
            f"{action} keeps version comment",
            bool(matching) and all(entry[2] == expected["version"] for entry in matching),
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
    _add(results, "reviewer downloads collector artifact", "actions/download-artifact@" in review_job)
    _add(results, "reviewer validates manifest schema", "expectedKeys" in review_job and "manifest.schema_version" in review_job)
    _add(results, "reviewer validates repository identity", "Manifest repository does not match expected repository." in review_job)
    _add(results, "reviewer rejects forks", "Skipping fork or external pull request." in review_job)
    _add(results, "reviewer rejects bots", "Skipping bot-authored pull request." in review_job)
    _add(results, "reviewer rejects drafts", "Skipping draft pull request." in review_job)
    _add(results, "reviewer checks author association", "allowedAssociations" in review_job)
    _add(results, "reviewer checks current head SHA", "pr.head.sha !== manifest.head_sha" in review_job)
    _add(results, "reviewer skips stale artifact without comment", "Stale review artifact" in review_job and "should_review', 'false'" in review_job)
    _add(results, "reviewer validates artifact paths", "Artifact path traversal detected" in review_job)
    _add(results, "reviewer validates artifact size", "maxArtifactBytes" in review_job)
    _add(results, "reviewer validates diff size", "maxDiffBytes" in review_job)
    _add(results, "reviewer uses trusted base checkout", "ref: ${{ steps.validate.outputs.base_sha }}" in review_job)
    _add(results, "trusted prompt is verified", "Trusted architect-review prompt is missing from the base SHA." in review_job)
    _add(results, "reviewer uses OpenAI API key", "OPENAI_API_KEY" in review_job and "openai-api-key: ${{ secrets.OPENAI_API_KEY }}" in review_job)
    _add(results, "Codex step id is run_codex", "id: run_codex" in review_job)
    _add(results, "uses official Codex action", "openai/codex-action@52fe01ec70a42f454c9d2ebd47598f9fd6893d56 # v1" in review_job)
    _add(results, "uses trusted base prompt file", "prompt-file: ${{ github.workspace }}/trusted-base/.github/codex/prompts/architect-review.md" in review_job)
    _add(results, "does not set explicit model", "model:" not in review_job)
    _add(results, "does not set explicit effort", "effort:" not in review_job)
    _add(results, "uses read-only permission profile", 'permission-profile: ":read-only"' in review_job)
    _add(results, "uses drop-sudo safety strategy", "safety-strategy: drop-sudo" in review_job)
    _add(results, "post_feedback does not checkout repository", "actions/checkout" not in post_job)
    _add(results, "post_feedback has no OpenAI API key", "OPENAI_API_KEY" not in post_job)
    _add(results, "post_feedback only runs when should_review true", "needs.review.outputs.should_review == 'true'" in post_job)
    _add(results, "post_feedback can write PR comments", _regex(post_job, r"permissions:\n\s+issues: write\n\s+pull-requests: write"))
    _add(results, "comment marker exists", "<!-- namma-ai-architect-review -->" in post_job)
    _add(results, "comment heading exists", "## Automated Architect Review" in post_job)
    _add(results, "comment states AI review is not merge judgment", "does not replace human merge judgment" in post_job)
    _add(results, "comment includes reviewed SHA", "Reviewed commit:" in post_job)
    _add(results, "comment links workflow run", "actions/runs/${context.runId}" in post_job)
    _add(results, "comment includes prompt version", "Prompt version:" in post_job)
    _add(results, "comment includes verdict", "Verdict:" in post_job)
    _add(results, "deduplicates by marker", "comment.body.includes(marker)" in post_job)
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
    return results


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def run_checks() -> list[CheckResult]:
    results: list[CheckResult] = []
    paths = (COLLECTOR_WORKFLOW_PATH, REVIEWER_WORKFLOW_PATH, PROMPT_PATH, DOC_PATH)
    for path in paths:
        _add(results, f"{path.relative_to(REPO_ROOT)} exists", path.exists())
    collector_text = load_text(COLLECTOR_WORKFLOW_PATH) if COLLECTOR_WORKFLOW_PATH.exists() else ""
    reviewer_text = load_text(REVIEWER_WORKFLOW_PATH) if REVIEWER_WORKFLOW_PATH.exists() else ""
    prompt_text = load_text(PROMPT_PATH) if PROMPT_PATH.exists() else ""
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
