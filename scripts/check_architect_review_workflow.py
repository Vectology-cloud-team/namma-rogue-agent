#!/usr/bin/env python3
"""Validate the Stage 1 architect-review workflow safety properties."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "architect-review.yml"
PROMPT_PATH = REPO_ROOT / ".github" / "codex" / "prompts" / "architect-review.md"
DOC_PATH = REPO_ROOT / "docs" / "ai-development-loop.md"
FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
ACTION_USES_RE = re.compile(
    r"(?m)^\s*uses:\s+([^@\s]+)@([^\s#]+)(?:\s+#\s*([^\s]+))?\s*$"
)
PINNED_ACTIONS = {
    "actions/checkout": {
        "sha": "93cb6efe18208431cddfb8368fd83d5badbf9bfd",
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


def existing_comment_block(post_job: str) -> str:
    start = post_job.find("const existing")
    if start == -1:
        return ""
    end = post_job.find("if (existing)", start)
    if end == -1:
        return post_job[start:]
    return post_job[start:end]


def check_workflow_text(text: str) -> list[CheckResult]:
    results: list[CheckResult] = []
    review_job = _job_section(text, "review")
    post_job = _job_section(text, "post_feedback")
    uses_entries = action_uses(text)
    existing_block = existing_comment_block(post_job)

    _add(results, "uses pull_request trigger", _contains(text, "pull_request:"))
    _add(results, "does not use pull_request_target", "pull_request_target" not in text)
    for event_type in ("opened", "synchronize", "reopened", "ready_for_review"):
        _add(results, f"includes {event_type} event", _contains(text, f"- {event_type}"))

    _add(results, "does not push to main", not _regex(text, r"(?m)^\s*push:\s*$"))
    _add(results, "does not run git push", "git push" not in text)
    _add(results, "does not run git merge", "git merge" not in text)
    _add(results, "does not force push", "force-with-lease" not in text and "force-push" not in text)

    _add(results, "all actions use full commit SHAs", bool(uses_entries) and all(FULL_SHA_RE.fullmatch(ref) for _, ref, _ in uses_entries))
    _add(results, "only allowed actions are used", all(action in PINNED_ACTIONS for action, _, _ in uses_entries))
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

    _add(results, "has PR concurrency group", _contains(text, "group: architect-review-${{ github.event.pull_request.number }}"))
    _add(results, "cancels in-progress duplicate runs", _contains(text, "cancel-in-progress: true"))

    _add(results, "skips draft PRs", _contains(text, "github.event.pull_request.draft == false"))
    _add(results, "skips forks", _contains(text, "github.event.pull_request.head.repo.full_name == github.repository"))
    _add(results, "skips bot authors", _contains(text, "github.event.pull_request.user.type != 'Bot'"))
    for association in ("OWNER", "MEMBER", "COLLABORATOR"):
        _add(results, f"allows {association} author association", _contains(text, f"'{association}'"))

    _add(results, "review job exists", bool(review_job))
    _add(results, "post_feedback job exists", bool(post_job))
    _add(
        results,
        "review job has contents read permission",
        _regex(review_job, r"permissions:\n\s+contents: read"),
    )
    _add(
        results,
        "post_feedback can write PR comments",
        _regex(post_job, r"permissions:\n\s+issues: write\n\s+pull-requests: write"),
    )
    _add(results, "post_feedback does not checkout repository", "actions/checkout" not in post_job)
    _add(results, "post_feedback has no OpenAI API key", "OPENAI_API_KEY" not in post_job)

    _add(results, "checkout uses trusted base SHA", _contains(review_job, "ref: ${{ github.event.pull_request.base.sha }}"))
    _add(results, "trusted base checkout path exists", _contains(review_job, "path: trusted-base"))
    _add(results, "checkout uses PR merge ref", _contains(review_job, "ref: refs/pull/${{ github.event.pull_request.number }}/merge"))
    _add(results, "review target checkout path exists", _contains(review_job, "path: review-target"))
    _add(results, "checkout fetches full history", _contains(review_job, "fetch-depth: 0"))
    _add(results, "checkout does not persist credentials", _contains(review_job, "persist-credentials: false"))
    _add(results, "trusted prompt is verified", _contains(review_job, "Trusted architect-review prompt is missing from the base SHA."))

    _add(results, "Codex step id is run_codex", _contains(review_job, "id: run_codex"))
    _add(results, "uses official Codex action", _contains(review_job, "uses: openai/codex-action@52fe01ec70a42f454c9d2ebd47598f9fd6893d56 # v1"))
    _add(results, "passes OpenAI API key to Codex action", _contains(review_job, "openai-api-key: ${{ secrets.OPENAI_API_KEY }}"))
    _add(results, "uses read-only permission profile", _contains(review_job, 'permission-profile: ":read-only"'))
    _add(results, "uses drop-sudo safety strategy", _contains(review_job, "safety-strategy: drop-sudo"))
    _add(results, "uses trusted base prompt file", _contains(review_job, "prompt-file: ${{ github.workspace }}/trusted-base/.github/codex/prompts/architect-review.md"))
    _add(results, "uses review target working directory", _contains(review_job, "working-directory: ${{ github.workspace }}/review-target"))
    _add(results, "does not use PR prompt as prompt-file", "prompt-file: .github/codex/prompts/architect-review.md" not in review_job)
    _add(results, "does not set explicit model", "model:" not in review_job)
    _add(results, "does not set explicit effort", "effort:" not in review_job)

    dangerous_tokens = ("danger-full-access", "workspace-write", "unsafe")
    for token in dangerous_tokens:
        _add(results, f"does not use {token}", token not in review_job)

    codex_index = review_job.find("uses: openai/codex-action@52fe01ec70a42f454c9d2ebd47598f9fd6893d56 # v1")
    review_tail = review_job[codex_index:] if codex_index != -1 else review_job
    _add(results, "Codex action is last review job step", review_tail.count("\n      - name:") == 0)
    _add(
        results,
        "API key availability check logs only availability",
        _contains(review_job, "HAS_OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY != '' }}")
        and _contains(review_job, "OPENAI_API_KEY is not available"),
    )

    _add(results, "comment marker exists", _contains(post_job, "<!-- namma-ai-architect-review -->"))
    _add(results, "comment heading exists", _contains(post_job, "## Automated Architect Review"))
    _add(results, "comment states AI review is not merge judgment", _contains(post_job, "does not replace human merge judgment"))
    _add(results, "comment includes reviewed SHA", _contains(post_job, "Reviewed commit:"))
    _add(results, "comment links workflow run", _contains(post_job, "actions/runs/${context.runId}"))
    _add(results, "comment includes prompt version", _contains(post_job, "Prompt version:"))
    _add(results, "comment includes verdict", _contains(post_job, "Verdict:"))
    _add(results, "deduplicates by marker", _contains(post_job, "comment.body.includes(marker)"))
    _add(results, "sticky comment ignores reviewed SHA for matching", "reviewedSha" not in existing_block)

    return results


def check_prompt_text(text: str) -> list[CheckResult]:
    results: list[CheckResult] = []
    _add(results, "prompt version exists", "architect-review-v1" in text)
    _add(results, "prompt defines trust boundary", "## Trust Boundary" in text)
    _add(results, "prompt separates trusted base and review target", "trusted-base/" in text and "review-target/" in text)
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
    _add(results, "docs describe Stage 2", "Stage 2 Plan" in text)
    _add(results, "docs describe stop methods", "Stop Methods" in text)
    _add(results, "docs mention API billing", "API Billing" in text)
    _add(results, "docs state no pull_request_target", "does not use `pull_request_target`" in text)
    _add(results, "docs state no auto-fix", "does not implement auto-fix behavior" in text)
    _add(results, "docs explain trusted prompt checkout", "`trusted-base/`" in text and "`review-target/`" in text)
    _add(results, "docs explain fail-closed prompt behavior", "fails closed" in text)
    _add(results, "docs explain sticky comment", "deduplicates comments by marker only" in text)
    return results


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def run_checks() -> list[CheckResult]:
    results: list[CheckResult] = []
    for path in (WORKFLOW_PATH, PROMPT_PATH, DOC_PATH):
        _add(results, f"{path.relative_to(REPO_ROOT)} exists", path.exists())
    if WORKFLOW_PATH.exists():
        results.extend(check_workflow_text(load_text(WORKFLOW_PATH)))
    if PROMPT_PATH.exists():
        results.extend(check_prompt_text(load_text(PROMPT_PATH)))
    if DOC_PATH.exists():
        results.extend(check_doc_text(load_text(DOC_PATH)))
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
