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
TRUSTED_OPTIONAL_TEST_ROOT_PREFIXES = ("tests",)
APPROVED_ROGUE_LAUNCH_SKIP_REASON = "set ROGUE_BINARY to run the Rogue launch test"
APPROVED_ENVIRONMENTAL_SKIP_REASONS = {
    "test_rogue_launch.RogueLaunchTest.test_launch_new_game_and_quit": (
        APPROVED_ROGUE_LAUNCH_SKIP_REASON
    ),
    "test_rogue_launch.RogueLaunchTest.test_suspend_resume_accepts_input_and_quits": (
        APPROVED_ROGUE_LAUNCH_SKIP_REASON
    ),
}
SHADOWING_PROTECTION_TEST_ID = (
    "test_sandbox_test.SandboxTestTests."
    "test_worktree_cannot_shadow_trusted_support_test_module"
)
EXPECTED_TEST_IDS = (
    "unit",
    "stage2c-targeted",
    "workflow-checkers",
    "compileall",
    "stage2c-b1-clamp",
)
EXPECTED_POLICY_COMMANDS = {
    "unit": ("python3", "-m", "unittest", "unit_tests"),
    "stage2c-targeted": ("python3", "-m", "unittest", "stage2c_targeted_tests"),
    "workflow-checkers": ("python3", "-m", "unittest", "workflow_checker_tests"),
    "compileall": ("python3", "-m", "unittest", "compileall_checks"),
    "stage2c-b1-clamp": ("python3", "-m", "unittest", "stage2c_b1_clamp_tests"),
}
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
TEST_ID_COMPONENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


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


def canonical_unittest_id(raw_id: str) -> str:
    text = raw_id.strip()
    if not text:
        raise ValueError("empty unittest ID")
    parts = text.split(".")
    if any(not part or not TEST_ID_COMPONENT_RE.fullmatch(part) for part in parts):
        raise ValueError(f"malformed unittest ID: {raw_id!r}")
    if parts[0] in TRUSTED_OPTIONAL_TEST_ROOT_PREFIXES:
        parts = parts[1:]
    if len(parts) != 3:
        raise ValueError(f"unexpected unittest ID shape: {raw_id!r}")
    module_name, class_name, method_name = parts
    if not module_name.startswith("test_"):
        raise ValueError(f"unexpected unittest module: {raw_id!r}")
    if not method_name.startswith("test_"):
        raise ValueError(f"unexpected unittest method: {raw_id!r}")
    return ".".join((module_name, class_name, method_name))


def canonical_unittest_id_or_raw(raw_id: str) -> str:
    try:
        return canonical_unittest_id(raw_id)
    except ValueError:
        return raw_id.strip()


def canonical_unittest_ids(raw_ids: list[str]) -> list[str]:
    return sorted({canonical_unittest_id(test_id) for test_id in raw_ids})


def canonical_test_set(result: dict[str, Any], key: str) -> set[str]:
    return {
        canonical_unittest_id_or_raw(test_id)
        for test_id in result.get(key, [])
    }


def canonical_skip_items(result: dict[str, Any]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for item in result.get("skipped_tests", []):
        raw_test = item.get("raw_test") or item.get("test", "")
        canonical_test = canonical_unittest_id_or_raw(item.get("test", raw_test))
        items.append(
            {
                "test": canonical_test,
                "raw_test": raw_test,
                "reason": item.get("reason", ""),
            }
        )
    return items


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
        raw_test_id = match.group("test_id").strip()
        test_id = canonical_unittest_id_or_raw(raw_test_id)
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
            skipped.append(
                {
                    "test": test_id,
                    "raw_test": raw_test_id,
                    "reason": reason,
                }
            )
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


def parse_command_policy_duplicate_ids(path: Path) -> tuple[str, ...]:
    seen: set[str] = set()
    duplicates: set[str] = set()
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
        key, separator, _value = line.strip().partition(":")
        if not separator:
            continue
        if key in seen:
            duplicates.add(key)
        seen.add(key)
    return tuple(sorted(duplicates))


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
        data = path.read_bytes() if path.is_file() else b""
        result[module] = {
            "path": str(path.relative_to(CONTROL_ROOT)).replace("\\", "/"),
            "sha256": sha256_bytes(data) if path.is_file() else "",
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
                    found.append(
                        canonical_unittest_id(
                            f"{module_name}.{class_node.name}.{node.name}"
                        )
                    )
    return sorted(found)


def classify_skips(
    full: dict[str, Any],
    targeted: dict[str, Any],
    expected_windows_python3_skips: list[str],
    *,
    rogue_binary_present: bool = False,
) -> dict[str, Any]:
    expected = canonical_unittest_ids(expected_windows_python3_skips)
    full_skip_items = canonical_skip_items(full)
    targeted_skip_items = canonical_skip_items(targeted)
    skip_items = full_skip_items + targeted_skip_items
    full_skips = {item["test"]: item["reason"] for item in full_skip_items}
    targeted_skips = {item["test"]: item["reason"] for item in targeted_skip_items}
    success_names = canonical_test_set(full, "successes") | canonical_test_set(
        targeted,
        "successes",
    )
    failure_names = canonical_test_set(full, "failure_tests") | canonical_test_set(
        targeted,
        "failure_tests",
    )
    error_names = canonical_test_set(full, "error_tests") | canonical_test_set(
        targeted,
        "error_tests",
    )
    skipped_names = set(full_skips) | set(targeted_skips)
    has_failures_or_errors = bool(failure_names or error_names)
    recovered = [
        test_id
        for test_id in expected
        if test_id in success_names
    ]
    observed_on_linux = [
        test_id
        for test_id in expected
        if test_id in success_names
        or test_id in failure_names
        or test_id in error_names
        or test_id in skipped_names
    ]
    still_skipped = [
        {"test": test_id, "reason": full_skips.get(test_id) or targeted_skips.get(test_id, "")}
        for test_id in expected
        if test_id in full_skips or test_id in targeted_skips
    ]
    failed = [
        test_id
        for test_id in expected
        if test_id in failure_names or test_id in error_names
    ]
    expected_environmental_skips: list[dict[str, str]] = []
    unexpected: list[dict[str, str]] = []
    for item in skip_items:
        expected_reason = APPROVED_ENVIRONMENTAL_SKIP_REASONS.get(item["test"])
        if (
            expected_reason is not None
            and item["reason"] == expected_reason
            and not rogue_binary_present
            and not has_failures_or_errors
        ):
            expected_environmental_skips.append(item)
        else:
            unexpected.append(item)
    required_evidence_passed = set(expected).issubset(success_names)
    shadowing_protection_passed = SHADOWING_PROTECTION_TEST_ID in success_names
    return {
        "windows_python3_skips_identified": expected,
        "windows_python3_skips_observed_on_linux": observed_on_linux,
        "windows_python3_skips_recovered": recovered,
        "windows_python3_skips_still_skipped": still_skipped,
        "windows_python3_skips_failed": failed,
        "recovered_windows_python3_tests": recovered,
        "skipped_tests": skip_items,
        "expected_environmental_skips": expected_environmental_skips,
        "unexpected_linux_skips": unexpected,
        "unexpected_skips": unexpected,
        "required_evidence_tests": expected,
        "required_evidence_passed": required_evidence_passed,
        "shadowing_protection_passed": shadowing_protection_passed,
    }


def trusted_policy_summary() -> dict[str, Any]:
    commands = parse_command_policy(POLICY_PATH)
    duplicate_command_ids = parse_command_policy_duplicate_ids(POLICY_PATH)
    fix_policy_ids = parse_fix_policy_ids(FIX_POLICY_PATH)
    downloaded_modules = workflow_downloaded_support_modules(SANDBOX_TEST_WORKFLOW)
    command_modules = {argv[3] for argv in commands.values() if len(argv) >= 4}
    expected_downloads = set(command_modules) | {"support_paths"}
    support_hashes = support_module_hashes(commands)
    duplicate_mapping = bool(duplicate_command_ids)
    command_argv_mismatches = {
        test_id: {
            "expected": list(expected),
            "actual": list(commands.get(test_id, ())),
        }
        for test_id, expected in EXPECTED_POLICY_COMMANDS.items()
        if commands.get(test_id) != expected
    }
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
        "duplicate_command_ids": list(duplicate_command_ids),
        "policy_command_argv_match": not command_argv_mismatches,
        "command_argv_mismatches": command_argv_mismatches,
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
    if full.get("failures") or targeted.get("failures"):
        return "TEST_FAILURE"
    if full.get("errors") or targeted.get("errors"):
        return "TEST_FAILURE"
    if full["returncode"] != 0 or targeted["returncode"] != 0:
        return "TEST_FAILURE"
    if policy["missing_commands"] or policy["missing_downloads"] or policy["orphan_downloads"]:
        return "POLICY_MISMATCH"
    if policy["unknown_policy_ids"] or policy["missing_fix_policy_ids"]:
        return "POLICY_MISMATCH"
    if policy["command_argv_mismatches"]:
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
    if expected != recovered or not skip_info.get("required_evidence_passed", False):
        return "MODULE_BINDING_FAILURE"
    if not skip_info.get("shadowing_protection_passed", False):
        return "MODULE_BINDING_FAILURE"
    if skip_info["unexpected_linux_skips"]:
        return "UNEXPECTED_SKIP"
    if forbidden_secret_environment_present():
        return "INTERNAL_ERROR"
    return "VERIFIED"


def policy_execution_plan() -> dict[str, list[str]]:
    commands = parse_command_policy(POLICY_PATH)
    targeted_modules = [
        commands[test_id][3]
        for test_id in (
            "stage2c-targeted",
            "workflow-checkers",
            "compileall",
        )
        if len(commands.get(test_id, ())) >= 4
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


def policy_test_execution_status(
    *,
    execution_plan: dict[str, list[str]],
    policy: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    target_available = (REPO_ROOT / "canary" / "stage2c_b1_clamp.py").is_file()
    command_binding_verified = policy["stage2c_b1_clamp_argv"] == [
        "python3",
        "-m",
        "unittest",
        "stage2c_b1_clamp_tests",
    ]
    return {
        "stage2c-b1-clamp": {
            "command_binding_verified": command_binding_verified,
            "runtime_target_available": target_available,
            "execution_status": (
                "EXECUTED"
                if "stage2c-b1-clamp" in execution_plan["executed_policy_test_ids"]
                else "NOT_APPLICABLE_DEFAULT_BRANCH"
            ),
        }
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

    policy_commands = parse_command_policy(POLICY_PATH)
    full_command = [
        *policy_commands.get("unit", EXPECTED_POLICY_COMMANDS["unit"]),
        "-v",
    ]
    execution_plan = policy_execution_plan()
    targeted_command = [
        *policy_commands.get(
            "stage2c-targeted",
            EXPECTED_POLICY_COMMANDS["stage2c-targeted"],
        )[:3],
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
    skip_info = classify_skips(
        full,
        targeted,
        skipped_tests,
        rogue_binary_present=bool(os.environ.get("ROGUE_BINARY")),
    )
    shadowing_passed = skip_info["shadowing_protection_passed"]
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
        "policy_test_execution_status": policy_test_execution_status(
            execution_plan=execution_plan,
            policy=policy,
        ),
        "canonical_commands": policy["canonical_commands"],
        "support_module_paths": policy["support_module_paths"],
        "support_module_hashes": {
            module: value["sha256"]
            for module, value in policy["support_module_hashes"].items()
        },
        "policy_download_list_match": policy["policy_download_list_match"],
        "policy_command_argv_match": policy["policy_command_argv_match"],
        "command_argv_mismatches": policy["command_argv_mismatches"],
        "shadowing_protection_passed": shadowing_passed,
        "rogue_binary_present": bool(os.environ.get("ROGUE_BINARY")),
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
