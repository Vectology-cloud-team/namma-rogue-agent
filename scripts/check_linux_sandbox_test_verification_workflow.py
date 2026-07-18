#!/usr/bin/env python3
"""Validate the Linux trusted sandbox test verification workflow."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = (
    REPO_ROOT
    / ".github"
    / "workflows"
    / "sandbox-test-linux-verification.yml"
)
SCRIPT_PATH = REPO_ROOT / "scripts" / "linux_sandbox_test_verification.py"
POLICY_PATH = REPO_ROOT / ".github" / "codex" / "sandbox-test-policy.yml"
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
}


@dataclass(frozen=True)
class CheckResult:
    label: str
    passed: bool
    detail: str = ""


def add(results: list[CheckResult], label: str, passed: bool, detail: str = "") -> None:
    results.append(CheckResult(label, passed, detail))


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def action_uses(text: str) -> list[tuple[str, str, str | None]]:
    return [
        (match.group(1), match.group(2), match.group(3))
        for match in ACTION_USES_RE.finditer(text)
    ]


def job_section(text: str, job_name: str) -> str:
    marker = f"  {job_name}:"
    start = text.find(marker)
    if start == -1:
        return ""
    match = re.search(r"\n  [A-Za-z0-9_-]+:\n", text[start + len(marker) :])
    if not match:
        return text[start:]
    return text[start : start + len(marker) + match.start()]


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
        if len(argv) >= 4 and argv[:3] in (
            ["python3", "-m", "unittest"],
            ["python", "-m", "unittest"],
        ):
            modules.add(argv[3])
    return modules


def check_action_pinning(text: str) -> list[CheckResult]:
    results: list[CheckResult] = []
    entries = action_uses(text)
    add(
        results,
        "all Linux verification actions use full commit SHAs",
        all(FULL_SHA_RE.fullmatch(ref) for _, ref, _ in entries),
    )
    add(
        results,
        "only allowed Linux verification actions are used",
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


def check_workflow(text: str, script: str, policy: str) -> list[CheckResult]:
    results: list[CheckResult] = []
    job = job_section(text, "linux_verification")
    add(results, "workflow exists", WORKFLOW_PATH.exists())
    add(results, "workflow name is explicit", "name: Sandbox Test Linux Verification" in text)
    add(results, "workflow uses pull_request trigger", "pull_request:" in text)
    add(results, "workflow uses workflow_dispatch trigger", "workflow_dispatch:" in text)
    add(results, "workflow uses ubuntu runner", "runs-on: ubuntu-latest" in job)
    add(results, "workflow has top-level contents read", re.search(r"(?m)^permissions:\n\s+contents: read$", text) is not None)
    add(results, "job has contents read", re.search(r"(?m)^\s+permissions:\n\s+contents: read$", job) is not None)
    add(results, "workflow has no write permission", ": write" not in text)
    add(results, "checkout persists no credentials", "persist-credentials: false" in text)
    add(results, "workflow records PR and base SHA", "PR_HEAD_SHA" in text and "MAIN_SHA" in text)
    add(results, "workflow runs verification script with python3", "python3 scripts/linux_sandbox_test_verification.py" in text)
    add(results, "workflow uploads artifact", "actions/upload-artifact@" in text and "linux-verification-results" in text)
    add(results, "artifact name is verification-specific", "sandbox-test-linux-verification-${{ github.run_id }}" in text)
    add(results, "script records uname", "uname -a" in script)
    add(results, "script records python paths", "command -v python3" in script and "python3_path" in script)
    add(results, "script requires python3", "if not env.get(\"python3_path\")" in script)
    add(results, "script runs full unit discovery", "\"discover\"" in script and "\"test_*.py\"" in script)
    add(results, "script runs targeted sandbox tests", "TARGETED_MODULES" in script and "tests.test_sandbox_test" in script)
    add(results, "script records skip details", "skipped-tests.json" in script and "skipped_tests" in script)
    add(results, "script identifies Windows python3 skips", "WINDOWS_PYTHON3_SKIP_REASON" in script)
    add(results, "script records support module hashes", "trusted-support-module-hashes.json" in script)
    add(results, "script checks policy download list match", "policy_download_list_match" in script)
    add(results, "script checks shadowing protection", "test_worktree_cannot_shadow_trusted_support_test_module" in script)
    add(results, "script records final status", '"VERIFIED"' in script and '"UNEXPECTED_SKIP"' in script)
    for module in sorted(sandbox_test_command_modules(policy)):
        add(
            results,
            f"policy module {module} source exists for Linux verification",
            (REPO_ROOT / "scripts" / "sandbox_test_support" / f"{module}.py").is_file(),
        )
    return results


def check_forbidden(text: str, script: str) -> list[CheckResult]:
    results: list[CheckResult] = []
    sanitized_script = script.replace('"OPENAI_API_KEY"', '"FORBIDDEN_SECRET_KEY"')
    lowered = (text + "\n" + sanitized_script).lower()
    for token in (
        "secrets.",
        "openai_api_key",
        "openai/codex-action",
        "contents: write",
        "pull-requests: write",
        "issues: write",
        "actions: write",
        "checks: write",
        "id-token: write",
        "packages: write",
        "pip install",
        "pip3 install",
        "apt install",
        "apt-get install",
        "npm install",
        "poetry",
        "uv ",
        "git push",
        "git merge",
        "gh pr merge",
        "createcommitonbranch",
        "createpullrequest",
        "merge_pull_request",
    ):
        add(results, f"Linux verification does not contain {token}", token not in lowered)
    add(results, "workflow does not use pull_request_target", "pull_request_target" not in lowered)
    return results


def run_checks() -> list[CheckResult]:
    text = load_text(WORKFLOW_PATH) if WORKFLOW_PATH.exists() else ""
    script = load_text(SCRIPT_PATH) if SCRIPT_PATH.exists() else ""
    policy = load_text(POLICY_PATH) if POLICY_PATH.exists() else ""
    results: list[CheckResult] = []
    results.extend(check_action_pinning(text))
    results.extend(check_workflow(text, script, policy))
    results.extend(check_forbidden(text, script))
    return results


def main() -> int:
    results = run_checks()
    failed = [result for result in results if not result.passed]
    for result in results:
        prefix = "PASS" if result.passed else "FAIL"
        detail = f": {result.detail}" if result.detail else ""
        print(f"{prefix}: {result.label}{detail}")
    if failed:
        print(f"{len(failed)} Linux sandbox test verification checks failed.")
        return 1
    print(f"{len(results)} Linux sandbox test verification checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
