#!/usr/bin/env python3
"""Validate Stage 2C-B1 sandbox apply workflow safety properties."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
COLLECTOR_PATH = WORKFLOW_DIR / "fix-sandbox-apply-collect.yml"
APPLY_PATH = WORKFLOW_DIR / "fix-sandbox-apply.yml"
SCRIPT_PATH = REPO_ROOT / "scripts" / "sandbox_apply.py"
SCHEMA_PATH = (
    REPO_ROOT
    / ".github"
    / "codex"
    / "schemas"
    / "sandbox-validation-result.schema.json"
)
EXPECTED_REPOSITORY = "Vectology-cloud-team/namma-rogue-agent"
COLLECTOR_WORKFLOW_NAME = "Sandbox Apply Request Collector"
APPLY_WORKFLOW_NAME = "Sandbox Apply Validator"
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
        "all sandbox apply actions use full commit SHAs",
        all(FULL_SHA_RE.fullmatch(ref) for _, ref, _ in entries),
    )
    add(
        results,
        "only allowed sandbox apply actions are used",
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
    add(results, "apply collector workflow exists", f"name: {COLLECTOR_WORKFLOW_NAME}" in text)
    add(results, "apply collector uses pull_request trigger", "pull_request:" in text)
    add(results, "apply collector only listens for labeled", "- labeled" in text and "- synchronize" not in text)
    add(results, "apply collector requires apply label", "github.event.label.name == 'ai-fix-apply-sandbox'" in text)
    add(results, "apply collector rejects fork PRs", "head.repo.full_name == github.repository" in text)
    add(results, "apply collector has only contents read", regex(collect_job, r"permissions:\n\s+contents: read"))
    add(results, "apply collector has no write permission", ": write" not in collect_job)
    add(results, "apply collector has no secrets", "secrets." not in collect_job)
    add(results, "apply collector has no OPENAI_API_KEY", "OPENAI_API_KEY" not in collect_job)
    add(results, "apply collector does not run Codex", "openai/codex-action" not in collect_job)
    add(results, "apply collector does not checkout", "actions/checkout" not in collect_job)
    add(results, "apply collector does not select artifacts", "fix-proposal" not in collect_job and "approval-record" not in collect_job)
    add(results, "apply collector writes fixed request stage", "SANDBOX_APPLY_REQUEST" in collect_job)
    add(results, "apply collector writes event label", '"event_label": event["label"]["name"]' in collect_job)
    add(results, "apply collector artifact name is stage-specific", "sandbox-apply-request-${{ github.run_id }}" in collect_job)
    return results


def check_apply_workflow(text: str) -> list[CheckResult]:
    results: list[CheckResult] = []
    apply_job = job_section(text, "sandbox_apply")
    post_job = job_section(text, "post_sandbox_apply")
    script = load_text(SCRIPT_PATH)
    add(results, "apply workflow exists", f"name: {APPLY_WORKFLOW_NAME}" in text)
    add(results, "apply workflow uses workflow_run trigger", "workflow_run:" in text)
    add(results, "apply workflow watches apply collector", f"- {COLLECTOR_WORKFLOW_NAME}" in text)
    add(results, "apply workflow requires collector success", "github.event.workflow_run.conclusion == 'success'" in text)
    add(results, "apply workflow checks workflow name", f"github.event.workflow_run.name == '{COLLECTOR_WORKFLOW_NAME}'" in text)
    add(results, "apply workflow checks event type", "github.event.workflow_run.event == 'pull_request'" in text)
    add(results, "apply workflow checks repository identity", f"github.repository == '{EXPECTED_REPOSITORY}'" in text)
    add(results, "apply workflow has no workflow_dispatch", "workflow_dispatch" not in text)
    add(results, "apply job has no write permission", ": write" not in apply_job)
    add(results, "apply job has no OPENAI_API_KEY", "OPENAI_API_KEY" not in apply_job)
    add(results, "apply workflow has exact SHA checkout", "ref: ${{ steps.prepare.outputs.head_sha }}" in apply_job)
    add(results, "checkout persists no credentials", "persist-credentials: false" in apply_job)
    add(results, "checkout disables submodules", "submodules: false" in apply_job)
    add(results, "checkout disables lfs", "lfs: false" in apply_job)
    add(results, "checkout uses sandbox path", "path: sandbox-worktree" in apply_job)
    add(results, "apply job downloads trusted files by API", "/contents/" in apply_job and "trusted sandbox apply control plane" in apply_job)
    add(results, "apply job downloads request artifact", "download-request-artifact" in apply_job)
    add(results, "apply job selects proposal approval preflight before checkout", apply_job.find("prepare") < apply_job.find("actions/checkout@"))
    add(results, "apply job runs fixed apply script after checkout", "sandbox_apply.py apply" in apply_job)
    add(results, "patch file is in runner temp", "PATCH_FILE: ${{ runner.temp }}/namma-fix.patch" in apply_job)
    add(results, "post job can write issue comments", "issues: write" in post_job)
    add(results, "post job can write pull request sticky comments", "pull-requests: write" in post_job)
    add(results, "post job has no contents write", "contents: write" not in post_job)
    add(results, "post job downloads result before comment", post_job.find("Download sandbox apply result artifact") < post_job.find("Post or update sandbox apply comment"))
    add(
        results,
        "script requires live four-label gate",
        all(
            token in script
            for token in (
                "required_labels",
                "APPLY_LABEL",
                "preflight.VALIDATE_LABEL",
                "policy.proposal_policy.proposal_label",
                "policy.proposal_policy.approval_label",
            )
        ),
    )
    add(results, "script verifies proposal approval preflight", "find_latest_preflight_artifact" in script and "validate_preflight_result" in script)
    add(results, "script defines canonical preflight artifact members", "PREFLIGHT_ARTIFACT_MEMBERS" in script)
    for member in (
        "sandbox-validation-result.json",
        "selected-proposal-manifest.json",
        "selected-approval-manifest.json",
        "target-blob-checks.json",
        "patch-metadata-check.json",
    ):
        add(results, f"script accepts canonical preflight sidecar {member}", member in script)
    add(results, "script rejects non-exact preflight artifact member set", "seen != set(PREFLIGHT_ARTIFACT_MEMBERS)" in script)
    add(results, "script rejects duplicate preflight artifact members", "duplicate preflight artifact member" in script)
    add(results, "script validates preflight sidecar cross-bindings", "validate_preflight_sidecars" in script and "selected proposal sidecar" in script)
    add(results, "script does not allow result-only preflight artifact", 'expected_files={"sandbox-validation-result.json"}' not in script)
    add(
        results,
        "script rechecks three actor permissions",
        all(
            token in script
            for token in (
                "apply_permission",
                "approval_permission",
                "validation_permission",
                "approval.approval_actor_repository_permission",
            )
        ),
    )
    add(results, "script checks head before checkout", "PRE_CHECKOUT_HEAD_STALE" in script)
    add(results, "script checks head after checkout", "POST_CHECKOUT_HEAD_STALE" in script)
    add(results, "script checks head before apply", "PRE_APPLY_HEAD_STALE" in script)
    add(results, "script checks head before result/comment", "FINAL_HEAD_STALE" in script and "validate_final_head" in script)
    add(results, "script uses fixed git apply check argv", "GIT_APPLY_CHECK_ARGV" in script and "--check" in script and "--whitespace=error-all" in script)
    add(results, "script uses fixed git apply argv", "GIT_APPLY_ARGV" in script and "--recount" in script)
    for token in ("--unsafe-paths", "--3way", "--reject", "--index", "--cached"):
        add(results, f"script forbids {token}", token in script and "FORBIDDEN_GIT_APPLY_OPTIONS" in script)
    add(
        results,
        "script verifies changed files",
        "verify_changed_files" in script
        and '"git", "diff", "--name-status", "-z"' in script
        and '"git", "diff", "--check"' in script,
    )
    add(results, "script verifies final diff binding", "patch_line_stats" in script and "DIFF_BINDING_MISMATCH" in script)
    add(results, "script records no tests executed", "Stage 2C-B1 records planned tests but does not execute tests." in script)
    add(results, "script cleans up sandbox", "cleanup_paths" in script and "shutil.rmtree" in script)
    add(results, "apply marker is implemented", "<!-- namma-ai-sandbox-apply -->" in script)
    add(results, "apply comment uses issue comment list endpoint", "iter_issue_comments" in script)
    add(results, "apply comment uses issue comment create endpoint", "/issues/{issue_number}/comments" in script)
    add(results, "apply comment uses issue comment update endpoint", "/issues/comments/{comment_id}" in script)
    return results


def check_forbidden(text: str) -> list[CheckResult]:
    results: list[CheckResult] = []
    lowered = text.lower()
    for token in (
        "openai_api_key",
        "openai/codex-action",
        "contents: write",
        "actions: write",
        "checks: write",
        "deployments: write",
        "id-token: write",
        "packages: write",
        "security-events: write",
        "statuses: write",
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
        "npm install",
        "pip install",
        "sudo ",
    ):
        add(results, f"sandbox apply automation does not contain {token}", token not in lowered)
    add(results, "sandbox apply does not use pull_request_target", "pull_request_target" not in lowered)
    return results


def check_schema() -> list[CheckResult]:
    schema = load_text(SCHEMA_PATH)
    results: list[CheckResult] = []
    add(results, "result schema has SANDBOX_APPLY phase", '"SANDBOX_APPLY"' in schema)
    add(results, "result schema has APPLY_PASSED status", '"APPLY_PASSED"' in schema)
    add(results, "result schema records apply request actor", "apply_request_actor" in schema)
    add(results, "result schema records preflight hash", "preflight_result_hash" in schema)
    add(results, "result schema records checkout fields", "checkout_performed" in schema and "checkout_sha" in schema)
    add(results, "result schema records git apply fields", "git_apply_check" in schema and "git_apply" in schema)
    add(results, "result schema records diff binding", "diff_binding" in schema)
    add(results, "result schema records cleanup", "sandbox_cleanup" in schema)
    return results


def run_checks() -> list[CheckResult]:
    collector = load_text(COLLECTOR_PATH)
    apply = load_text(APPLY_PATH)
    script = load_text(SCRIPT_PATH)
    results: list[CheckResult] = []
    results.extend(check_action_pinning(collector + "\n" + apply))
    results.extend(check_collector(collector))
    results.extend(check_apply_workflow(apply))
    results.extend(check_forbidden(collector + "\n" + apply))
    results.extend(check_forbidden(script.replace("git apply", "git-apply")))
    results.extend(check_schema())
    return results


def main() -> int:
    results = run_checks()
    failed = [result for result in results if not result.passed]
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        detail = f" - {result.detail}" if result.detail else ""
        print(f"{status}: {result.label}{detail}")
    if failed:
        print(f"\n{len(failed)} sandbox apply workflow check(s) failed.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
