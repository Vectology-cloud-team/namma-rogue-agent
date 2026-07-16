#!/usr/bin/env python3
"""Validate Stage 2B approval-record workflow safety properties."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
COLLECTOR_PATH = WORKFLOW_DIR / "fix-approval-collect.yml"
RECORDER_PATH = WORKFLOW_DIR / "fix-approval.yml"
FIX_PROPOSAL_WORKFLOW_PATH = WORKFLOW_DIR / "fix-proposal.yml"
SCHEMA_PATH = REPO_ROOT / ".github" / "codex" / "schemas" / "approval-record.schema.json"
SCRIPT_PATH = REPO_ROOT / "scripts" / "approval_record.py"
EXPECTED_REPOSITORY = "Vectology-cloud-team/namma-rogue-agent"
COLLECTOR_WORKFLOW_NAME = "Fix Approval Request Collect"
RECORDER_WORKFLOW_NAME = "Fix Approval Recorder"
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
    add(results, "approval collector workflow exists", f"name: {COLLECTOR_WORKFLOW_NAME}" in text)
    add(results, "approval collector uses pull_request trigger", "pull_request:" in text)
    add(results, "approval collector listens for labeled", "- labeled" in text)
    add(results, "approval collector does not listen for synchronize", "- synchronize" not in text)
    add(results, "approval collector does not listen for reopened", "- reopened" not in text)
    add(results, "approval collector does not listen for ready_for_review", "- ready_for_review" not in text)
    add(results, "approval collector has no workflow_dispatch", "workflow_dispatch" not in text)
    add(results, "approval collector has only contents read", regex(collect_job, r"permissions:\n\s+contents: read"))
    add(results, "approval collector has no write permission", ": write" not in collect_job)
    add(results, "approval collector has no secrets", "secrets." not in collect_job)
    add(results, "approval collector has no OPENAI_API_KEY", "OPENAI_API_KEY" not in collect_job)
    add(results, "approval collector does not run Codex", "openai/codex-action" not in collect_job)
    add(results, "approval collector does not run repository scripts", "scripts/" not in collect_job)
    add(results, "approval collector writes fixed schema", "fix-approval-request-v1" in collect_job)
    add(results, "approval collector records event label", "event_label" in collect_job)
    add(results, "approval collector uploads request artifact", "fix-approval-request-${{ github.run_id }}" in collect_job)
    return results


def check_recorder(text: str) -> list[CheckResult]:
    results: list[CheckResult] = []
    record_job = job_section(text, "record")
    post_job = job_section(text, "post_approval")
    script = load_text(SCRIPT_PATH)
    add(results, "approval recorder workflow exists", f"name: {RECORDER_WORKFLOW_NAME}" in text)
    add(results, "approval recorder uses workflow_run trigger", "workflow_run:" in text)
    add(results, "approval recorder watches collector", f"- {COLLECTOR_WORKFLOW_NAME}" in text)
    add(results, "approval recorder requires collector success", "github.event.workflow_run.conclusion == 'success'" in text)
    add(results, "approval recorder checks workflow name", f"github.event.workflow_run.name == '{COLLECTOR_WORKFLOW_NAME}'" in text)
    add(results, "approval recorder checks event type", "github.event.workflow_run.event == 'pull_request'" in text)
    add(results, "approval recorder checks repository identity", f"github.repository == '{EXPECTED_REPOSITORY}'" in text)
    add(results, "approval recorder has no workflow_dispatch", "workflow_dispatch" not in text)
    add(results, "record job has no write permission", ": write" not in record_job)
    add(results, "record job has no OPENAI_API_KEY", "OPENAI_API_KEY" not in record_job)
    add(results, "record job can read actions artifacts", "actions: read" in record_job)
    add(results, "record job can read trusted contents", "contents: read" in record_job)
    add(results, "record job can read issues", "issues: read" in record_job)
    add(results, "record job can read pull requests", "pull-requests: read" in record_job)
    add(results, "record job downloads approval request artifact", "download-request-artifact" in record_job)
    add(results, "record job uses trusted policy", ".github/codex/fix-policy.yml" in record_job)
    add(results, "record job uses trusted approval schema", "approval-record.schema.json" in record_job)
    add(results, "record job binds approval actor from workflow_run", "APPROVAL_ACTOR:" in record_job and "github.event.workflow_run.actor.login" in record_job)
    add(results, "record job uploads approval record artifact", "APPROVAL_RECORD_DIR" in record_job and "actions/upload-artifact@" in record_job)
    add(results, "post job has no OPENAI_API_KEY", "OPENAI_API_KEY" not in post_job)
    add(results, "post job can write issue comments", "issues: write" in post_job)
    add(results, "post job can write pull request comments", "pull-requests: write" in post_job)
    add(results, "post job has no contents write", "contents: write" not in post_job)
    add(results, "post job downloads record artifact before comment", post_job.find("Download generated approval record artifact") < post_job.find("Post or update fix approval comment"))
    add(results, "approval marker is implemented", "<!-- namma-ai-approval -->" in script)
    add(results, "approval uses issue comment list endpoint", "iter_issue_comments" in script and "github_approval_comments_list" in script)
    add(results, "approval uses issue comment create endpoint", "/issues/{issue_number}/comments" in script)
    add(results, "approval uses issue comment update endpoint", "/issues/comments/{comment_id}" in script)
    add(results, "approval does not use PR review API", "pulls.createReview" not in script and "createReviewComment" not in script and "/pulls/{issue_number}/comments" not in script)
    add(results, "approval validates proposal artifact", "validate_proposal_for_approval" in script)
    add(results, "approval validates actor membership", "approval_actor_association" in script and "github_approval_actor_membership" in script)
    add(results, "approval rejects manifest actor spoofing", "approval actor mismatch" in script and "APPROVAL_ACTOR" in script)
    add(results, "approval validates live head before comment", "validate_comment_target" in script)
    add(results, "approval ID is deterministic", "sha256_hex_json" in script and "approval_id" in script)
    add(results, "approval script does not invoke Codex", "openai/codex-action" not in script and "OPENAI_API_KEY" not in script)
    return results


def check_forbidden_automation(text: str) -> list[CheckResult]:
    lowered = text.lower()
    results: list[CheckResult] = []
    for token in (
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
    ):
        add(results, f"approval workflows do not contain {token}", token not in lowered)
    add(results, "approval workflows do not use pull_request_target", "pull_request_target" not in lowered)
    return results


def check_schema_and_scripts() -> list[CheckResult]:
    results: list[CheckResult] = []
    schema = load_text(SCHEMA_PATH)
    script = load_text(SCRIPT_PATH)
    fix_workflow = load_text(FIX_PROPOSAL_WORKFLOW_PATH)
    add(results, "approval schema exists", SCHEMA_PATH.exists())
    add(results, "approval schema has approved status", '"APPROVED"' in schema)
    add(results, "approval schema has stale status", '"STALE"' in schema)
    add(results, "approval schema requires deterministic ID field", '"approval_id"' in schema)
    add(results, "proposal workflow cannot write approval record", "approval-record-" not in fix_workflow)
    add(results, "proposal workflow cannot write approval marker", "<!-- namma-ai-approval -->" not in fix_workflow)
    add(results, "approval script states no patch apply", "must never apply patches" in script)
    subprocess_import = "import " + "subprocess"
    add(results, "approval script avoids subprocess module", subprocess_import not in script)
    return results


def run_checks() -> list[CheckResult]:
    results: list[CheckResult] = []
    for path in (COLLECTOR_PATH, RECORDER_PATH, SCHEMA_PATH, SCRIPT_PATH):
        add(results, f"{path.relative_to(REPO_ROOT)} exists", path.exists())
    combined = "\n".join(load_text(path) for path in workflow_files())
    approval_workflows = "\n".join(load_text(path) for path in (COLLECTOR_PATH, RECORDER_PATH))
    results.extend(check_action_pinning(combined))
    results.extend(check_collector(load_text(COLLECTOR_PATH)))
    results.extend(check_recorder(load_text(RECORDER_PATH)))
    results.extend(check_forbidden_automation(approval_workflows))
    results.extend(check_schema_and_scripts())
    return results


def main() -> int:
    results = run_checks()
    failed = [result for result in results if not result.passed]
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        detail = f" - {result.detail}" if result.detail else ""
        print(f"{status}: {result.label}{detail}")
    if failed:
        print(f"{len(failed)} approval workflow checks failed.", file=sys.stderr)
        return 1
    print(f"{len(results)} approval workflow checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
