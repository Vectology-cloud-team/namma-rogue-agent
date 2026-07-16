#!/usr/bin/env python3
"""Validate Stage 2A fix-proposal workflow safety properties."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
COLLECTOR_PATH = WORKFLOW_DIR / "fix-proposal-collect.yml"
GENERATOR_PATH = WORKFLOW_DIR / "fix-proposal.yml"
PROMPT_PATH = REPO_ROOT / ".github" / "codex" / "prompts" / "fix-proposal.md"
POLICY_PATH = REPO_ROOT / ".github" / "codex" / "fix-policy.yml"
SCHEMA_PATH = REPO_ROOT / ".github" / "codex" / "schemas" / "fix-proposal.schema.json"
SCRIPT_PATH = REPO_ROOT / "scripts" / "fix_proposal_generator.py"
EXPECTED_REPOSITORY = "Vectology-cloud-team/namma-rogue-agent"
COLLECTOR_WORKFLOW_NAME = "Fix Proposal Request Collect"
GENERATOR_WORKFLOW_NAME = "Fix Proposal Generator"
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
        "sha": "d3f86a106a0bac45b974a628896c90dbdf5c8093",
        "version": "v4",
    },
    "openai/codex-action": {
        "sha": "52fe01ec70a42f454c9d2ebd47598f9fd6893d56",
        "version": "v1",
    },
}


@dataclass(frozen=True)
class CheckResult:
    label: str
    passed: bool
    detail: str = ""


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def add(results: list[CheckResult], label: str, passed: bool, detail: str = "") -> None:
    results.append(CheckResult(label, passed, detail))


def regex(text: str, pattern: str) -> bool:
    return re.search(pattern, text, flags=re.MULTILINE) is not None


def job_section(text: str, job_name: str) -> str:
    marker = f"  {job_name}:"
    start = text.find(marker)
    if start == -1:
        return ""
    match = re.search(r"\n  [A-Za-z0-9_-]+:\n", text[start + len(marker):])
    if not match:
        return text[start:]
    return text[start : start + len(marker) + match.start()]


def workflow_files() -> list[Path]:
    return sorted({*WORKFLOW_DIR.glob("*.yml"), *WORKFLOW_DIR.glob("*.yaml")})


def action_uses(text: str) -> list[tuple[str, str, str | None]]:
    return [
        (match.group(1), match.group(2), match.group(3))
        for match in ACTION_USES_RE.finditer(text)
    ]


def check_action_pinning(text: str) -> list[CheckResult]:
    results: list[CheckResult] = []
    entries = action_uses(text)
    add(
        results,
        "all workflow actions use full commit SHAs",
        all(FULL_SHA_RE.fullmatch(ref) for _, ref, _ in entries),
    )
    add(
        results,
        "only allowed actions are used",
        all(action in PINNED_ACTIONS for action, _, _ in entries),
    )
    for action, ref, version in entries:
        expected = PINNED_ACTIONS.get(action)
        add(
            results,
            f"{action} is pinned to allowed SHA",
            expected is not None and ref == expected["sha"],
        )
        add(
            results,
            f"{action} keeps version comment",
            expected is not None and version == expected["version"],
        )
    return results


def check_collector(text: str) -> list[CheckResult]:
    results: list[CheckResult] = []
    collect_job = job_section(text, "collect")
    add(results, "collector workflow exists", f"name: {COLLECTOR_WORKFLOW_NAME}" in text)
    add(results, "collector uses pull_request trigger", "pull_request:" in text)
    add(results, "collector listens for labeled", "- labeled" in text)
    add(results, "collector has no workflow_dispatch", "workflow_dispatch" not in text)
    add(results, "collector has only contents read permission", regex(collect_job, r"permissions:\n\s+contents: read"))
    add(results, "collector has no write permission", ": write" not in collect_job)
    add(results, "collector has no secrets", "secrets." not in collect_job)
    add(results, "collector has no OPENAI_API_KEY", "OPENAI_API_KEY" not in collect_job)
    add(results, "collector does not run Codex", "openai/codex-action" not in collect_job)
    add(results, "collector does not run repository scripts", "scripts/" not in collect_job and "scripts\\" not in collect_job)
    add(results, "collector writes fixed manifest schema", "fix-proposal-request-v1" in collect_job)
    add(results, "collector limits artifact size", "MAX_ARTIFACT_BYTES" in collect_job)
    add(results, "collector uploads request artifact", "fix-proposal-request-${{ github.run_id }}" in collect_job)
    add(results, "collector does not shell-expand PR title", "github.event.pull_request.title" not in collect_job)
    return results


def check_generator(text: str) -> list[CheckResult]:
    results: list[CheckResult] = []
    generate_job = job_section(text, "generate")
    post_job = job_section(text, "post_feedback")
    script = load_text(SCRIPT_PATH)
    add(results, "generator workflow exists", f"name: {GENERATOR_WORKFLOW_NAME}" in text)
    add(results, "generator uses workflow_run trigger", "workflow_run:" in text)
    add(results, "generator watches collector", f"- {COLLECTOR_WORKFLOW_NAME}" in text)
    add(results, "generator requires collector success", "github.event.workflow_run.conclusion == 'success'" in text)
    add(results, "generator checks workflow name", f"github.event.workflow_run.name == '{COLLECTOR_WORKFLOW_NAME}'" in text)
    add(results, "generator checks event type", "github.event.workflow_run.event == 'pull_request'" in text)
    add(results, "generator checks repository identity", f"github.repository == '{EXPECTED_REPOSITORY}'" in text)
    add(results, "generator has no workflow_dispatch", "workflow_dispatch" not in text)
    add(results, "generate job has no write permission", ": write" not in generate_job)
    add(results, "generate job can read artifacts", "actions: read" in generate_job)
    add(results, "generate job can read contents", "contents: read" in generate_job)
    add(results, "post job can read artifacts", "actions: read" in post_job)
    add(results, "post job can read trusted control plane", "contents: read" in post_job)
    add(results, "post job can write issue comments", "issues: write" in post_job)
    add(results, "post job has pull request read only", "pull-requests: read" in post_job and "pull-requests: write" not in post_job)
    add(results, "post job has no contents write", "contents: write" not in post_job)
    add(results, "only generator references OPENAI_API_KEY", "OPENAI_API_KEY" in generate_job and "OPENAI_API_KEY" not in post_job)
    add(results, "collector artifact is downloaded before Codex", "download-request-artifact" in generate_job)
    add(results, "trusted fix policy is loaded", ".github/codex/fix-policy.yml" in generate_job)
    add(results, "trusted fix prompt is verified", ".github/codex/prompts/fix-proposal.md" in generate_job and "verify-prompt" in generate_job)
    add(results, "trusted schema is referenced", ".github/codex/schemas/fix-proposal.schema.json" in generate_job)
    add(results, "gate runs before Codex", generate_job.find("prepare-generation") < generate_job.find("openai/codex-action@"))
    add(results, "Codex only runs when gate passes", "steps.prepare.outputs.should_generate == 'true'" in generate_job)
    add(results, "Codex uses read-only permission profile", 'permission-profile: ":read-only"' in generate_job)
    add(results, "Codex uses policy model", "model: ${{ steps.policy.outputs.model }}" in generate_job)
    add(results, "Codex uses policy effort", "effort: ${{ steps.policy.outputs.effort }}" in generate_job)
    add(results, "validated proposal artifact is uploaded", "fix-proposal-" in generate_job and "actions/upload-artifact@" in generate_job)
    add(results, "sticky marker is implemented", "<!-- namma-ai-fix-proposal -->" in script)
    add(results, "proposal hash is deterministic", "canonical_json_bytes" in script and "proposal_input_hash" in script)
    add(results, "protected path validation is reused", "validate_fix_proposal" in script)
    add(results, "trusted target contents are collected", "target-file-contents.json" in text and "trusted_target_contents" in script)
    add(results, "patch applicability is validated", "validate_patches_apply_to_targets" in script and "PATCH_DOES_NOT_APPLY" in script)
    add(results, "proposal generation requires changes requested verdict", "review_result.get(\"verdict\") != \"CHANGES_REQUESTED\"" in script)
    add(results, "proposal comment validates live head", "validate_comment_target" in script and "github_fix_comment_target" in script)
    add(results, "proposal comment uses issue comment list endpoint", "iter_issue_comments" in script and "github_issue_comments_list" in script)
    add(results, "proposal comment uses issue comment create endpoint", "/issues/{issue_number}/comments" in script)
    add(results, "proposal comment uses issue comment update endpoint", "/issues/comments/{comment_id}" in script)
    add(results, "proposal comment does not use PR review API", "pulls.createReview" not in script and "pulls.createReviewComment" not in script and "/pulls/{issue_number}/comments" not in script)
    add(results, "duplicate proposal detection is wired", "existing_proposal_records_from_comments" in script and "existing_proposals=existing_proposals" in script)
    add(results, "Stage 2B and Stage 2C are absent", "Stage 2B" not in text and "Stage 2C" not in text)
    return results


def check_forbidden_automation(text: str) -> list[CheckResult]:
    lowered = text.lower()
    results: list[CheckResult] = []
    for token in (
        "git push",
        "git merge",
        "gh pr merge",
        "gh pr create",
        "createcommitonbranch",
        "createpullrequest",
        "createreviewcomment",
        "contents: write",
    ):
        add(results, f"workflow does not contain {token}", token not in lowered)
    add(results, "workflow does not use pull_request_target", "pull_request_target" not in lowered)
    return results


def check_policy_prompt_and_schema() -> list[CheckResult]:
    results: list[CheckResult] = []
    policy = load_text(POLICY_PATH)
    prompt = load_text(PROMPT_PATH)
    schema = load_text(SCHEMA_PATH)
    add(results, "fix policy sets generator model", regex(policy, r"(?m)^  model:\s*\S+"))
    add(results, "fix policy sets generator effort", regex(policy, r"(?m)^  reasoning_effort:\s*\S+"))
    add(results, "fix policy protects workflows", "- .github/workflows/**" in policy)
    add(results, "fix policy protects prompts", "- .github/codex/prompts/**" in policy)
    add(results, "fix prompt forbids applying patches", "Do not apply patches" in prompt)
    add(results, "fix prompt treats PR input as untrusted", "untrusted data" in prompt)
    add(results, "fix prompt requires JSON only", "Return exactly one JSON object" in prompt)
    add(results, "proposal schema requires human approval", "human_approval_required" in schema)
    return results


def run_checks() -> list[CheckResult]:
    results: list[CheckResult] = []
    for path in (COLLECTOR_PATH, GENERATOR_PATH, PROMPT_PATH, POLICY_PATH, SCHEMA_PATH, SCRIPT_PATH):
        add(results, f"{path.relative_to(REPO_ROOT)} exists", path.exists())
    combined = "\n".join(load_text(path) for path in workflow_files())
    results.extend(check_action_pinning(combined))
    if COLLECTOR_PATH.exists():
        results.extend(check_collector(load_text(COLLECTOR_PATH)))
    if GENERATOR_PATH.exists():
        results.extend(check_generator(load_text(GENERATOR_PATH)))
    results.extend(check_forbidden_automation(combined))
    results.extend(check_policy_prompt_and_schema())
    return results


def main() -> int:
    results = run_checks()
    failed = [result for result in results if not result.passed]
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        detail = f" - {result.detail}" if result.detail else ""
        print(f"{status}: {result.label}{detail}")
    if failed:
        print(f"{len(failed)} fix proposal workflow checks failed.", file=sys.stderr)
        return 1
    print(f"{len(results)} fix proposal workflow checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
