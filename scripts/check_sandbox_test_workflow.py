#!/usr/bin/env python3
"""Validate Stage 2C-B2 sandbox test workflow safety properties."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
COLLECTOR_PATH = WORKFLOW_DIR / "fix-sandbox-test-collect.yml"
TEST_PATH = WORKFLOW_DIR / "fix-sandbox-test.yml"
SCRIPT_PATH = REPO_ROOT / "scripts" / "sandbox_test.py"
POLICY_PATH = REPO_ROOT / ".github" / "codex" / "sandbox-test-policy.yml"
SCHEMA_PATH = (
    REPO_ROOT / ".github" / "codex" / "schemas" / "sandbox-test-result.schema.json"
)
EXPECTED_REPOSITORY = "Vectology-cloud-team/namma-rogue-agent"
COLLECTOR_WORKFLOW_NAME = "Sandbox Test Request Collector"
TEST_WORKFLOW_NAME = "Sandbox Test Validator"
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


def sandbox_test_command_modules(policy: str) -> set[str]:
    modules: set[str] = set()
    in_commands = False
    for raw_line in policy.splitlines():
        line = raw_line.rstrip()
        if line == "commands:":
            in_commands = True
            continue
        if in_commands and line and not line.startswith(" "):
            break
        if not in_commands or not line.strip():
            continue
        _, _, value = line.strip().partition(":")
        argv = [part for part in value.strip().split("|") if part]
        if len(argv) >= 4 and argv[:3] in (["python3", "-m", "unittest"], ["python", "-m", "unittest"]):
            modules.add(argv[3])
    return modules


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


def step_section(text: str, step_name: str) -> str:
    marker = f"      - name: {step_name}"
    start = text.find(marker)
    if start == -1:
        return ""
    next_step = text.find("\n      - name:", start + len(marker))
    if next_step == -1:
        return text[start:]
    return text[start:next_step]


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
        "all sandbox test actions use full commit SHAs",
        all(FULL_SHA_RE.fullmatch(ref) for _, ref, _ in entries),
    )
    add(
        results,
        "only allowed sandbox test actions are used",
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
    add(results, "test collector workflow exists", f"name: {COLLECTOR_WORKFLOW_NAME}" in text)
    add(results, "test collector uses pull_request trigger", "pull_request:" in text)
    add(results, "test collector only listens for labeled", "- labeled" in text and "- synchronize" not in text)
    add(results, "test collector requires test label", "github.event.label.name == 'ai-fix-test-sandbox'" in text)
    add(results, "test collector rejects fork PRs", "head.repo.full_name == github.repository" in text)
    add(results, "test collector has only contents read", regex(collect_job, r"permissions:\n\s+contents: read"))
    add(results, "test collector has no write permission", ": write" not in collect_job)
    add(results, "test collector has no secrets", "secrets." not in collect_job)
    add(results, "test collector has no OPENAI_API_KEY", "OPENAI_API_KEY" not in collect_job)
    add(results, "test collector does not run Codex", "openai/codex-action" not in collect_job)
    add(results, "test collector does not checkout", "actions/checkout" not in collect_job)
    add(results, "test collector writes fixed request stage", "SANDBOX_TEST_REQUEST" in collect_job)
    add(results, "test collector artifact name is stage-specific", "sandbox-test-request-${{ github.run_id }}" in collect_job)
    return results


def check_test_workflow(text: str) -> list[CheckResult]:
    results: list[CheckResult] = []
    test_job = job_section(text, "sandbox_test")
    post_job = job_section(text, "post_sandbox_test")
    run_tests_step = step_section(text, "Run approved tests in ephemeral sandbox")
    script = load_text(SCRIPT_PATH)
    policy = load_text(POLICY_PATH)
    add(results, "test workflow exists", f"name: {TEST_WORKFLOW_NAME}" in text)
    add(results, "test workflow uses workflow_run trigger", "workflow_run:" in text)
    add(results, "test workflow watches test collector", f"- {COLLECTOR_WORKFLOW_NAME}" in text)
    add(results, "test workflow requires collector success", "github.event.workflow_run.conclusion == 'success'" in text)
    add(results, "test workflow checks workflow name", f"github.event.workflow_run.name == '{COLLECTOR_WORKFLOW_NAME}'" in text)
    add(results, "test workflow checks event type", "github.event.workflow_run.event == 'pull_request'" in text)
    add(results, "test workflow checks repository identity", f"github.repository == '{EXPECTED_REPOSITORY}'" in text)
    add(results, "test workflow has no workflow_dispatch", "workflow_dispatch" not in text)
    add(results, "test job has no write permission", ": write" not in test_job)
    add(results, "test job has no OPENAI_API_KEY", "OPENAI_API_KEY" not in test_job)
    add(results, "test workflow has exact SHA checkout", "ref: ${{ steps.prepare.outputs.head_sha }}" in test_job)
    add(results, "checkout persists no credentials", "persist-credentials: false" in test_job)
    add(results, "checkout disables submodules", "submodules: false" in test_job)
    add(results, "checkout disables lfs", "lfs: false" in test_job)
    add(results, "test job downloads trusted files by API", "/contents/" in test_job and "trusted sandbox test control plane" in test_job)
    add(results, "test job selects artifacts before checkout", test_job.find("prepare") < test_job.find("actions/checkout@"))
    add(results, "test job runs sandbox test script", "sandbox_test.py run-tests" in test_job)
    add(results, "test runner step has no GITHUB_TOKEN", "GITHUB_TOKEN" not in run_tests_step)
    add(results, "test job writes patch only to runner temp", "PATCH_FILE: ${{ runner.temp }}/namma-fix.patch" in test_job)
    add(results, "post job can write issue comments", "issues: write" in post_job)
    add(results, "post job can write pull request sticky comments", "pull-requests: write" in post_job)
    add(results, "post job has no contents write", "contents: write" not in post_job)
    add(results, "post job downloads result before comment", post_job.find("Download sandbox test result artifact") < post_job.find("Post or update sandbox test comment"))
    add(results, "script requires live five-label gate", "apply.APPLY_LABEL" in script and "test_policy.label" in script)
    add(results, "script verifies proposal approval preflight apply", all(token in script for token in ("find_latest_proposal_artifact", "find_latest_approval_artifact", "find_latest_preflight_artifact", "find_latest_apply_result_artifact")))
    add(results, "script rejects empty tests", "EMPTY_TEST_PLAN" in script)
    add(results, "script uses proposal tests_recommended source", "proposal.tests_recommended" in script)
    add(results, "script uses canonical trusted command IDs", "test_policy.commands" in script and "test_policy.aliases" not in script)
    add(results, "script keeps command cwd logical", 'LOGICAL_WORKING_DIRECTORY = "."' in script)
    add(
        results,
        "script keeps trusted support on PYTHONPATH",
        "python_path = [str(support_dir)]" in script,
    )
    add(results, "script appends worktree after trusted support path", "python_path.append(str(worktree))" in script)
    add(results, "script prevents Python cwd module shadowing", 'env["PYTHONSAFEPATH"] = "1"' in script)
    add(results, "script reads canonical apply patch_file_hash", '"patch_file_hash"' in script)
    add(results, "script rejects invalid test context before execution", "validate_test_context_contract" in script)
    add(results, "script has no legacy patch_hash context lookup", 'context["patch_hash"]' not in script)
    add(results, "script uses shell false subprocess", "shell=True" not in script and "subprocess.run(" in script)
    add(results, "script forbids inline python command", "INLINE_CODE_REJECTED" in script)
    add(results, "script forbids shell runners", "FORBIDDEN_COMMAND_WORDS" in script and "bash" in script)
    add(results, "script strips credential env for test process", "FORBIDDEN_ENV_KEYS" in script and "test_environment" in script)
    add(results, "script records network isolation honestly", "network_isolation_enforced" in script)
    add(results, "script enforces output limits", "stdout_max_bytes" in script and "stderr_max_bytes" in script)
    add(results, "script detects test-generated changes", "post_test_changes" in script)
    add(results, "script cleans up sandbox", "cleanup_paths" in script)
    add(results, "test marker is implemented", "<!-- namma-ai-sandbox-test -->" in script)
    add(results, "policy defines fixed test label", "label: ai-fix-test-sandbox" in policy)
    add(results, "policy has no natural-language alias section", "\naliases:" not in policy)
    for command_id in (
        "unit",
        "stage2c-targeted",
        "workflow-checkers",
        "compileall",
        "stage2c-b1-clamp",
    ):
        add(results, f"policy defines fixed command {command_id}", f"  {command_id}: python3|-m|unittest|" in policy)
    add(results, "policy defines fixed unittest command", "python3|-m|unittest|stage2c_b1_clamp_tests" in policy)
    for module in sorted(sandbox_test_command_modules(policy)):
        support_path = f"scripts/sandbox_test_support/{module}.py"
        add(
            results,
            f"workflow downloads trusted support module {module}",
            support_path in test_job,
        )
    add(
        results,
        "workflow downloads trusted support helpers",
        "scripts/sandbox_test_support/support_paths.py" in test_job,
    )
    add(results, "policy declares network isolation false", "network_isolation_enforced: false" in policy)
    return results


def check_forbidden(text: str, script: str) -> list[CheckResult]:
    results: list[CheckResult] = []
    sanitized_script = script.replace('"OPENAI_API_KEY"', '"FORBIDDEN_ENV"')
    lowered = (text + "\n" + sanitized_script).lower()
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
        "bash -c",
        "sh -c",
        "eval ",
        "shell=true",
    ):
        add(results, f"sandbox test automation does not contain {token}", token not in lowered)
    add(results, "sandbox test does not use pull_request_target", "pull_request_target" not in lowered)
    return results


def check_schema() -> list[CheckResult]:
    schema = load_text(SCHEMA_PATH)
    results: list[CheckResult] = []
    add(results, "test result schema has SANDBOX_TEST phase", '"SANDBOX_TEST"' in schema)
    add(results, "test result schema has TESTS_PASSED", '"TESTS_PASSED"' in schema)
    add(results, "test result schema has TEST_COMMAND_REJECTED", '"TEST_COMMAND_REJECTED"' in schema)
    add(results, "test result schema records sandbox apply hash", "sandbox_apply_result_hash" in schema)
    add(results, "test result schema records canonical patch_file_hash", '"patch_file_hash"' in schema)
    add(results, "test result schema does not accept patch_hash alias", '"patch_hash"' not in schema)
    add(results, "test result schema keeps working_directory logical", '"working_directory": {\n          "const": "."' in schema)
    add(results, "test result schema rejects trusted support cwd", "trusted-support" not in schema)
    add(results, "test result schema records stdout and stderr hashes", "stdout_hashes" in schema and "stderr_hashes" in schema)
    add(results, "test result schema records no persistent writes", "persistent_repository_modified" in schema and "commit_performed" in schema)
    return results


def run_checks() -> list[CheckResult]:
    collector = load_text(COLLECTOR_PATH)
    test_workflow = load_text(TEST_PATH)
    script = load_text(SCRIPT_PATH)
    results: list[CheckResult] = []
    results.extend(check_action_pinning(collector + "\n" + test_workflow))
    results.extend(check_collector(collector))
    results.extend(check_test_workflow(test_workflow))
    results.extend(check_forbidden(collector + "\n" + test_workflow, script))
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
        print(f"\n{len(failed)} sandbox test workflow check(s) failed.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
