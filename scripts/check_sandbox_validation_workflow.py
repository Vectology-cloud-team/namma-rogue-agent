#!/usr/bin/env python3
"""Validate Stage 2C-A sandbox preflight workflow safety properties."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
COLLECTOR_PATH = WORKFLOW_DIR / "fix-sandbox-collect.yml"
VALIDATOR_PATH = WORKFLOW_DIR / "fix-sandbox.yml"
SCRIPT_PATH = REPO_ROOT / "scripts" / "sandbox_validation.py"
SCHEMA_PATH = (
    REPO_ROOT
    / ".github"
    / "codex"
    / "schemas"
    / "sandbox-validation-result.schema.json"
)
FIX_POLICY_PATH = REPO_ROOT / ".github" / "codex" / "fix-policy.yml"
EXPECTED_REPOSITORY = "Vectology-cloud-team/namma-rogue-agent"
COLLECTOR_WORKFLOW_NAME = "Sandbox Validation Request Collector"
VALIDATOR_WORKFLOW_NAME = "Sandbox Preflight Validator"
FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
ACTION_USES_RE = re.compile(
    r"(?m)^\s*uses:\s+([^@\s]+)@([^\s#]+)(?:\s+#\s*([^\s]+))?\s*$"
)
PINNED_ACTIONS = {
    "actions/upload-artifact": {
        "sha": "ea165f8d65b6e75b540449e92b4886f43607fa02",
        "version": "v4",
    },
    "actions/download-artifact": {
        "sha": "d3f86a106a0bac45b974a628896c90dbdf5c8093",
        "version": "v4",
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
        "all sandbox workflow actions use full commit SHAs",
        all(FULL_SHA_RE.fullmatch(ref) for _, ref, _ in entries),
    )
    add(
        results,
        "only allowed sandbox actions are used",
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
    add(results, "sandbox collector workflow exists", f"name: {COLLECTOR_WORKFLOW_NAME}" in text)
    add(results, "sandbox collector uses pull_request trigger", "pull_request:" in text)
    add(results, "sandbox collector only listens for labeled", "- labeled" in text and "- synchronize" not in text and "- reopened" not in text)
    add(results, "sandbox collector requires validate label", "github.event.label.name == 'ai-fix-validate'" in text)
    add(results, "sandbox collector rejects fork PRs", "head.repo.full_name == github.repository" in text)
    add(results, "sandbox collector has no workflow_dispatch", "workflow_dispatch" not in text)
    add(results, "sandbox collector has only contents read", regex(collect_job, r"permissions:\n\s+contents: read"))
    add(results, "sandbox collector has no write permission", ": write" not in collect_job)
    add(results, "sandbox collector has no secrets", "secrets." not in collect_job)
    add(results, "sandbox collector has no OPENAI_API_KEY", "OPENAI_API_KEY" not in collect_job)
    add(results, "sandbox collector does not run Codex", "openai/codex-action" not in collect_job)
    add(results, "sandbox collector does not run repository scripts", "scripts/" not in collect_job)
    add(results, "sandbox collector records trusted event actor", '"actor": event["sender"]["login"]' in collect_job)
    add(results, "sandbox collector writes fixed request schema", "sandbox-validation-request-v1" in collect_job)
    add(results, "sandbox collector uploads request artifact", "sandbox-validation-request-${{ github.run_id }}" in collect_job)
    return results


def check_validator(text: str) -> list[CheckResult]:
    results: list[CheckResult] = []
    preflight_job = job_section(text, "preflight")
    post_job = job_section(text, "post_sandbox_validation")
    script = load_text(SCRIPT_PATH)
    add(results, "sandbox validator workflow exists", f"name: {VALIDATOR_WORKFLOW_NAME}" in text)
    add(results, "sandbox validator uses workflow_run trigger", "workflow_run:" in text)
    add(results, "sandbox validator watches collector", f"- {COLLECTOR_WORKFLOW_NAME}" in text)
    add(results, "sandbox validator requires collector success", "github.event.workflow_run.conclusion == 'success'" in text)
    add(results, "sandbox validator checks workflow name", f"github.event.workflow_run.name == '{COLLECTOR_WORKFLOW_NAME}'" in text)
    add(results, "sandbox validator checks event type", "github.event.workflow_run.event == 'pull_request'" in text)
    add(results, "sandbox validator checks repository identity", f"github.repository == '{EXPECTED_REPOSITORY}'" in text)
    add(results, "sandbox validator has no workflow_dispatch", "workflow_dispatch" not in text)
    add(results, "preflight job has no write permission", ": write" not in preflight_job)
    add(results, "preflight job has no OPENAI_API_KEY", "OPENAI_API_KEY" not in preflight_job)
    add(results, "preflight job has no checkout action", "actions/checkout" not in preflight_job)
    add(results, "preflight job downloads trusted files by API", "trusted sandbox control plane" in preflight_job and "/contents/" in preflight_job)
    add(results, "preflight job downloads request artifact", "download-request-artifact" in preflight_job)
    add(results, "preflight job uses trusted policy", ".github/codex/fix-policy.yml" in preflight_job)
    add(results, "preflight job uses trusted result schema", "sandbox-validation-result.schema.json" in preflight_job)
    add(results, "preflight job binds validation actor from workflow_run", "VALIDATION_ACTOR:" in preflight_job and "github.event.workflow_run.actor.login" in preflight_job)
    add(results, "preflight job uploads result artifact", "sandbox-validation-preflight" in preflight_job and "actions/upload-artifact@" in preflight_job)
    add(results, "post job can write issue comments", "issues: write" in post_job)
    add(results, "post job can write pull request sticky comments", "pull-requests: write" in post_job)
    add(results, "post job has no contents write", "contents: write" not in post_job)
    add(results, "post job has no OPENAI_API_KEY", "OPENAI_API_KEY" not in post_job)
    add(results, "post job downloads result before comment", post_job.find("Download sandbox preflight result artifact") < post_job.find("Post or update sandbox preflight comment"))
    add(results, "sandbox script requires live three-label gate", "ai-fix-proposal" in script and "ai-fix-approved" in script and "ai-fix-validate" in script)
    add(results, "sandbox script recalculates proposal hash through approval validation", "validate_proposal_for_approval" in script)
    add(results, "sandbox script validates approval record hash", "validate_approval_record_shape" in script and "approval_record_hash" in script)
    add(results, "sandbox script rechecks actor repository permission", "approval_actor_repository_permission" in script and "/collaborators/{actor}/permission" in load_text(REPO_ROOT / "scripts" / "approval_record.py"))
    add(results, "sandbox script only allows admin maintain", "ALLOWED_REPOSITORY_PERMISSIONS = {\"admin\", \"maintain\"}" in script)
    add(results, "sandbox script performs double head check", "validate_final_head" in script)
    add(results, "sandbox script verifies target blob metadata", "fetch_tree_entries" in script and "validate_target_blob_shas" in script)
    add(results, "sandbox script validates patch metadata only", "validate_patch_metadata" in script)
    add(results, "sandbox script validates trusted test IDs", "normalize_test_ids" in script and "sandbox_test_ids" in script)
    add(results, "sandbox script validates result schema before artifact", "validate_result_against_schema" in script and "SANDBOX_RESULT_SCHEMA" in preflight_job)
    add(results, "sandbox marker is implemented", "<!-- namma-ai-sandbox-validation -->" in script)
    add(results, "sandbox comment uses issue comment list endpoint", "iter_issue_comments" in script)
    add(results, "sandbox comment uses issue comment create endpoint", "/issues/{issue_number}/comments" in script)
    add(results, "sandbox comment uses issue comment update endpoint", "/issues/comments/{comment_id}" in script)
    return results


def check_forbidden_automation(text: str) -> list[CheckResult]:
    lowered = text.lower()
    results: list[CheckResult] = []
    for token in (
        "actions/checkout",
        "git apply",
        "git push",
        "git merge",
        "gh pr merge",
        "gh pr create",
        "merge_pull_request",
        "createcommitonbranch",
        "createpullrequest",
        "createreviewcomment",
        "createreview",
        "submitreview",
        "pulls.createreview",
        "pulls.submitreview",
        "pulls.createreviewcomment",
        "contents: write",
        "actions: write",
        "checks: write",
        "deployments: write",
        "id-token: write",
        "packages: write",
        "security-events: write",
        "statuses: write",
        "openai_api_key",
        "openai/codex-action",
    ):
        add(results, f"sandbox workflows do not contain {token}", token not in lowered)
    add(results, "sandbox workflows do not use pull_request_target", "pull_request_target" not in lowered)
    return results


def check_schema_and_policy() -> list[CheckResult]:
    results: list[CheckResult] = []
    schema = load_text(SCHEMA_PATH)
    policy = load_text(FIX_POLICY_PATH)
    add(results, "sandbox result schema exists", SCHEMA_PATH.exists())
    add(results, "sandbox result schema has precheck status", '"PRECHECK_PASSED"' in schema)
    add(results, "sandbox result schema records phase", '"phase"' in schema and '"PREFLIGHT"' in schema)
    add(results, "sandbox result schema records validation actor", "validation_request_actor" in schema)
    add(results, "sandbox result schema records live labels", "live_labels" in schema)
    add(results, "sandbox result schema records target blob checks", "target_blob_checks" in schema)
    add(results, "sandbox result schema records patch metadata check", "patch_metadata_check" in schema)
    add(results, "sandbox result schema records no checkout flag", "sandbox_checkout_performed" in schema)
    add(results, "sandbox result schema records no test execution flag", "test_execution_performed" in schema)
    add(results, "trusted policy defines sandbox test IDs", "sandbox_test_ids:" in policy)
    return results


def run_checks() -> list[CheckResult]:
    collector = load_text(COLLECTOR_PATH)
    validator = load_text(VALIDATOR_PATH)
    combined_workflows = "\n".join(path.read_text(encoding="utf-8") for path in workflow_files())
    results: list[CheckResult] = []
    results.extend(check_action_pinning(collector + "\n" + validator))
    results.extend(check_collector(collector))
    results.extend(check_validator(validator))
    results.extend(check_forbidden_automation(collector + "\n" + validator))
    results.extend(check_forbidden_automation(load_text(SCRIPT_PATH)))
    results.extend(check_schema_and_policy())
    add(results, "all repository workflow actions remain pinned", all(FULL_SHA_RE.fullmatch(ref) for _, ref, _ in action_uses(combined_workflows)))
    return results


def main() -> int:
    results = run_checks()
    failed = [result for result in results if not result.passed]
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        detail = f" - {result.detail}" if result.detail else ""
        print(f"{status}: {result.label}{detail}")
    if failed:
        print(f"\n{len(failed)} sandbox validation workflow check(s) failed.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
