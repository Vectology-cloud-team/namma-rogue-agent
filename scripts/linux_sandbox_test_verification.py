#!/usr/bin/env python3
"""Collect Linux evidence for trusted sandbox test execution.

This script is used by the Linux verification workflow. It intentionally
uses only the Python standard library and repository files.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTROL_ROOT = REPO_ROOT
POLICY_PATH = REPO_ROOT / ".github" / "codex" / "sandbox-test-policy.yml"
FIX_POLICY_PATH = REPO_ROOT / ".github" / "codex" / "fix-policy.yml"
SANDBOX_TEST_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "fix-sandbox-test.yml"
SUPPORT_DIR = REPO_ROOT / "scripts" / "sandbox_test_support"
WINDOWS_PYTHON3_SKIP_REASON = "python3 is unavailable locally"
EXPLAINED_LINUX_SKIP_REASONS = {
    "set ROGUE_BINARY to run the Rogue launch test",
}
EXPECTED_TEST_IDS = (
    "unit",
    "stage2c-targeted",
    "workflow-checkers",
    "compileall",
    "stage2c-b1-clamp",
)
SECRET_ENV_KEYS = (
    "GITHUB_TOKEN",
    "OPENAI_API_KEY",
    "ACTIONS_ID_TOKEN_REQUEST_TOKEN",
)
RESULT_LINE_RE = re.compile(
    r"^(?P<label>.+?) \((?P<test_id>[^)]+)\) \.\.\. (?P<status>.+)$"
)
RUN_COUNT_RE = re.compile(r"Ran (?P<count>\d+) tests?")
SUMMARY_FIELD_RE = re.compile(r"([A-Za-z ]+)=([0-9]+)")


def configure_roots(*, target_root: Path, control_root: Path) -> None:
    global REPO_ROOT
    global CONTROL_ROOT
    global POLICY_PATH
    global FIX_POLICY_PATH
    global SANDBOX_TEST_WORKFLOW
    global SUPPORT_DIR

    REPO_ROOT = target_root.resolve()
    CONTROL_ROOT = control_root.resolve()
    POLICY_PATH = CONTROL_ROOT / ".github" / "codex" / "sandbox-test-policy.yml"
    FIX_POLICY_PATH = CONTROL_ROOT / ".github" / "codex" / "fix-policy.yml"
    SANDBOX_TEST_WORKFLOW = (
        CONTROL_ROOT / ".github" / "workflows" / "fix-sandbox-test.yml"
    )
    SUPPORT_DIR = CONTROL_ROOT / "scripts" / "sandbox_test_support"


@dataclass(frozen=True)
class CommandResult:
    argv: tuple[str, ...]
    returncode: int
    output: str
    log_path: str
    timed_out: bool = False
    output_truncated: bool = False


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def write_json(path: Path, value: Any) -> None:
    write_text(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def parse_sandbox_policy(path: Path) -> dict[str, Any]:
    policy: dict[str, Any] = {
        "limits": {
            "command_timeout_seconds": 120,
            "stdout_max_bytes": 1048576,
            "stderr_max_bytes": 1048576,
        },
        "allowed_environment": (),
    }
    in_limits = False
    in_allowed_environment = False
    allowed: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if line == "limits:":
            in_limits = True
            in_allowed_environment = False
            continue
        if line == "allowed_environment:":
            in_limits = False
            in_allowed_environment = True
            continue
        if stripped and not line.startswith(" "):
            in_limits = False
            in_allowed_environment = False
        if in_limits and stripped:
            key, separator, value = stripped.partition(":")
            if separator:
                policy["limits"][key] = int(value.strip())
        if in_allowed_environment and stripped.startswith("- "):
            allowed.append(stripped[2:])
    policy["allowed_environment"] = tuple(allowed)
    return policy


def command_environment() -> dict[str, str]:
    policy = parse_sandbox_policy(POLICY_PATH)
    allowed = set(policy["allowed_environment"])
    env = {
        key: value
        for key, value in os.environ.items()
        if key in allowed
    }
    python_path = [str(SUPPORT_DIR), str(REPO_ROOT)]
    existing_python_path = os.environ.get("PYTHONPATH")
    if existing_python_path:
        python_path.append(existing_python_path)
    env["PYTHONPATH"] = os.pathsep.join(python_path)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def read_limited_text(path: Path, max_bytes: int) -> tuple[str, bool]:
    data = path.read_bytes()
    truncated = len(data) > max_bytes
    if truncated:
        data = data[:max_bytes]
    text = data.decode("utf-8", errors="replace")
    if truncated:
        text += "\n[output truncated by Linux verification]\n"
    return text, truncated


def run_command(argv: list[str], *, output_dir: Path, log_name: str) -> CommandResult:
    policy = parse_sandbox_policy(POLICY_PATH)
    timeout = int(policy["limits"]["command_timeout_seconds"])
    max_output = int(policy["limits"]["stdout_max_bytes"]) + int(
        policy["limits"]["stderr_max_bytes"]
    )
    env = command_environment()
    log_path = output_dir / log_name
    log_path.parent.mkdir(parents=True, exist_ok=True)
    timed_out = False
    returncode = 0
    with log_path.open("wb") as output:
        try:
            completed = subprocess.run(
                argv,
                cwd=SUPPORT_DIR,
                env=env,
                stdout=output,
                stderr=subprocess.STDOUT,
                timeout=timeout,
                check=False,
            )
            returncode = completed.returncode
        except subprocess.TimeoutExpired:
            timed_out = True
            returncode = 124
            output.write(b"\n[command timed out]\n")
    output_text, output_truncated = read_limited_text(log_path, max_output)
    return CommandResult(
        argv=tuple(argv),
        returncode=returncode,
        output=output_text,
        log_path=str(log_path.relative_to(output_dir)),
        timed_out=timed_out,
        output_truncated=output_truncated,
    )


def parse_unittest_output(command: CommandResult) -> dict[str, Any]:
    successes: list[str] = []
    failures: list[str] = []
    errors: list[str] = []
    skipped: list[dict[str, str]] = []
    expected_failures: list[str] = []
    unexpected_successes: list[str] = []
    total = 0

    for line in command.output.splitlines():
        run_match = RUN_COUNT_RE.search(line)
        if run_match:
            total = int(run_match.group("count"))
        match = RESULT_LINE_RE.match(line)
        if not match:
            continue
        test_id = match.group("test_id")
        status = match.group("status")
        if status == "ok":
            successes.append(test_id)
        elif status == "FAIL":
            failures.append(test_id)
        elif status == "ERROR":
            errors.append(test_id)
        elif status.startswith("skipped "):
            reason = status.removeprefix("skipped ").strip()
            if len(reason) >= 2 and reason[0] == reason[-1] and reason[0] in {"'", '"'}:
                reason = reason[1:-1]
            skipped.append({"test": test_id, "reason": reason})
        elif status == "expected failure":
            expected_failures.append(test_id)
        elif status == "unexpected success":
            unexpected_successes.append(test_id)

    summary_counts = {
        "failures": len(failures),
        "errors": len(errors),
        "skipped": len(skipped),
        "expected_failures": len(expected_failures),
        "unexpected_successes": len(unexpected_successes),
    }
    for line in reversed(command.output.splitlines()):
        if line.startswith(("OK", "FAILED")):
            for raw_name, raw_value in SUMMARY_FIELD_RE.findall(line):
                normalized = raw_name.strip().lower().replace(" ", "_")
                if normalized == "expected_failures":
                    normalized = "expected_failures"
                elif normalized == "unexpected_successes":
                    normalized = "unexpected_successes"
                summary_counts[normalized] = int(raw_value)
            break

    passed = max(
        0,
        total
        - summary_counts.get("failures", 0)
        - summary_counts.get("errors", 0)
        - summary_counts.get("skipped", 0)
        - summary_counts.get("expected_failures", 0)
        - summary_counts.get("unexpected_successes", 0),
    )
    return {
        "argv": list(command.argv),
        "returncode": command.returncode,
        "log_path": command.log_path,
        "run": total,
        "passed": passed,
        "failures": summary_counts.get("failures", 0),
        "errors": summary_counts.get("errors", 0),
        "skipped": summary_counts.get("skipped", 0),
        "expected_failures": summary_counts.get("expected_failures", 0),
        "unexpected_successes": summary_counts.get("unexpected_successes", 0),
        "timed_out": command.timed_out,
        "output_truncated": command.output_truncated,
        "successes": sorted(successes),
        "failure_tests": sorted(failures),
        "error_tests": sorted(errors),
        "skipped_tests": sorted(skipped, key=lambda item: item["test"]),
        "expected_failure_tests": sorted(expected_failures),
        "unexpected_success_tests": sorted(unexpected_successes),
    }


def command_version(argv: list[str]) -> str:
    try:
        completed = subprocess.run(
            argv,
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
    except OSError as exc:
        return f"unavailable: {exc}"
    return completed.stdout.strip()


def environment_summary() -> tuple[dict[str, Any], str]:
    python_path = shutil.which("python")
    python3_path = shutil.which("python3")
    lines = [
        f"uname -a: {command_version(['uname', '-a'])}",
        f"python --version: {command_version(['python', '--version'])}",
        f"python3 --version: {command_version(['python3', '--version'])}",
        f"command -v python: {python_path or ''}",
        f"command -v python3: {python3_path or ''}",
        f"sys.executable: {sys.executable}",
        f"platform.platform(): {platform.platform()}",
        f"cwd: {Path.cwd()}",
    ]
    summary = {
        "os": platform.system(),
        "runner": os.environ.get("RUNNER_OS", ""),
        "python_path": python_path,
        "python3_path": python3_path,
        "python_version": command_version(["python", "--version"]),
        "python3_version": command_version(["python3", "--version"]),
        "sys_executable": sys.executable,
        "platform": platform.platform(),
        "cwd": str(Path.cwd()),
        "target_root": str(REPO_ROOT),
        "control_root": str(CONTROL_ROOT),
    }
    return summary, "\n".join(lines) + "\n"


def parse_command_policy(path: Path) -> dict[str, tuple[str, ...]]:
    commands: dict[str, tuple[str, ...]] = {}
    in_commands = False
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        if line == "commands:":
            in_commands = True
            continue
        if in_commands and line and not line.startswith(" "):
            break
        if not in_commands or not line.strip():
            continue
        key, separator, value = line.strip().partition(":")
        if not separator:
            continue
        commands[key] = tuple(part for part in value.strip().split("|") if part)
    return commands


def parse_fix_policy_ids(path: Path) -> tuple[str, ...]:
    ids: list[str] = []
    in_ids = False
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        if line == "sandbox_test_ids:":
            in_ids = True
            continue
        if in_ids and line and not line.startswith(" "):
            break
        if in_ids and line.strip().startswith("- "):
            ids.append(line.strip()[2:])
    return tuple(ids)


def workflow_downloaded_support_modules(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    return {
        match.group(1)
        for match in re.finditer(
            r"scripts/sandbox_test_support/([A-Za-z0-9_]+)\.py",
            text,
        )
    }


def support_module_hashes(commands: dict[str, tuple[str, ...]]) -> dict[str, dict[str, str]]:
    modules = {argv[3] for argv in commands.values() if len(argv) >= 4}
    modules.add("support_paths")
    result: dict[str, dict[str, str]] = {}
    for module in sorted(modules):
        path = SUPPORT_DIR / f"{module}.py"
        data = path.read_bytes()
        result[module] = {
            "path": str(path.relative_to(CONTROL_ROOT)).replace("\\", "/"),
            "sha256": sha256_bytes(data),
            "bytes": str(len(data)),
            "exists": str(path.is_file()).lower(),
        }
    return result


def source_python3_skip_tests(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    module_name = ".".join(path.relative_to(REPO_ROOT).with_suffix("").parts)
    found: list[str] = []
    for class_node in [node for node in tree.body if isinstance(node, ast.ClassDef)]:
        for node in class_node.body:
            if not isinstance(node, ast.FunctionDef):
                continue
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call) or len(decorator.args) < 2:
                    continue
                function = decorator.func
                is_skip_unless = (
                    isinstance(function, ast.Attribute)
                    and function.attr == "skipUnless"
                    or isinstance(function, ast.Name)
                    and function.id == "skipUnless"
                )
                if not is_skip_unless:
                    continue
                reason = decorator.args[1]
                if (
                    isinstance(reason, ast.Constant)
                    and reason.value == WINDOWS_PYTHON3_SKIP_REASON
                ):
                    found.append(f"{module_name}.{class_node.name}.{node.name}")
    return sorted(found)


def classify_skips(
    full: dict[str, Any],
    targeted: dict[str, Any],
    expected_windows_python3_skips: list[str],
) -> dict[str, Any]:
    full_skips = {item["test"]: item["reason"] for item in full["skipped_tests"]}
    targeted_skips = {item["test"]: item["reason"] for item in targeted["skipped_tests"]}
    success_names = set(full["successes"]) | set(targeted["successes"])
    recovered = [
        test_id
        for test_id in expected_windows_python3_skips
        if test_id in success_names
    ]
    still_skipped = [
        {"test": test_id, "reason": full_skips.get(test_id) or targeted_skips.get(test_id, "")}
        for test_id in expected_windows_python3_skips
        if test_id in full_skips or test_id in targeted_skips
    ]
    unexpected = [
        item
        for item in full["skipped_tests"] + targeted["skipped_tests"]
        if item["reason"] not in EXPLAINED_LINUX_SKIP_REASONS
    ]
    return {
        "windows_python3_skips_identified": expected_windows_python3_skips,
        "windows_python3_skips_recovered": recovered,
        "windows_python3_skips_still_skipped": still_skipped,
        "unexpected_linux_skips": unexpected,
    }


def trusted_policy_summary() -> dict[str, Any]:
    commands = parse_command_policy(POLICY_PATH)
    fix_policy_ids = parse_fix_policy_ids(FIX_POLICY_PATH)
    downloaded_modules = workflow_downloaded_support_modules(SANDBOX_TEST_WORKFLOW)
    command_modules = {argv[3] for argv in commands.values() if len(argv) >= 4}
    expected_downloads = set(command_modules) | {"support_paths"}
    support_hashes = support_module_hashes(commands)
    duplicate_mapping = len(commands) != len(set(commands))
    unknown_policy_ids = sorted(set(fix_policy_ids) - set(commands))
    missing_fix_policy_ids = sorted(set(EXPECTED_TEST_IDS) - set(fix_policy_ids))
    missing_commands = sorted(set(fix_policy_ids) - set(commands))
    missing_downloads = sorted(expected_downloads - downloaded_modules)
    orphan_downloads = sorted(downloaded_modules - expected_downloads)
    orphan_support_modules = sorted(
        path.stem
        for path in SUPPORT_DIR.glob("*.py")
        if path.stem not in expected_downloads
    )
    canonical_commands = {test_id: list(argv) for test_id, argv in sorted(commands.items())}
    return {
        "trusted_test_ids": list(fix_policy_ids),
        "policy_command_ids": sorted(commands),
        "canonical_commands": canonical_commands,
        "sandbox_test_policy_hash": sha256_bytes(POLICY_PATH.read_bytes()),
        "fix_policy_hash": sha256_bytes(FIX_POLICY_PATH.read_bytes()),
        "downloaded_support_modules": sorted(downloaded_modules),
        "expected_download_modules": sorted(expected_downloads),
        "support_module_paths": {
            module: value["path"] for module, value in support_hashes.items()
        },
        "support_module_hashes": support_hashes,
        "policy_download_list_match": not missing_downloads and not orphan_downloads,
        "duplicate_mapping": duplicate_mapping,
        "unknown_policy_ids": unknown_policy_ids,
        "missing_fix_policy_ids": missing_fix_policy_ids,
        "missing_commands": missing_commands,
        "missing_downloads": missing_downloads,
        "orphan_downloads": orphan_downloads,
        "orphan_support_modules": orphan_support_modules,
        "stage2c_b1_clamp_argv": list(commands.get("stage2c-b1-clamp", ())),
    }


def forbidden_secret_environment_present() -> list[str]:
    env = command_environment()
    return sorted(key for key in SECRET_ENV_KEYS if env.get(key))


def determine_status(
    *,
    env: dict[str, Any],
    full: dict[str, Any],
    targeted: dict[str, Any],
    skip_info: dict[str, Any],
    policy: dict[str, Any],
) -> str:
    if not env.get("python3_path"):
        return "INTERNAL_ERROR"
    if full.get("timed_out") or targeted.get("timed_out"):
        return "TEST_FAILURE"
    if full.get("output_truncated") or targeted.get("output_truncated"):
        return "TEST_FAILURE"
    if full["returncode"] != 0 or targeted["returncode"] != 0:
        return "TEST_FAILURE"
    if policy["missing_commands"] or policy["missing_downloads"] or policy["orphan_downloads"]:
        return "POLICY_MISMATCH"
    if policy["unknown_policy_ids"] or policy["missing_fix_policy_ids"]:
        return "POLICY_MISMATCH"
    if policy["duplicate_mapping"] or policy["orphan_support_modules"]:
        return "POLICY_MISMATCH"
    if policy["stage2c_b1_clamp_argv"] != [
        "python3",
        "-m",
        "unittest",
        "stage2c_b1_clamp_tests",
    ]:
        return "POLICY_MISMATCH"
    expected = set(skip_info["windows_python3_skips_identified"])
    recovered = set(skip_info["windows_python3_skips_recovered"])
    if expected != recovered:
        return "UNEXPECTED_SKIP"
    if skip_info["unexpected_linux_skips"]:
        return "UNEXPECTED_SKIP"
    shadow_test = (
        "tests.test_sandbox_test.SandboxTestTests."
        "test_worktree_cannot_shadow_trusted_support_test_module"
    )
    if shadow_test not in set(full["successes"]) | set(targeted["successes"]):
        return "MODULE_BINDING_FAILURE"
    if forbidden_secret_environment_present():
        return "INTERNAL_ERROR"
    return "VERIFIED"


def policy_execution_plan() -> dict[str, list[str]]:
    targeted_modules = [
        "stage2c_targeted_tests",
        "workflow_checker_tests",
        "compileall_checks",
    ]
    executed_policy_test_ids = [
        "unit",
        "stage2c-targeted",
        "workflow-checkers",
        "compileall",
    ]
    not_applicable_policy_test_ids: list[str] = []
    if (REPO_ROOT / "canary" / "stage2c_b1_clamp.py").is_file():
        targeted_modules.append("stage2c_b1_clamp_tests")
        executed_policy_test_ids.append("stage2c-b1-clamp")
    else:
        not_applicable_policy_test_ids.append("stage2c-b1-clamp")
    return {
        "targeted_modules": targeted_modules,
        "executed_policy_test_ids": executed_policy_test_ids,
        "not_applicable_policy_test_ids": not_applicable_policy_test_ids,
    }


def run_verification(output_dir: Path) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    env, env_text = environment_summary()
    write_text(output_dir / "environment.txt", env_text)
    if not env.get("python3_path"):
        summary = {
            "schema_version": "trusted-sandbox-test-linux-verification-v1",
            **env,
            "main_sha": os.environ.get("MAIN_SHA", ""),
            "trigger_head_sha": os.environ.get("TRIGGER_HEAD_SHA", ""),
            "verification_scope": os.environ.get(
                "VERIFICATION_SCOPE",
                "default-branch-control-plane",
            ),
            "status": "INTERNAL_ERROR",
            "failure_reason": "python3 is unavailable",
        }
        write_json(output_dir / "linux-verification-summary.json", summary)
        return 1

    full_command = [
        "python3",
        "-m",
        "unittest",
        "unit_tests",
        "-v",
    ]
    execution_plan = policy_execution_plan()
    targeted_command = [
        "python3",
        "-m",
        "unittest",
        *execution_plan["targeted_modules"],
        "-v",
    ]
    full = parse_unittest_output(
        run_command(full_command, output_dir=output_dir, log_name="full-unit.log")
    )
    targeted = parse_unittest_output(
        run_command(
            targeted_command,
            output_dir=output_dir,
            log_name="targeted-tests.log",
        )
    )
    policy = trusted_policy_summary()
    skipped_tests = source_python3_skip_tests(REPO_ROOT / "tests" / "test_sandbox_test.py")
    skip_info = classify_skips(full, targeted, skipped_tests)
    shadowing_passed = (
        "tests.test_sandbox_test.SandboxTestTests."
        "test_worktree_cannot_shadow_trusted_support_test_module"
    ) in set(full["successes"]) | set(targeted["successes"])
    status = determine_status(
        env=env,
        full=full,
        targeted=targeted,
        skip_info=skip_info,
        policy=policy,
    )
    summary = {
        "schema_version": "trusted-sandbox-test-linux-verification-v1",
        **env,
        "main_sha": os.environ.get("MAIN_SHA", ""),
        "trigger_head_sha": os.environ.get("TRIGGER_HEAD_SHA", ""),
        "verification_scope": os.environ.get(
            "VERIFICATION_SCOPE",
            "default-branch-control-plane",
        ),
        "full_tests_run": full["run"],
        "full_passed": full["passed"],
        "full_failures": full["failures"],
        "full_errors": full["errors"],
        "full_skipped": full["skipped"],
        "full_expected_failures": full["expected_failures"],
        "full_unexpected_successes": full["unexpected_successes"],
        "full_timed_out": full["timed_out"],
        "full_output_truncated": full["output_truncated"],
        "full_skipped_tests": full["skipped_tests"],
        "targeted_tests_run": targeted["run"],
        "targeted_passed": targeted["passed"],
        "targeted_failures": targeted["failures"],
        "targeted_errors": targeted["errors"],
        "targeted_skipped": targeted["skipped"],
        "targeted_expected_failures": targeted["expected_failures"],
        "targeted_unexpected_successes": targeted["unexpected_successes"],
        "targeted_timed_out": targeted["timed_out"],
        "targeted_output_truncated": targeted["output_truncated"],
        "targeted_skipped_tests": targeted["skipped_tests"],
        **skip_info,
        "trusted_test_ids": policy["trusted_test_ids"],
        "executed_policy_test_ids": execution_plan["executed_policy_test_ids"],
        "not_applicable_policy_test_ids": execution_plan[
            "not_applicable_policy_test_ids"
        ],
        "canonical_commands": policy["canonical_commands"],
        "support_module_paths": policy["support_module_paths"],
        "support_module_hashes": {
            module: value["sha256"]
            for module, value in policy["support_module_hashes"].items()
        },
        "policy_download_list_match": policy["policy_download_list_match"],
        "shadowing_protection_passed": shadowing_passed,
        "secret_environment_keys_present": forbidden_secret_environment_present(),
        "status": status,
    }
    write_json(output_dir / "skipped-tests.json", skip_info)
    write_json(output_dir / "trusted-test-policy-summary.json", policy)
    write_json(
        output_dir / "trusted-support-module-hashes.json",
        policy["support_module_hashes"],
    )
    write_json(output_dir / "linux-verification-summary.json", summary)
    return 0 if status == "VERIFIED" else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("linux-verification-results"),
    )
    parser.add_argument(
        "--target-root",
        type=Path,
        default=REPO_ROOT,
        help="Repository worktree whose tests are verified.",
    )
    parser.add_argument(
        "--control-root",
        type=Path,
        default=CONTROL_ROOT,
        help="Trusted control-plane checkout containing policies and support modules.",
    )
    args = parser.parse_args()
    configure_roots(target_root=args.target_root, control_root=args.control_root)
    return run_verification(args.output_dir)


if __name__ == "__main__":
    raise SystemExit(main())
