#!/usr/bin/env python3
"""Stage 2C-B2 approved sandbox test helpers.

This module revalidates the Stage 2A proposal, Stage 2B approval record,
Stage 2C-A preflight result, and Stage 2C-B1 sandbox apply result before it
runs any approved tests. It may check out the exact pull request HEAD into an
ephemeral sandbox, apply the approved patch there, and run only fixed argv
test commands selected by trusted policy from proposal.tests_recommended.

It must never commit, push, merge, update pull request contents, install
packages, invoke arbitrary shell, or persist repository changes.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import approval_record as approval
import architect_review_retry as stage1
import check_fix_proposal_design as proposal_design
import fix_proposal_generator as fix
import sandbox_apply as apply
import sandbox_validation as preflight


EXPECTED_REPOSITORY = "Vectology-cloud-team/namma-rogue-agent"
COLLECTOR_WORKFLOW_NAME = "Sandbox Test Request Collector"
TEST_WORKFLOW_NAME = "Sandbox Test Validator"
REQUEST_SCHEMA_VERSION = "sandbox-test-request-v1"
REQUEST_STAGE = "SANDBOX_TEST_REQUEST"
RESULT_SCHEMA_VERSION = "sandbox-test-result-v1"
RESULT_PHASE_SANDBOX_TEST = "SANDBOX_TEST"
RESULT_STATUS_TESTS_PASSED = "TESTS_PASSED"
RESULT_STATUS_TESTS_FAILED = "TESTS_FAILED"
RESULT_STATUS_TESTS_TIMEOUT = "TESTS_TIMEOUT"
RESULT_STATUS_TEST_COMMAND_REJECTED = "TEST_COMMAND_REJECTED"
RESULT_STATUS_TEST_ENVIRONMENT_REJECTED = "TEST_ENVIRONMENT_REJECTED"
RESULT_STATUS_TEST_OUTPUT_LIMIT = "TEST_OUTPUT_LIMIT"
RESULT_STATUS_ARTIFACT_INVALID = "ARTIFACT_INVALID"
RESULT_STATUS_BINDING_MISMATCH = "BINDING_MISMATCH"
RESULT_STATUS_PATCH_APPLY_FAILED = "PATCH_APPLY_FAILED"
RESULT_STATUS_INTERNAL_ERROR = "INTERNAL_ERROR"
TEST_LABEL = "ai-fix-test-sandbox"
SANDBOX_TEST_MARKER = "<!-- namma-ai-sandbox-test -->"
TEST_CONTEXT_FILE = "sandbox-test-context.json"
MAX_ARTIFACT_BYTES = 100000
ALLOWED_REPOSITORY_PERMISSIONS = {"admin", "maintain"}
ALLOWED_EXECUTABLES = {"python", "python3"}
FORBIDDEN_ENV_KEYS = {
    "ACTIONS_ID_TOKEN_REQUEST_TOKEN",
    "ACTIONS_RUNTIME_TOKEN",
    "GITHUB_TOKEN",
    "GH_TOKEN",
    "OPENAI_API_KEY",
    "PAT",
    "SSH_AUTH_SOCK",
}
FORBIDDEN_COMMAND_WORDS = {
    "bash",
    "sh",
    "zsh",
    "powershell",
    "cmd",
    "make",
    "cmake",
    "npm",
    "yarn",
    "pnpm",
    "pip",
    "pip3",
    "uv",
    "poetry",
    "cargo",
    "go",
    "docker",
    "podman",
    "curl",
    "wget",
    "git",
    "gh",
    "sudo",
    "apt",
    "apt-get",
    "brew",
    "chmod",
    "chown",
    "rm",
    "mv",
    "cp",
    "tee",
    "env",
    "xargs",
    "find",
    "sed",
    "awk",
}
FORBIDDEN_ARG_FRAGMENTS = (
    "\x00",
    "\n",
    "\r",
    ";",
    "|",
    ">",
    "<",
    "$(",
    "`",
    "*",
    "?",
    "@",
)
SAFE_MODULE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")
APPLY_ARTIFACT_FILES = {
    "sandbox-validation-result.json",
    "checkout-verification.json",
    "patch-apply-check.json",
    "changed-files.json",
    "resulting-file-hashes.json",
    "diff-binding.json",
    "git-apply.log",
}


@dataclass(frozen=True)
class TestCommandSpec:
    test_id: str
    argv: tuple[str, ...]
    working_directory: str
    timeout_seconds: int


@dataclass(frozen=True)
class SandboxTestPolicy:
    label: str
    command_timeout_seconds: int
    total_timeout_seconds: int
    stdout_max_bytes: int
    stderr_max_bytes: int
    allowed_environment: tuple[str, ...]
    commands: dict[str, TestCommandSpec]
    network_isolation_enforced: bool
    policy_hash: str


@dataclass(frozen=True)
class ApplyBundle:
    result: dict[str, Any]
    result_hash: str
    artifact_id: int
    artifact_name: str
    workflow_run_id: int
    workflow_name: str


class SandboxTestStatus(Exception):
    def __init__(self, status: str, code: str, message: str, operation: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.operation = operation


def required_env(name: str) -> str:
    return stage1.required_env(name)


def github_output(values: dict[str, str]) -> None:
    stage1.github_output(values)


def write_job_summary(text: str) -> None:
    stage1.write_job_summary(text)


def now_utc() -> str:
    return preflight.now_utc()


def read_json_file(path: Path) -> Any:
    return fix.read_json_file(path)


def write_json_file(path: Path, value: Any) -> None:
    preflight.write_json_file(path, value)


def sha256_hex_bytes(data: bytes) -> str:
    return fix.sha256_hex_bytes(data)


def sha256_hex_json(value: Any) -> str:
    return fix.sha256_hex_json(value)


def canonical_json_bytes(value: Any) -> bytes:
    return fix.canonical_json_bytes(value)


def check_result(status: str, message: str) -> dict[str, str]:
    return preflight.check_result(status, message)


def fatal(code: fix.FailureCode, message: str, operation: str) -> fix.FixProposalFailure:
    return fix.fatal(code, message, operation)


def parse_test_policy(text: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    list_sections = {"allowed_environment"}
    current_section: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line:
            continue
        if not raw_line.startswith(" "):
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            if value:
                if value.lower() in {"true", "false"}:
                    data[key] = value.lower() == "true"
                else:
                    data[key] = proposal_design.strip_yaml_scalar(value)
                current_section = None
            else:
                data[key] = [] if key in list_sections else {}
                current_section = key
            continue
        if current_section is None:
            raise fatal(
                fix.FailureCode.WORKFLOW_CONFIGURATION_ERROR,
                "unexpected indented sandbox test policy line",
                "sandbox_test_policy",
            )
        stripped = line.strip()
        if stripped.startswith("- "):
            if not isinstance(data[current_section], list):
                raise fatal(
                    fix.FailureCode.WORKFLOW_CONFIGURATION_ERROR,
                    f"section {current_section} is not a list",
                    "sandbox_test_policy",
                )
            data[current_section].append(proposal_design.strip_yaml_scalar(stripped[2:]))
            continue
        key, _, value = stripped.partition(":")
        if not value or not isinstance(data[current_section], dict):
            raise fatal(
                fix.FailureCode.WORKFLOW_CONFIGURATION_ERROR,
                "sandbox test policy supports only one-level mappings",
                "sandbox_test_policy",
            )
        data[current_section][key.strip()] = proposal_design.strip_yaml_scalar(value)
    return data


def int_policy(raw: dict[str, Any], section: str, key: str) -> int:
    parent = raw.get(section)
    if not isinstance(parent, dict) or key not in parent:
        raise fatal(
            fix.FailureCode.WORKFLOW_CONFIGURATION_ERROR,
            f"sandbox test policy missing {section}.{key}",
            "sandbox_test_policy",
        )
    try:
        value = int(str(parent[key]))
    except ValueError as exc:
        raise fatal(
            fix.FailureCode.WORKFLOW_CONFIGURATION_ERROR,
            f"sandbox test policy {section}.{key} must be an integer",
            "sandbox_test_policy",
        ) from exc
    if value <= 0:
        raise fatal(
            fix.FailureCode.WORKFLOW_CONFIGURATION_ERROR,
            f"sandbox test policy {section}.{key} must be positive",
            "sandbox_test_policy",
        )
    return value


def validate_argv(test_id: str, argv: tuple[str, ...]) -> None:
    if len(argv) < 4:
        raise SandboxTestStatus(
            RESULT_STATUS_TEST_COMMAND_REJECTED,
            "COMMAND_TOO_SHORT",
            "approved test command must include python -m unittest and a target",
            "sandbox_test_policy",
        )
    executable = argv[0]
    if executable not in ALLOWED_EXECUTABLES:
        raise SandboxTestStatus(
            RESULT_STATUS_TEST_COMMAND_REJECTED,
            "UNKNOWN_RUNNER",
            f"test command {test_id} uses an unapproved executable",
            "sandbox_test_policy",
        )
    if tuple(argv[1:3]) != ("-m", "unittest"):
        raise SandboxTestStatus(
            RESULT_STATUS_TEST_COMMAND_REJECTED,
            "UNAPPROVED_MODULE",
            "only python -m unittest is approved",
            "sandbox_test_policy",
        )
    for index, arg in enumerate(argv):
        lowered = arg.lower()
        if arg in {"-c", "--command"}:
            raise SandboxTestStatus(
                RESULT_STATUS_TEST_COMMAND_REJECTED,
                "INLINE_CODE_REJECTED",
                "inline interpreter code is not approved",
                "sandbox_test_policy",
            )
        if index != 0 and lowered in FORBIDDEN_COMMAND_WORDS:
            raise SandboxTestStatus(
                RESULT_STATUS_TEST_COMMAND_REJECTED,
                "FORBIDDEN_EXECUTABLE",
                "test command contains a forbidden runner",
                "sandbox_test_policy",
            )
        if any(fragment in arg for fragment in FORBIDDEN_ARG_FRAGMENTS):
            raise SandboxTestStatus(
                RESULT_STATUS_TEST_COMMAND_REJECTED,
                "UNSAFE_ARGUMENT",
                "test command argument contains shell syntax",
                "sandbox_test_policy",
            )
        if arg.startswith("/") or re.match(r"^[A-Za-z]:", arg) is not None:
            raise SandboxTestStatus(
                RESULT_STATUS_TEST_COMMAND_REJECTED,
                "ABSOLUTE_PATH_REJECTED",
                "test command argument contains an absolute path",
                "sandbox_test_policy",
            )
        if ".." in arg.replace("\\", "/").split("/"):
            raise SandboxTestStatus(
                RESULT_STATUS_TEST_COMMAND_REJECTED,
                "PATH_TRAVERSAL_REJECTED",
                "test command argument contains path traversal",
                "sandbox_test_policy",
            )
    for target in argv[3:]:
        if target.startswith("-"):
            raise SandboxTestStatus(
                RESULT_STATUS_TEST_COMMAND_REJECTED,
                "UNAPPROVED_UNITTEST_OPTION",
                "unittest options after the module target are not approved",
                "sandbox_test_policy",
            )
        if not SAFE_MODULE_RE.fullmatch(target):
            raise SandboxTestStatus(
                RESULT_STATUS_TEST_COMMAND_REJECTED,
                "UNSAFE_TEST_TARGET",
                "unittest target must be a trusted Python module name",
                "sandbox_test_policy",
            )


def load_sandbox_test_policy(path: Path) -> SandboxTestPolicy:
    text = path.read_text(encoding="utf-8")
    raw = parse_test_policy(text)
    if raw.get("schema_version") != "1":
        raise fatal(
            fix.FailureCode.WORKFLOW_CONFIGURATION_ERROR,
            "sandbox test policy schema_version must be 1",
            "sandbox_test_policy",
        )
    label = str(raw.get("label", "")).strip()
    if label != TEST_LABEL:
        raise fatal(
            fix.FailureCode.WORKFLOW_CONFIGURATION_ERROR,
            "sandbox test policy must define the fixed test label",
            "sandbox_test_policy",
        )
    allowed_environment = raw.get("allowed_environment")
    if not isinstance(allowed_environment, list):
        raise fatal(
            fix.FailureCode.WORKFLOW_CONFIGURATION_ERROR,
            "sandbox test policy must define allowed_environment",
            "sandbox_test_policy",
        )
    commands_raw = raw.get("commands")
    if not isinstance(commands_raw, dict) or not commands_raw:
        raise fatal(
            fix.FailureCode.WORKFLOW_CONFIGURATION_ERROR,
            "sandbox test policy must define commands",
            "sandbox_test_policy",
        )
    timeout = int_policy(raw, "limits", "command_timeout_seconds")
    total_timeout = int_policy(raw, "limits", "total_timeout_seconds")
    stdout_limit = int_policy(raw, "limits", "stdout_max_bytes")
    stderr_limit = int_policy(raw, "limits", "stderr_max_bytes")
    commands: dict[str, TestCommandSpec] = {}
    for test_id, value in commands_raw.items():
        if not re.fullmatch(r"[a-z][a-z0-9_-]*", str(test_id)):
            raise fatal(
                fix.FailureCode.WORKFLOW_CONFIGURATION_ERROR,
                "sandbox test command IDs must be simple identifiers",
                "sandbox_test_policy",
            )
        argv = tuple(part for part in str(value).split("|") if part)
        validate_argv(str(test_id), argv)
        commands[str(test_id)] = TestCommandSpec(
            test_id=str(test_id),
            argv=argv,
            working_directory="trusted-support",
            timeout_seconds=timeout,
        )
    return SandboxTestPolicy(
        label=label,
        command_timeout_seconds=timeout,
        total_timeout_seconds=total_timeout,
        stdout_max_bytes=stdout_limit,
        stderr_max_bytes=stderr_limit,
        allowed_environment=tuple(str(item) for item in allowed_environment),
        commands=commands,
        network_isolation_enforced=bool(raw.get("network_isolation_enforced", False)),
        policy_hash=sha256_hex_bytes(text.encode("utf-8")),
    )


def validate_request_manifest_shape(manifest: dict[str, Any]) -> None:
    required = {
        "schema_version",
        "request_stage",
        "repository",
        "pull_request_number",
        "base_sha",
        "head_sha",
        "actor",
        "author_association",
        "draft",
        "base_repository",
        "head_repository",
        "labels",
        "event_action",
        "event_name",
        "event_label",
        "collector_workflow_name",
        "collector_workflow_run_id",
        "requested_at",
    }
    missing = sorted(required.difference(manifest))
    extra = sorted(set(manifest).difference(required))
    if missing or extra:
        raise fatal(
            fix.FailureCode.INVALID_MANIFEST,
            f"sandbox test request manifest field mismatch: missing={missing} extra={extra}",
            "sandbox_test_request_validation",
        )
    if manifest["schema_version"] != REQUEST_SCHEMA_VERSION:
        raise fatal(
            fix.FailureCode.INVALID_MANIFEST,
            "unsupported sandbox test request manifest schema",
            "sandbox_test_request_validation",
        )
    if manifest["request_stage"] != REQUEST_STAGE:
        raise fatal(
            fix.FailureCode.TRUST_BOUNDARY_VIOLATION,
            "sandbox test request came from an unexpected stage",
            "sandbox_test_request_validation",
        )
    if manifest["collector_workflow_name"] != COLLECTOR_WORKFLOW_NAME:
        raise fatal(
            fix.FailureCode.TRUST_BOUNDARY_VIOLATION,
            "sandbox test request came from an unexpected collector workflow",
            "sandbox_test_request_validation",
        )
    if manifest["repository"] != EXPECTED_REPOSITORY:
        raise fatal(
            fix.FailureCode.REPOSITORY_MISMATCH,
            "sandbox test request repository mismatch",
            "sandbox_test_request_validation",
        )
    if not isinstance(manifest["pull_request_number"], int):
        raise fatal(
            fix.FailureCode.PR_MISMATCH,
            "pull_request_number must be an integer",
            "sandbox_test_request_validation",
        )
    preflight.ensure_full_sha(manifest["base_sha"], "base_sha")
    preflight.ensure_full_sha(manifest["head_sha"], "head_sha")
    if not isinstance(manifest["labels"], list):
        raise fatal(
            fix.FailureCode.INVALID_MANIFEST,
            "labels must be an array",
            "sandbox_test_request_validation",
        )
    if manifest["event_action"] != "labeled" or manifest["event_label"] != TEST_LABEL:
        raise fatal(
            fix.FailureCode.LABEL_MISSING,
            "sandbox test requires the ai-fix-test-sandbox label event",
            "sandbox_test_request_validation",
        )
    if manifest["event_name"] != "pull_request":
        raise fatal(
            fix.FailureCode.INVALID_MANIFEST,
            "sandbox test request must come from pull_request",
            "sandbox_test_request_validation",
        )
    if not preflight.DATE_TIME_RE.fullmatch(str(manifest["requested_at"])):
        raise fatal(
            fix.FailureCode.INVALID_MANIFEST,
            "requested_at must be an ISO-8601 timestamp",
            "sandbox_test_request_validation",
        )


def labels_from_request(manifest: dict[str, Any]) -> set[str]:
    return preflight.labels_from_request(manifest)


def validate_live_test_gate(
    *,
    manifest: dict[str, Any],
    live_pull: dict[str, Any],
    live_issue: dict[str, Any],
    policy: fix.FixProposalPolicy,
    test_policy: SandboxTestPolicy,
    test_actor: str,
    test_actor_permission: str,
) -> set[str]:
    validate_request_manifest_shape(manifest)
    live_labels = approval.labels_from_pull_or_issue(live_issue)
    required_labels = {
        policy.proposal_policy.proposal_label,
        policy.proposal_policy.approval_label,
        preflight.VALIDATE_LABEL,
        apply.APPLY_LABEL,
        test_policy.label,
    }
    if test_actor != str(manifest["actor"]):
        raise fatal(
            fix.FailureCode.TRUST_BOUNDARY_VIOLATION,
            "sandbox test actor mismatch between workflow_run and request artifact",
            "sandbox_test_live_gate",
        )
    if bool(manifest.get("draft")) or bool(live_pull.get("draft")):
        raise fatal(
            fix.FailureCode.DRAFT_PULL_REQUEST,
            "draft pull requests cannot run sandbox tests",
            "sandbox_test_live_gate",
        )
    if str(live_pull.get("state", "")) != "open":
        raise SandboxTestStatus(
            RESULT_STATUS_BINDING_MISMATCH,
            "PR_NOT_OPEN",
            "pull request is no longer open",
            "sandbox_test_live_gate",
        )
    if manifest.get("base_repository") != EXPECTED_REPOSITORY:
        raise fatal(
            fix.FailureCode.REPOSITORY_MISMATCH,
            "base repository mismatch",
            "sandbox_test_live_gate",
        )
    if manifest.get("head_repository") != EXPECTED_REPOSITORY:
        raise fatal(
            fix.FailureCode.FORK_PULL_REQUEST,
            "fork pull requests cannot run sandbox tests",
            "sandbox_test_live_gate",
        )
    missing = sorted(required_labels.difference(live_labels))
    if missing:
        raise fatal(
            fix.FailureCode.LABEL_MISSING,
            f"live pull request is missing labels: {missing}",
            "sandbox_test_live_gate",
        )
    if test_policy.label not in labels_from_request(manifest):
        raise fatal(
            fix.FailureCode.LABEL_MISSING,
            "request artifact does not contain ai-fix-test-sandbox",
            "sandbox_test_live_gate",
        )
    live_head_sha = str(live_pull.get("head", {}).get("sha", ""))
    live_base_sha = str(live_pull.get("base", {}).get("sha", ""))
    if live_head_sha != manifest["head_sha"] or live_base_sha != manifest["base_sha"]:
        raise SandboxTestStatus(
            RESULT_STATUS_BINDING_MISMATCH,
            "REQUEST_HEAD_STALE",
            "live pull request SHA changed after sandbox test request collection",
            "sandbox_test_live_gate",
        )
    if int(live_pull.get("number", 0)) != int(manifest["pull_request_number"]):
        raise fatal(
            fix.FailureCode.PR_MISMATCH,
            "live pull request number mismatch",
            "sandbox_test_live_gate",
        )
    if str(live_pull.get("user", {}).get("type", "")).lower() == "bot":
        raise fatal(
            fix.FailureCode.BOT_PULL_REQUEST,
            "bot pull requests cannot run sandbox tests",
            "sandbox_test_live_gate",
        )
    if test_actor_permission not in ALLOWED_REPOSITORY_PERMISSIONS:
        raise fatal(
            fix.FailureCode.UNAUTHORIZED_ASSOCIATION,
            "sandbox test actor must have repository admin or maintain permission",
            "sandbox_test_live_gate",
        )
    return live_labels


def resolve_requested_test_commands(
    tests_recommended: Any,
    test_policy: SandboxTestPolicy,
) -> tuple[TestCommandSpec, ...]:
    if not isinstance(tests_recommended, list):
        raise SandboxTestStatus(
            RESULT_STATUS_TEST_COMMAND_REJECTED,
            "INVALID_TEST_PLAN",
            "tests_recommended must be a list",
            "sandbox_test_command_validation",
        )
    if not tests_recommended:
        raise SandboxTestStatus(
            RESULT_STATUS_TEST_COMMAND_REJECTED,
            "EMPTY_TEST_PLAN",
            "tests_recommended is empty",
            "sandbox_test_command_validation",
        )
    selected: list[TestCommandSpec] = []
    unknown: list[str] = []
    for raw_item in tests_recommended:
        if not isinstance(raw_item, str):
            raise SandboxTestStatus(
                RESULT_STATUS_TEST_COMMAND_REJECTED,
                "INVALID_TEST_PLAN",
                "test recommendation must be a string",
                "sandbox_test_command_validation",
            )
        item = raw_item.strip()
        if not item:
            raise SandboxTestStatus(
                RESULT_STATUS_TEST_COMMAND_REJECTED,
                "EMPTY_TEST_PLAN",
                "test recommendation is empty",
                "sandbox_test_command_validation",
            )
        test_id = item
        if test_id not in test_policy.commands:
            unknown.append(item)
            continue
        selected.append(test_policy.commands[test_id])
    if unknown:
        raise SandboxTestStatus(
            RESULT_STATUS_TEST_COMMAND_REJECTED,
            "UNKNOWN_TEST_COMMAND",
            f"test recommendations are not trusted policy command IDs: {unknown}",
            "sandbox_test_command_validation",
        )
    if not selected:
        raise SandboxTestStatus(
            RESULT_STATUS_TEST_COMMAND_REJECTED,
            "EMPTY_TEST_PLAN",
            "no approved test commands were selected",
            "sandbox_test_command_validation",
        )
    dedup: dict[str, TestCommandSpec] = {}
    for command in selected:
        dedup[command.test_id] = command
    return tuple(dedup.values())


def apply_result_targets_test_request(
    *,
    result: dict[str, Any],
    manifest: dict[str, Any],
    proposal_bundle: preflight.ArtifactBundle,
    approval_bundle: preflight.ApprovalBundle,
    preflight_bundle: apply.PreflightBundle,
) -> bool:
    return (
        result.get("repository") == manifest["repository"]
        and result.get("pull_request_number") == manifest["pull_request_number"]
        and result.get("head_sha") == manifest["head_sha"]
        and result.get("proposal_id") == proposal_bundle.metadata.get("proposal_id")
        and result.get("proposal_hash") == proposal_bundle.metadata.get("proposal_hash")
        and result.get("approval_id") == approval_bundle.record.get("approval_id")
        and result.get("approval_record_hash")
        == approval_bundle.record.get("approval_record_hash")
        and result.get("preflight_validation_id")
        == preflight_bundle.result.get("validation_id")
        and result.get("preflight_result_hash") == preflight_bundle.result_hash
    )


def validate_apply_result_for_test(
    *,
    result: dict[str, Any],
    manifest: dict[str, Any],
    proposal_bundle: preflight.ArtifactBundle,
    approval_bundle: preflight.ApprovalBundle,
    preflight_bundle: apply.PreflightBundle,
    policy_hash: str,
    schema_path: Path,
) -> None:
    apply.validate_apply_result_against_schema(result, schema_path)
    if not apply_result_targets_test_request(
        result=result,
        manifest=manifest,
        proposal_bundle=proposal_bundle,
        approval_bundle=approval_bundle,
        preflight_bundle=preflight_bundle,
    ):
        raise fatal(
            fix.FailureCode.TRUST_BOUNDARY_VIOLATION,
            "sandbox apply result identity does not match sandbox test request",
            "sandbox_apply_result_lookup",
        )
    expected = {
        "phase": apply.RESULT_PHASE_SANDBOX_APPLY,
        "status": apply.RESULT_STATUS_APPLY_PASSED,
        "policy_hash": policy_hash,
        "persistent_repository_modified": False,
        "commit_created": False,
        "push_performed": False,
        "merge_performed": False,
        "test_execution_performed": False,
        "sandbox_destroyed": True,
        "patch_applied": True,
    }
    for key, value in expected.items():
        if result.get(key) != value:
            raise fatal(
                fix.FailureCode.TRUST_BOUNDARY_VIOLATION,
                f"sandbox apply result requires {key}={value!r}",
                "sandbox_apply_result_lookup",
            )
    if result.get("git_apply_check", {}).get("status") != "PASS":
        raise fatal(
            fix.FailureCode.TRUST_BOUNDARY_VIOLATION,
            "sandbox apply result did not pass git apply --check",
            "sandbox_apply_result_lookup",
        )
    if result.get("git_apply", {}).get("status") != "PASS":
        raise fatal(
            fix.FailureCode.TRUST_BOUNDARY_VIOLATION,
            "sandbox apply result did not pass git apply",
            "sandbox_apply_result_lookup",
        )
    if result.get("diff_binding", {}).get("status") != "PASS":
        raise fatal(
            fix.FailureCode.TRUST_BOUNDARY_VIOLATION,
            "sandbox apply result did not pass diff binding",
            "sandbox_apply_result_lookup",
        )
    expected_patch_hash = apply.sha256_hex_bytes(
        apply.combined_patch_text(proposal_bundle.data).encode("utf-8")
    )
    if result.get("patch_file_hash") != expected_patch_hash:
        raise fatal(
            fix.FailureCode.TRUST_BOUNDARY_VIOLATION,
            "sandbox apply patch hash does not match proposal patch bytes",
            "sandbox_apply_result_lookup",
        )


def find_latest_apply_result_artifact(
    *,
    repo: str,
    token: str,
    manifest: dict[str, Any],
    proposal_bundle: preflight.ArtifactBundle,
    approval_bundle: preflight.ApprovalBundle,
    preflight_bundle: apply.PreflightBundle,
    policy_hash: str,
    output_dir: Path,
    max_bytes: int,
    schema_path: Path,
) -> ApplyBundle:
    runs_data, _ = stage1.github_json(
        "GET",
        f"/repos/{repo}/actions/workflows/fix-sandbox-apply.yml/runs?status=completed&per_page=50",
        token=token,
    )
    runs = runs_data.get("workflow_runs", []) if isinstance(runs_data, dict) else []
    for run in preflight.sorted_successful_workflow_runs(runs):
        run_id = int(run.get("id", 0) or 0)
        try:
            artifacts_data, _ = stage1.github_json(
                "GET",
                f"/repos/{repo}/actions/runs/{run_id}/artifacts?per_page=100",
                token=token,
            )
        except BaseException as error:
            if preflight.is_unavailable_artifact_candidate(error):
                continue
            raise
        artifacts = artifacts_data.get("artifacts", []) if isinstance(artifacts_data, dict) else []
        for artifact in artifacts:
            name = str(artifact.get("name", ""))
            if not name.startswith("sandbox-apply-result-"):
                continue
            try:
                artifact_id = fix.download_artifact_by_name(
                    repo=repo,
                    token=token,
                    run_id=str(run_id),
                    artifact_name=name,
                    target_dir=output_dir,
                    expected_files=set(APPLY_ARTIFACT_FILES),
                    max_bytes=max_bytes,
                )
            except BaseException as error:
                if preflight.is_unavailable_artifact_candidate(error):
                    continue
                raise
            result = read_json_file(output_dir / "sandbox-validation-result.json")
            if not isinstance(result, dict):
                raise fatal(
                    fix.FailureCode.INVALID_PROPOSAL,
                    "sandbox apply result artifact must contain a JSON object",
                    "sandbox_apply_result_lookup",
                )
            validate_apply_result_for_test(
                result=result,
                manifest=manifest,
                proposal_bundle=proposal_bundle,
                approval_bundle=approval_bundle,
                preflight_bundle=preflight_bundle,
                policy_hash=policy_hash,
                schema_path=schema_path,
            )
            return ApplyBundle(
                result=result,
                result_hash=sha256_hex_json(result),
                artifact_id=artifact_id,
                artifact_name=name,
                workflow_run_id=run_id,
                workflow_name=apply.APPLY_WORKFLOW_NAME,
            )
    raise fatal(
        fix.FailureCode.PROPOSAL_ARTIFACT_NOT_FOUND,
        "NOT_FOUND: no verified sandbox apply result artifact was found",
        "sandbox_apply_result_lookup",
    )


def sandbox_test_id_for(
    *,
    repository: str,
    pull_request_number: int,
    head_sha: str,
    proposal_id: str,
    proposal_hash: str,
    approval_id: str,
    approval_record_hash: str,
    preflight_validation_id: str,
    preflight_result_hash: str,
    sandbox_apply_id: str,
    sandbox_apply_result_hash: str,
    test_request_actor: str,
    policy_hash: str,
    sandbox_test_policy_hash: str,
    test_plan_hash: str,
    patch_hash: str,
) -> str:
    return sha256_hex_json(
        {
            "repository": repository,
            "pull_request_number": pull_request_number,
            "head_sha": head_sha,
            "proposal_id": proposal_id,
            "proposal_hash": proposal_hash,
            "approval_id": approval_id,
            "approval_record_hash": approval_record_hash,
            "preflight_validation_id": preflight_validation_id,
            "preflight_result_hash": preflight_result_hash,
            "sandbox_apply_id": sandbox_apply_id,
            "sandbox_apply_result_hash": sandbox_apply_result_hash,
            "test_request_actor": test_request_actor,
            "policy_hash": policy_hash,
            "sandbox_test_policy_hash": sandbox_test_policy_hash,
            "phase": RESULT_PHASE_SANDBOX_TEST,
            "test_plan_hash": test_plan_hash,
            "patch_hash": patch_hash,
        }
    )[:32]


def command_record(command: TestCommandSpec, status: str = "REJECTED") -> dict[str, Any]:
    return {
        "test_id": command.test_id,
        "argv": list(command.argv),
        "working_directory": command.working_directory,
        "timeout_seconds": command.timeout_seconds,
        "status": status,
        "exit_code": None,
        "duration_seconds": 0.0,
        "stdout_bytes": 0,
        "stderr_bytes": 0,
        "stdout_hash": sha256_hex_bytes(b""),
        "stderr_hash": sha256_hex_bytes(b""),
        "stdout_truncated": False,
        "stderr_truncated": False,
    }


def build_test_context(
    *,
    manifest: dict[str, Any],
    proposal_bundle: preflight.ArtifactBundle,
    approval_bundle: preflight.ApprovalBundle,
    preflight_bundle: apply.PreflightBundle,
    apply_bundle: ApplyBundle,
    test_policy: SandboxTestPolicy,
    test_commands: tuple[TestCommandSpec, ...],
    test_actor: str,
    test_actor_permission: str,
    test_actor_role: str | None,
    validation_actor_permission: str,
    validation_actor_role: str | None,
    approval_actor_permission: str,
    approval_actor_role: str | None,
    apply_actor_permission: str,
    apply_actor_role: str | None,
    live_labels: Iterable[str],
) -> dict[str, Any]:
    proposal = proposal_bundle.data
    metadata = proposal_bundle.metadata
    record = approval_bundle.record
    precheck = preflight_bundle.result
    apply_result = apply_bundle.result
    patch_text = apply.combined_patch_text(proposal)
    patch_hash = apply.sha256_hex_bytes(patch_text.encode("utf-8"))
    test_plan = [
        {
            "test_id": command.test_id,
            "argv": list(command.argv),
            "working_directory": command.working_directory,
            "timeout_seconds": command.timeout_seconds,
        }
        for command in test_commands
    ]
    test_plan_hash = sha256_hex_json(
        {
            "phase": RESULT_PHASE_SANDBOX_TEST,
            "commands": test_plan,
        }
    )
    sandbox_test_id = sandbox_test_id_for(
        repository=manifest["repository"],
        pull_request_number=int(manifest["pull_request_number"]),
        head_sha=manifest["head_sha"],
        proposal_id=str(metadata["proposal_id"]),
        proposal_hash=str(metadata["proposal_hash"]),
        approval_id=str(record["approval_id"]),
        approval_record_hash=str(record["approval_record_hash"]),
        preflight_validation_id=str(precheck["validation_id"]),
        preflight_result_hash=preflight_bundle.result_hash,
        sandbox_apply_id=str(apply_result["validation_id"]),
        sandbox_apply_result_hash=apply_bundle.result_hash,
        test_request_actor=test_actor,
        policy_hash=str(metadata["policy_hash"]),
        sandbox_test_policy_hash=test_policy.policy_hash,
        test_plan_hash=test_plan_hash,
        patch_hash=patch_hash,
    )
    return {
        "schema_version": "sandbox-test-context-v1",
        "sandbox_test_id": sandbox_test_id,
        "manifest": manifest,
        "proposal": proposal,
        "proposal_metadata": metadata,
        "approval_record": record,
        "preflight_result": precheck,
        "preflight_result_hash": preflight_bundle.result_hash,
        "sandbox_apply_result": apply_result,
        "sandbox_apply_result_hash": apply_bundle.result_hash,
        "test_request_actor": test_actor,
        "test_request_actor_repository_permission": test_actor_permission,
        "test_request_actor_repository_role": test_actor_role,
        "validation_request_actor": str(precheck["validation_request_actor"]),
        "validation_request_actor_repository_permission": validation_actor_permission,
        "validation_request_actor_repository_role": validation_actor_role,
        "approved_by_repository_permission": approval_actor_permission,
        "approved_by_repository_role": approval_actor_role,
        "apply_request_actor": str(apply_result["apply_request_actor"]),
        "apply_request_actor_repository_permission": apply_actor_permission,
        "apply_request_actor_repository_role": apply_actor_role,
        "proposal_artifact": preflight.artifact_provenance(
            artifact_id=proposal_bundle.artifact_id,
            artifact_name=proposal_bundle.artifact_name,
            workflow_run_id=proposal_bundle.workflow_run_id,
            workflow_name=proposal_bundle.workflow_name,
            repository=manifest["repository"],
            pull_request_number=int(manifest["pull_request_number"]),
            head_sha=str(proposal["head_sha"]),
        ),
        "approval_artifact": preflight.artifact_provenance(
            artifact_id=approval_bundle.artifact_id,
            artifact_name=approval_bundle.artifact_name,
            workflow_run_id=approval_bundle.workflow_run_id,
            workflow_name=approval_bundle.workflow_name,
            repository=manifest["repository"],
            pull_request_number=int(manifest["pull_request_number"]),
            head_sha=str(record["head_sha"]),
        ),
        "preflight_artifact": preflight.artifact_provenance(
            artifact_id=preflight_bundle.artifact_id,
            artifact_name=preflight_bundle.artifact_name,
            workflow_run_id=preflight_bundle.workflow_run_id,
            workflow_name=preflight_bundle.workflow_name,
            repository=manifest["repository"],
            pull_request_number=int(manifest["pull_request_number"]),
            head_sha=str(precheck["head_sha"]),
        ),
        "sandbox_apply_artifact": preflight.artifact_provenance(
            artifact_id=apply_bundle.artifact_id,
            artifact_name=apply_bundle.artifact_name,
            workflow_run_id=apply_bundle.workflow_run_id,
            workflow_name=apply_bundle.workflow_name,
            repository=manifest["repository"],
            pull_request_number=int(manifest["pull_request_number"]),
            head_sha=str(apply_result["head_sha"]),
        ),
        "sandbox_test_policy_hash": test_policy.policy_hash,
        "sandbox_test_policy": {
            "network_isolation_enforced": test_policy.network_isolation_enforced,
            "stdout_max_bytes": test_policy.stdout_max_bytes,
            "stderr_max_bytes": test_policy.stderr_max_bytes,
            "total_timeout_seconds": test_policy.total_timeout_seconds,
            "allowed_environment": list(test_policy.allowed_environment),
        },
        "live_labels": sorted(set(str(label) for label in live_labels)),
        "expected_files": apply.expected_change_paths(proposal),
        "patch_text": patch_text,
        "patch_hash": patch_hash,
        "resulting_diff_hash": sha256_hex_json(apply_result["diff_binding"]),
        "test_commands": test_plan,
        "test_plan_hash": test_plan_hash,
        "started_at": now_utc(),
    }


def test_environment(
    *,
    allowed_environment: Iterable[str],
    support_dir: Path,
    worktree: Path | None = None,
) -> dict[str, str]:
    env: dict[str, str] = {}
    allowed = set(allowed_environment)
    for key in ("PATH", "HOME", "LANG", "LC_ALL"):
        if key in allowed and key in os.environ:
            env[key] = os.environ[key]
    if "PYTHONPATH" in allowed:
        python_path = [str(support_dir)]
        if worktree is not None:
            python_path.append(str(worktree))
        env["PYTHONPATH"] = os.pathsep.join(python_path)
    if "PYTHONDONTWRITEBYTECODE" in allowed:
        env["PYTHONDONTWRITEBYTECODE"] = "1"
    for forbidden in FORBIDDEN_ENV_KEYS:
        env.pop(forbidden, None)
    return env


def credentials_available(env: dict[str, str]) -> bool:
    return any(key in env for key in FORBIDDEN_ENV_KEYS)


def redacted_output(data: bytes, limit: int) -> tuple[bytes, bool]:
    if len(data) <= limit:
        return data, False
    return data[:limit], True


def run_one_test(
    *,
    command: TestCommandSpec,
    worktree: Path,
    support_dir: Path,
    env: dict[str, str],
    stdout_limit: int,
    stderr_limit: int,
) -> tuple[dict[str, Any], bytes, bytes]:
    if command.working_directory == ".":
        cwd = worktree
    elif command.working_directory == "trusted-support":
        cwd = support_dir
    else:
        raise SandboxTestStatus(
            RESULT_STATUS_TEST_COMMAND_REJECTED,
            "UNAPPROVED_WORKING_DIRECTORY",
            "approved test command uses an unapproved working directory",
            "sandbox_test_policy",
        )
    start = time.monotonic()
    try:
        completed = subprocess.run(
            list(command.argv),
            cwd=cwd,
            env=env,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=command.timeout_seconds,
        )
        timed_out = False
        exit_code: int | None = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        exit_code = None
        stdout = exc.stdout if isinstance(exc.stdout, bytes) else b""
        stderr = exc.stderr if isinstance(exc.stderr, bytes) else b""
    duration = time.monotonic() - start
    stdout_truncated, stdout_was_truncated = redacted_output(stdout, stdout_limit)
    stderr_truncated, stderr_was_truncated = redacted_output(stderr, stderr_limit)
    if timed_out:
        status = "TIMEOUT"
    elif stdout_was_truncated or stderr_was_truncated:
        status = "OUTPUT_LIMIT"
    elif exit_code == 0:
        status = "PASS"
    else:
        status = "FAIL"
    record = {
        "test_id": command.test_id,
        "argv": list(command.argv),
        "working_directory": command.working_directory,
        "timeout_seconds": command.timeout_seconds,
        "status": status,
        "exit_code": exit_code,
        "duration_seconds": round(duration, 3),
        "stdout_bytes": len(stdout),
        "stderr_bytes": len(stderr),
        "stdout_hash": sha256_hex_bytes(stdout),
        "stderr_hash": sha256_hex_bytes(stderr),
        "stdout_truncated": stdout_was_truncated,
        "stderr_truncated": stderr_was_truncated,
    }
    return record, stdout_truncated, stderr_truncated


def effective_command_timeout(
    *,
    start_time: float,
    total_timeout_seconds: int,
    command_timeout_seconds: int,
) -> int:
    remaining = total_timeout_seconds - (time.monotonic() - start_time)
    if remaining <= 0:
        raise SandboxTestStatus(
            RESULT_STATUS_TESTS_TIMEOUT,
            "TOTAL_TEST_TIMEOUT",
            "approved sandbox test plan exceeded the total timeout",
            "sandbox_test_execution",
        )
    return max(1, min(command_timeout_seconds, int(remaining)))


def post_test_changes(
    *,
    worktree: Path,
    expected_files: Iterable[str],
    expected_hashes: Iterable[dict[str, str]],
) -> tuple[list[str], list[str]]:
    expected = set(str(path) for path in expected_files)
    expected_hash_by_path = {
        str(entry["path"]): str(entry["resulting_blob_sha"])
        for entry in expected_hashes
    }
    status_entries = apply.parse_status_z(
        apply.run_git(worktree, ("git", "status", "--porcelain=v1", "-z")).stdout
    )
    tracked: list[str] = []
    untracked: list[str] = []
    for entry in status_entries:
        status = entry["status"]
        path = entry["path"]
        if status == "??":
            untracked.append(path)
        elif path not in expected or status != " M":
            tracked.append(path)
    current_hashes = apply.resulting_file_hashes(worktree, sorted(expected))
    for entry in current_hashes:
        path = entry["path"]
        if entry["resulting_blob_sha"] != expected_hash_by_path.get(path):
            tracked.append(path)
    return sorted(set(tracked)), sorted(set(untracked))


def base_test_result(
    *,
    context: dict[str, Any],
    status: str,
    failure_class: str | None,
    failure_code: str | None,
    failed_operation: str | None = None,
    last_error: str | None = None,
    completed_at: str | None = None,
) -> dict[str, Any]:
    manifest = context["manifest"]
    metadata = context["proposal_metadata"]
    record = context["approval_record"]
    precheck = context["preflight_result"]
    apply_result = context["sandbox_apply_result"]
    completed = completed_at or now_utc()
    return {
        "schema_version": RESULT_SCHEMA_VERSION,
        "phase": RESULT_PHASE_SANDBOX_TEST,
        "status": status,
        "sandbox_test_id": context["sandbox_test_id"],
        "repository": manifest["repository"],
        "pull_request_number": int(manifest["pull_request_number"]),
        "base_sha": manifest["base_sha"],
        "head_sha": manifest["head_sha"],
        "proposal_id": str(metadata["proposal_id"]),
        "proposal_hash": str(metadata["proposal_hash"]),
        "approval_id": str(record["approval_id"]),
        "approval_record_hash": str(record["approval_record_hash"]),
        "preflight_validation_id": str(precheck["validation_id"]),
        "preflight_artifact_id": int(context["preflight_artifact"]["artifact_id"]),
        "preflight_result_hash": context["preflight_result_hash"],
        "sandbox_apply_id": str(apply_result["validation_id"]),
        "sandbox_apply_artifact_id": int(context["sandbox_apply_artifact"]["artifact_id"]),
        "sandbox_apply_result_hash": context["sandbox_apply_result_hash"],
        "policy_hash": str(metadata["policy_hash"]),
        "sandbox_test_policy_hash": context["sandbox_test_policy_hash"],
        "patch_hash": context["patch_hash"],
        "resulting_diff_hash": context["resulting_diff_hash"],
        "test_request_actor": context["test_request_actor"],
        "test_request_actor_repository_permission": context[
            "test_request_actor_repository_permission"
        ],
        "approved_by": str(record["approved_by"]),
        "approved_by_repository_permission": context[
            "approved_by_repository_permission"
        ],
        "validation_request_actor": context["validation_request_actor"],
        "validation_request_actor_repository_permission": context[
            "validation_request_actor_repository_permission"
        ],
        "apply_request_actor": context["apply_request_actor"],
        "apply_request_actor_repository_permission": context[
            "apply_request_actor_repository_permission"
        ],
        "tests_source": "proposal.tests_recommended",
        "tests_requested": [
            command_record(
                TestCommandSpec(
                    test_id=item["test_id"],
                    argv=tuple(item["argv"]),
                    working_directory=item["working_directory"],
                    timeout_seconds=int(item["timeout_seconds"]),
                )
            )
            for item in context["test_commands"]
        ],
        "tests_executed": [],
        "commands": [list(item["argv"]) for item in context["test_commands"]],
        "working_directories": [str(item["working_directory"]) for item in context["test_commands"]],
        "started_at": context.get("started_at", completed),
        "completed_at": completed,
        "duration_seconds": 0.0,
        "exit_codes": [],
        "timeouts": [],
        "stdout_hashes": [],
        "stderr_hashes": [],
        "stdout_truncated": [],
        "stderr_truncated": [],
        "stdout_byte_counts": [],
        "stderr_byte_counts": [],
        "network_isolation_enforced": bool(
            context["sandbox_test_policy"]["network_isolation_enforced"]
        ),
        "credentials_available": False,
        "patch_apply_result": check_result("SKIPPED", "patch not applied in this run"),
        "test_generated_tracked_changes": [],
        "test_generated_untracked_files": [],
        "persistent_repository_modified": False,
        "commit_performed": False,
        "push_performed": False,
        "merge_performed": False,
        "cleanup_performed": False,
        "sandbox_destroyed": False,
        "failure_class": failure_class,
        "failure_code": failure_code,
        "failed_operation": failed_operation,
        "last_error": last_error,
    }


def validate_test_result_against_schema(result: dict[str, Any], schema_path: Path) -> None:
    schema = read_json_file(schema_path)
    if not isinstance(schema, dict):
        raise fatal(
            fix.FailureCode.WORKFLOW_CONFIGURATION_ERROR,
            "sandbox test result schema must be a JSON object",
            "sandbox_test_result_schema",
        )
    apply.validate_json_schema_subset(result, schema)
    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        raise fatal(
            fix.FailureCode.WORKFLOW_CONFIGURATION_ERROR,
            "sandbox test result schema must declare properties",
            "sandbox_test_result_schema",
        )
    extra = sorted(set(result).difference(properties))
    if extra:
        raise fatal(
            fix.FailureCode.INVALID_PROPOSAL,
            f"sandbox test result contains unknown fields: {extra}",
            "sandbox_test_result_schema",
        )
    if result["persistent_repository_modified"] is not False:
        raise fatal(
            fix.FailureCode.INVALID_PROPOSAL,
            "sandbox tests must not persist repository changes",
            "sandbox_test_result_schema",
        )
    for key in ("commit_performed", "push_performed", "merge_performed"):
        if result[key] is not False:
            raise fatal(
                fix.FailureCode.INVALID_PROPOSAL,
                f"sandbox tests must keep {key}=false",
                "sandbox_test_result_schema",
            )


def write_test_artifact(
    *,
    output_dir: Path,
    result: dict[str, Any],
    stdout_logs: list[bytes],
    stderr_logs: list[bytes],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json_file(output_dir / "sandbox-test-result.json", result)
    write_json_file(output_dir / "test-commands.json", result["tests_requested"])
    write_json_file(
        output_dir / "test-output-manifest.json",
        {
            "stdout_hashes": result["stdout_hashes"],
            "stderr_hashes": result["stderr_hashes"],
            "stdout_truncated": result["stdout_truncated"],
            "stderr_truncated": result["stderr_truncated"],
            "stdout_byte_counts": result["stdout_byte_counts"],
            "stderr_byte_counts": result["stderr_byte_counts"],
        },
    )
    for index, data in enumerate(stdout_logs):
        (output_dir / f"stdout-{index}.log").write_bytes(data)
    for index, data in enumerate(stderr_logs):
        (output_dir / f"stderr-{index}.log").write_bytes(data)


def sandbox_test_comment_body(
    *,
    result: dict[str, Any],
    workflow_run_id: str,
    repo: str,
    artifact_id: str | None = None,
) -> str:
    run_url = f"https://github.com/{repo}/actions/runs/{workflow_run_id}"
    artifact_line = f"- Artifact ID: `{artifact_id}`" if artifact_id else "- Artifact ID: `pending`"
    passed = sum(1 for item in result["tests_executed"] if item["status"] == "PASS")
    failed = sum(1 for item in result["tests_executed"] if item["status"] != "PASS")
    return "\n".join(
        [
            SANDBOX_TEST_MARKER,
            "",
            "## AI Sandbox Test Validation",
            "",
            "> Stage 2C-B2 applied the approved proposal only inside an ephemeral sandbox and ran only trusted approved test commands. No commit, push, or merge was performed.",
            "",
            f"- Phase: `{result['phase']}`",
            f"- Status: `{result['status']}`",
            f"- Sandbox Test ID: `{result['sandbox_test_id']}`",
            f"- Proposal ID: `{result['proposal_id']}`",
            f"- Approval ID: `{result['approval_id']}`",
            f"- Preflight Validation ID: `{result['preflight_validation_id']}`",
            f"- Sandbox Apply ID: `{result['sandbox_apply_id']}`",
            f"- HEAD SHA: `{result['head_sha']}`",
            f"- Test Commands Count: `{len(result['commands'])}`",
            f"- Tests Passed / Failed: `{passed}` / `{failed}`",
            f"- Timeout: `{any(result['timeouts'])}`",
            f"- Network Isolation Enforced: `{result['network_isolation_enforced']}`",
            f"- Credentials Available: `{result['credentials_available']}`",
            f"- Workflow run: {run_url}",
            artifact_line,
            "",
            "### Safety",
            "",
            "- Persistent Repository Modified: `No`",
            "- Commit: `No`",
            "- Push: `No`",
            "- Merge: `No`",
            f"- Cleanup: `{'Yes' if result['cleanup_performed'] else 'No'}`",
            f"- Sandbox Destroyed: `{'Yes' if result['sandbox_destroyed'] else 'No'}`",
        ]
    )


def post_or_update_test_comment(
    *,
    repo: str,
    issue_number: str,
    token: str,
    body: str,
) -> tuple[str, str]:
    comments = list(stage1.iter_issue_comments(repo, issue_number, token))
    marker_comments = [
        comment
        for comment in comments
        if SANDBOX_TEST_MARKER in str(comment.get("body", ""))
    ]
    if marker_comments:
        comment_id = str(marker_comments[0]["id"])
        stage1.github_json(
            "PATCH",
            f"/repos/{repo}/issues/comments/{comment_id}",
            token=token,
            body={"body": body},
        )
        return comment_id, "update"
    comment, _ = stage1.github_json(
        "POST",
        f"/repos/{repo}/issues/{issue_number}/comments",
        token=token,
        body={"body": body},
    )
    if not isinstance(comment, dict) or "id" not in comment:
        raise fatal(
            fix.FailureCode.PERMISSION_ERROR,
            "GitHub issue comment create response was malformed",
            "github_sandbox_test_comment_create",
        )
    return str(comment["id"]), "create"


def command_download_request_artifact(_: argparse.Namespace) -> int:
    try:
        artifact_id = fix.run_with_retry(
            "github_sandbox_test_request_artifact",
            lambda: fix.download_artifact_by_name(
                repo=required_env("GITHUB_REPOSITORY"),
                token=required_env("GITHUB_TOKEN"),
                run_id=required_env("COLLECTOR_RUN_ID"),
                artifact_name=required_env("ARTIFACT_NAME"),
                target_dir=Path(required_env("TEST_REQUEST_DIR")),
                expected_files={"manifest.json"},
                max_bytes=int(required_env("MAX_ARTIFACT_BYTES")),
            ),
        )
        github_output({"request_artifact_id": str(artifact_id)})
        return 0
    except fix.FixProposalFailure as error:
        return fix.fail_command(error)


def command_validate_request(_: argparse.Namespace) -> int:
    try:
        manifest = read_json_file(Path(required_env("TEST_REQUEST_DIR")) / "manifest.json")
        if not isinstance(manifest, dict):
            raise fatal(
                fix.FailureCode.INVALID_MANIFEST,
                "sandbox test request manifest must be a JSON object",
                "sandbox_test_request_validation",
            )
        validate_request_manifest_shape(manifest)
        github_output(
            {
                "pr_number": str(manifest["pull_request_number"]),
                "head_sha": str(manifest["head_sha"]),
            }
        )
        return 0
    except fix.FixProposalFailure as error:
        return fix.fail_command(error)


def command_prepare(_: argparse.Namespace) -> int:
    try:
        repo = required_env("GITHUB_REPOSITORY")
        token = required_env("GITHUB_TOKEN")
        request_dir = Path(required_env("TEST_REQUEST_DIR"))
        context_dir = Path(required_env("TEST_CONTEXT_DIR"))
        proposal_dir = Path(required_env("PROPOSAL_ARTIFACT_DIR"))
        approval_dir = Path(required_env("APPROVAL_ARTIFACT_DIR"))
        preflight_dir = Path(required_env("PREFLIGHT_ARTIFACT_DIR"))
        apply_dir = Path(required_env("APPLY_ARTIFACT_DIR"))
        policy_path = Path(required_env("FIX_POLICY"))
        test_policy_path = Path(required_env("SANDBOX_TEST_POLICY"))
        apply_schema = Path(required_env("SANDBOX_RESULT_SCHEMA"))
        manifest = read_json_file(request_dir / "manifest.json")
        if not isinstance(manifest, dict):
            raise fatal(
                fix.FailureCode.INVALID_MANIFEST,
                "sandbox test request manifest must be a JSON object",
                "sandbox_test_prepare",
            )
        validate_request_manifest_shape(manifest)
        policy = fix.load_fix_proposal_policy(policy_path)
        test_policy = load_sandbox_test_policy(test_policy_path)
        test_actor = required_env("TEST_ACTOR")
        live_pull = approval.fetch_live_pull(
            repo=repo,
            pr_number=int(manifest["pull_request_number"]),
            token=token,
        )
        live_issue = approval.fetch_live_issue(
            repo=repo,
            pr_number=int(manifest["pull_request_number"]),
            token=token,
        )
        test_permission = approval.approval_actor_repository_permission(
            repo=repo,
            actor=test_actor,
            token=token,
        )
        live_labels = validate_live_test_gate(
            manifest=manifest,
            live_pull=live_pull,
            live_issue=live_issue,
            policy=policy,
            test_policy=test_policy,
            test_actor=test_actor,
            test_actor_permission=str(test_permission["permission"]),
        )
        proposal_bundle = preflight.find_latest_proposal_artifact(
            repo=repo,
            token=token,
            manifest=manifest,
            policy=policy,
            output_dir=proposal_dir,
            max_bytes=int(required_env("MAX_ARTIFACT_BYTES")),
        )
        test_commands = resolve_requested_test_commands(
            proposal_bundle.data.get("tests_recommended", []),
            test_policy,
        )
        approval_bundle = preflight.find_latest_approval_artifact(
            repo=repo,
            token=token,
            manifest=manifest,
            proposal=proposal_bundle.data,
            metadata=proposal_bundle.metadata,
            policy_hash=policy.policy_hash,
            output_dir=approval_dir,
            max_bytes=int(required_env("MAX_ARTIFACT_BYTES")),
        )
        approved_by = str(approval_bundle.record["approved_by"])
        approval_permission = approval.approval_actor_repository_permission(
            repo=repo,
            actor=approved_by,
            token=token,
        )
        if approval_permission["permission"] not in ALLOWED_REPOSITORY_PERMISSIONS:
            raise fatal(
                fix.FailureCode.UNAUTHORIZED_ASSOCIATION,
                "approval actor no longer has repository admin or maintain permission",
                "sandbox_test_approval_actor_permission",
            )
        preflight_bundle = apply.find_latest_preflight_artifact(
            repo=repo,
            token=token,
            manifest=manifest,
            proposal_bundle=proposal_bundle,
            approval_bundle=approval_bundle,
            policy_hash=policy.policy_hash,
            output_dir=preflight_dir,
            max_bytes=int(required_env("MAX_ARTIFACT_BYTES")),
        )
        validation_actor = str(preflight_bundle.result["validation_request_actor"])
        validation_permission = approval.approval_actor_repository_permission(
            repo=repo,
            actor=validation_actor,
            token=token,
        )
        if validation_permission["permission"] not in ALLOWED_REPOSITORY_PERMISSIONS:
            raise fatal(
                fix.FailureCode.UNAUTHORIZED_ASSOCIATION,
                "preflight validation actor no longer has repository admin or maintain permission",
                "sandbox_test_validation_actor_permission",
            )
        apply_bundle = find_latest_apply_result_artifact(
            repo=repo,
            token=token,
            manifest=manifest,
            proposal_bundle=proposal_bundle,
            approval_bundle=approval_bundle,
            preflight_bundle=preflight_bundle,
            policy_hash=policy.policy_hash,
            output_dir=apply_dir,
            max_bytes=int(required_env("MAX_ARTIFACT_BYTES")),
            schema_path=apply_schema,
        )
        apply_actor = str(apply_bundle.result["apply_request_actor"])
        apply_permission = approval.approval_actor_repository_permission(
            repo=repo,
            actor=apply_actor,
            token=token,
        )
        if apply_permission["permission"] not in ALLOWED_REPOSITORY_PERMISSIONS:
            raise fatal(
                fix.FailureCode.UNAUTHORIZED_ASSOCIATION,
                "sandbox apply actor no longer has repository admin or maintain permission",
                "sandbox_test_apply_actor_permission",
            )
        context = build_test_context(
            manifest=manifest,
            proposal_bundle=proposal_bundle,
            approval_bundle=approval_bundle,
            preflight_bundle=preflight_bundle,
            apply_bundle=apply_bundle,
            test_policy=test_policy,
            test_commands=test_commands,
            test_actor=test_actor,
            test_actor_permission=str(test_permission["permission"]),
            test_actor_role=test_permission.get("role_name"),
            validation_actor_permission=str(validation_permission["permission"]),
            validation_actor_role=validation_permission.get("role_name"),
            approval_actor_permission=str(approval_permission["permission"]),
            approval_actor_role=approval_permission.get("role_name"),
            apply_actor_permission=str(apply_permission["permission"]),
            apply_actor_role=apply_permission.get("role_name"),
            live_labels=live_labels,
        )
        apply.validate_final_head(
            repo=repo,
            pr_number=int(manifest["pull_request_number"]),
            expected_head_sha=str(manifest["head_sha"]),
            token=token,
            code="PRE_TEST_CHECKOUT_HEAD_STALE",
        )
        context_dir.mkdir(parents=True, exist_ok=True)
        write_json_file(context_dir / TEST_CONTEXT_FILE, context)
        artifact_name = f"sandbox-test-result-{context['sandbox_test_id']}"
        github_output(
            {
                "test_ready": "true",
                "should_comment": "true",
                "artifact_name": artifact_name,
                "pr_number": str(manifest["pull_request_number"]),
                "head_sha": str(manifest["head_sha"]),
                "sandbox_test_id": str(context["sandbox_test_id"]),
            }
        )
        write_job_summary(
            "\n".join(
                [
                    "## Sandbox Test Prepare",
                    "",
                    "- status: `READY`",
                    f"- sandbox test ID: `{context['sandbox_test_id']}`",
                    f"- test commands: `{len(test_commands)}`",
                    "- checkout: not yet performed",
                ]
            )
        )
        return 0
    except SandboxTestStatus as status_error:
        return fix.fail_command(
            fatal(
                fix.FailureCode.INVALID_PROPOSAL,
                status_error.message,
                status_error.operation,
            )
        )
    except apply.ApplyStatus as status_error:
        return fix.fail_command(
            fatal(
                fix.FailureCode.STALE_ARTIFACT,
                status_error.message,
                "sandbox_test_prepare",
            )
        )
    except fix.FixProposalFailure as error:
        return fix.fail_command(error)


def command_run_tests(_: argparse.Namespace) -> int:
    context_path = Path(required_env("TEST_CONTEXT_DIR")) / TEST_CONTEXT_FILE
    output_dir = Path(required_env("TEST_RESULT_DIR"))
    worktree = Path(required_env("SANDBOX_WORKTREE"))
    patch_path = Path(required_env("PATCH_FILE"))
    schema_path = Path(required_env("SANDBOX_TEST_RESULT_SCHEMA"))
    support_dir = Path(required_env("TEST_SUPPORT_DIR"))
    context = read_json_file(context_path)
    if not isinstance(context, dict):
        raise SystemExit(1)
    result = base_test_result(
        context=context,
        status=RESULT_STATUS_INTERNAL_ERROR,
        failure_class=RESULT_STATUS_INTERNAL_ERROR,
        failure_code="INCOMPLETE",
    )
    stdout_logs: list[bytes] = []
    stderr_logs: list[bytes] = []
    executed: list[dict[str, Any]] = []
    cleanup = check_result("SKIPPED", "cleanup not started")
    start = time.monotonic()
    try:
        checkout_verification = apply.verify_checkout(
            worktree,
            str(context["manifest"]["head_sha"]),
        )
        patch_hash = apply.materialize_patch(context, patch_path)
        if patch_hash != context["patch_hash"]:
            raise SandboxTestStatus(
                RESULT_STATUS_BINDING_MISMATCH,
                "PATCH_HASH_MISMATCH",
                "materialized patch hash does not match trusted context",
                "sandbox_test_patch_materialization",
            )
        apply.run_git(worktree, (*apply.GIT_APPLY_CHECK_ARGV, str(patch_path)))
        apply.run_git(worktree, (*apply.GIT_APPLY_ARGV, str(patch_path)))
        changed_files, diff_binding, resulting_hashes = apply.verify_changed_files(
            worktree=worktree,
            context=context,
        )
        expected_hashes = context["sandbox_apply_result"]["resulting_file_hashes"]
        if resulting_hashes != expected_hashes:
            raise SandboxTestStatus(
                RESULT_STATUS_BINDING_MISMATCH,
                "RESULTING_FILE_HASH_MISMATCH",
                "sandbox test apply result does not match Stage 2C-B1 resulting hashes",
                "sandbox_test_diff_binding",
            )
        if sha256_hex_json(diff_binding) != context["resulting_diff_hash"]:
            raise SandboxTestStatus(
                RESULT_STATUS_BINDING_MISMATCH,
                "RESULTING_DIFF_HASH_MISMATCH",
                "sandbox test diff binding does not match Stage 2C-B1",
                "sandbox_test_diff_binding",
            )
        test_policy_data = context["sandbox_test_policy"]
        test_env = test_environment(
            allowed_environment=test_policy_data["allowed_environment"],
            support_dir=support_dir,
            worktree=worktree,
        )
        if credentials_available(test_env):
            raise SandboxTestStatus(
                RESULT_STATUS_TEST_ENVIRONMENT_REJECTED,
                "SECRET_ENVIRONMENT",
                "test environment contains forbidden credentials",
                "sandbox_test_environment",
            )
        for item in context["test_commands"]:
            command = TestCommandSpec(
                test_id=str(item["test_id"]),
                argv=tuple(str(arg) for arg in item["argv"]),
                working_directory=str(item["working_directory"]),
                timeout_seconds=int(item["timeout_seconds"]),
            )
            command = TestCommandSpec(
                test_id=command.test_id,
                argv=command.argv,
                working_directory=command.working_directory,
                timeout_seconds=effective_command_timeout(
                    start_time=start,
                    total_timeout_seconds=int(test_policy_data["total_timeout_seconds"]),
                    command_timeout_seconds=command.timeout_seconds,
                ),
            )
            record, stdout, stderr = run_one_test(
                command=command,
                worktree=worktree,
                support_dir=support_dir,
                env=test_env,
                stdout_limit=int(test_policy_data["stdout_max_bytes"]),
                stderr_limit=int(test_policy_data["stderr_max_bytes"]),
            )
            executed.append(record)
            stdout_logs.append(stdout)
            stderr_logs.append(stderr)
            if record["status"] == "TIMEOUT":
                raise SandboxTestStatus(
                    RESULT_STATUS_TESTS_TIMEOUT,
                    "TEST_TIMEOUT",
                    "approved test command timed out",
                    "sandbox_test_execution",
                )
            if record["status"] == "OUTPUT_LIMIT":
                raise SandboxTestStatus(
                    RESULT_STATUS_TEST_OUTPUT_LIMIT,
                    "TEST_OUTPUT_LIMIT",
                    "approved test command exceeded output limits",
                    "sandbox_test_execution",
                )
            if record["status"] != "PASS":
                raise SandboxTestStatus(
                    RESULT_STATUS_TESTS_FAILED,
                    "TEST_EXIT_NONZERO",
                    "approved test command returned a non-zero exit code",
                    "sandbox_test_execution",
                )
        tracked_changes, untracked = post_test_changes(
            worktree=worktree,
            expected_files=context["expected_files"],
            expected_hashes=expected_hashes,
        )
        if tracked_changes or untracked:
            raise SandboxTestStatus(
                RESULT_STATUS_TEST_ENVIRONMENT_REJECTED,
                "TEST_GENERATED_FILES",
                "approved tests changed files outside the approved patch state",
                "sandbox_test_post_status",
            )
        result = base_test_result(
            context=context,
            status=RESULT_STATUS_TESTS_PASSED,
            failure_class=None,
            failure_code=None,
        )
        result.update(
            {
                "duration_seconds": round(time.monotonic() - start, 3),
                "tests_requested": [command_record(
                    TestCommandSpec(
                        test_id=str(item["test_id"]),
                        argv=tuple(str(arg) for arg in item["argv"]),
                        working_directory=str(item["working_directory"]),
                        timeout_seconds=int(item["timeout_seconds"]),
                    ),
                    status="PASS",
                ) for item in context["test_commands"]],
                "tests_executed": executed,
                "exit_codes": [item["exit_code"] for item in executed],
                "timeouts": [item["status"] == "TIMEOUT" for item in executed],
                "stdout_hashes": [item["stdout_hash"] for item in executed],
                "stderr_hashes": [item["stderr_hash"] for item in executed],
                "stdout_truncated": [item["stdout_truncated"] for item in executed],
                "stderr_truncated": [item["stderr_truncated"] for item in executed],
                "stdout_byte_counts": [item["stdout_bytes"] for item in executed],
                "stderr_byte_counts": [item["stderr_bytes"] for item in executed],
                "credentials_available": False,
                "patch_apply_result": check_result("PASS", "approved patch applied in sandbox"),
                "test_generated_tracked_changes": tracked_changes,
                "test_generated_untracked_files": untracked,
            }
        )
        if checkout_verification["head_sha"] != context["manifest"]["head_sha"]:
            raise SandboxTestStatus(
                RESULT_STATUS_BINDING_MISMATCH,
                "CHECKOUT_SHA_MISMATCH",
                "checkout SHA does not match sandbox test context",
                "sandbox_test_checkout",
            )
        if changed_files != context["expected_files"]:
            raise SandboxTestStatus(
                RESULT_STATUS_BINDING_MISMATCH,
                "CHANGED_FILES_MISMATCH",
                "sandbox changed files do not match proposal expected files",
                "sandbox_test_diff_binding",
            )
    except apply.ApplyStatus as status_error:
        result = base_test_result(
            context=context,
            status=RESULT_STATUS_PATCH_APPLY_FAILED,
            failure_class=RESULT_STATUS_PATCH_APPLY_FAILED,
            failure_code=status_error.code,
            failed_operation="sandbox_test_patch_apply",
            last_error=status_error.message,
        )
    except SandboxTestStatus as status_error:
        result = base_test_result(
            context=context,
            status=status_error.status,
            failure_class=status_error.status,
            failure_code=status_error.code,
            failed_operation=status_error.operation,
            last_error=status_error.message,
        )
        result.update(
            {
                "duration_seconds": round(time.monotonic() - start, 3),
                "tests_executed": executed,
                "exit_codes": [item["exit_code"] for item in executed],
                "timeouts": [item["status"] == "TIMEOUT" for item in executed],
                "stdout_hashes": [item["stdout_hash"] for item in executed],
                "stderr_hashes": [item["stderr_hash"] for item in executed],
                "stdout_truncated": [item["stdout_truncated"] for item in executed],
                "stderr_truncated": [item["stderr_truncated"] for item in executed],
                "stdout_byte_counts": [item["stdout_bytes"] for item in executed],
                "stderr_byte_counts": [item["stderr_bytes"] for item in executed],
            }
        )
    finally:
        cleanup = apply.cleanup_paths((patch_path, worktree))
        result["cleanup_performed"] = cleanup["status"] == "PASS"
        result["sandbox_destroyed"] = cleanup["status"] == "PASS"
        if cleanup["status"] != "PASS" and result["status"] == RESULT_STATUS_TESTS_PASSED:
            result["status"] = RESULT_STATUS_INTERNAL_ERROR
            result["failure_class"] = RESULT_STATUS_INTERNAL_ERROR
            result["failure_code"] = "SANDBOX_CLEANUP_FAILED"
            result["failed_operation"] = "sandbox_test_cleanup"
            result["last_error"] = cleanup["message"]
        validate_test_result_against_schema(result, schema_path)
        write_test_artifact(
            output_dir=output_dir,
            result=result,
            stdout_logs=stdout_logs,
            stderr_logs=stderr_logs,
        )
        github_output(
            {
                "result_ready": "true",
                "should_comment": "true",
                "status": str(result["status"]),
                "sandbox_test_id": str(result["sandbox_test_id"]),
            }
        )
        write_job_summary(
            "\n".join(
                [
                    "## Sandbox Test Result",
                    "",
                    f"- status: `{result['status']}`",
                    f"- sandbox test ID: `{result['sandbox_test_id']}`",
                    f"- tests executed: `{len(result['tests_executed'])}`",
                    f"- sandbox destroyed: `{result['sandbox_destroyed']}`",
                ]
            )
        )
    return 0


def command_post_comment(_: argparse.Namespace) -> int:
    try:
        repo = required_env("GITHUB_REPOSITORY")
        result_path = Path(required_env("TEST_RESULT_PATH"))
        result = read_json_file(result_path)
        if not isinstance(result, dict):
            raise fatal(
                fix.FailureCode.INVALID_PROPOSAL,
                "sandbox test result must be a JSON object",
                "sandbox_test_comment",
            )
        validate_test_result_against_schema(
            result,
            Path(required_env("SANDBOX_TEST_RESULT_SCHEMA")),
        )
        apply.validate_final_head(
            repo=repo,
            pr_number=int(required_env("PR_NUMBER")),
            expected_head_sha=required_env("HEAD_SHA"),
            token=required_env("GITHUB_TOKEN"),
            code="SANDBOX_TEST_COMMENT_HEAD_STALE",
        )
        body = sandbox_test_comment_body(
            result=result,
            workflow_run_id=required_env("WORKFLOW_RUN_ID"),
            repo=repo,
            artifact_id=os.environ.get("ARTIFACT_ID"),
        )
        comment_id, action = post_or_update_test_comment(
            repo=repo,
            issue_number=required_env("PR_NUMBER"),
            token=required_env("GITHUB_TOKEN"),
            body=body,
        )
        github_output({"comment_id": comment_id, "comment_action": action})
        return 0
    except apply.ApplyStatus as status_error:
        return fix.fail_command(
            fatal(
                fix.FailureCode.STALE_ARTIFACT,
                status_error.message,
                "sandbox_test_comment",
            )
        )
    except fix.FixProposalFailure as error:
        return fix.fail_command(error)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("download-request-artifact").set_defaults(
        func=command_download_request_artifact
    )
    subparsers.add_parser("validate-request").set_defaults(func=command_validate_request)
    subparsers.add_parser("prepare").set_defaults(func=command_prepare)
    subparsers.add_parser("run-tests").set_defaults(func=command_run_tests)
    subparsers.add_parser("post-comment").set_defaults(func=command_post_comment)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
