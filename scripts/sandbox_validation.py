#!/usr/bin/env python3
"""Stage 2C-A sandbox validation preflight helpers.

This module only decides whether a future sandbox validation may start. It
never checks out repository contents, applies proposal patches, runs tests,
commits, pushes, merges, or updates pull request contents.
"""

from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import json
import os
import re
import urllib.error
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import approval_record as approval
import architect_review_retry as stage1
import check_fix_proposal_design as proposal_design
import fix_proposal_generator as fix


EXPECTED_REPOSITORY = "Vectology-cloud-team/namma-rogue-agent"
COLLECTOR_WORKFLOW_NAME = "Sandbox Validation Request Collector"
VALIDATOR_WORKFLOW_NAME = "Sandbox Preflight Validator"
REQUEST_SCHEMA_VERSION = "sandbox-validation-request-v1"
RESULT_SCHEMA_VERSION = "sandbox-validation-result-v1"
RESULT_PHASE_PREFLIGHT = "PREFLIGHT"
RESULT_STATUS_PRECHECK_PASSED = "PRECHECK_PASSED"
RESULT_STATUS_PATCH_REJECTED = "PATCH_REJECTED"
RESULT_STATUS_STALE = "STALE"
RESULT_STATUS_FATAL = "FATAL"
RESULT_STATUS_INFRA_ERROR = "INFRA_ERROR"
SANDBOX_MARKER = "<!-- namma-ai-sandbox-validation -->"
PROPOSAL_LABEL = "ai-fix-proposal"
APPROVAL_LABEL = "ai-fix-approved"
VALIDATE_LABEL = "ai-fix-validate"
MAX_ARTIFACT_BYTES = 100000
ALLOWED_REPOSITORY_PERMISSIONS = {"admin", "maintain"}
DEFAULT_SANDBOX_TEST_IDS = (
    "unit",
    "stage2c-targeted",
    "workflow-checkers",
    "compileall",
)
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
DIFF_GIT_RE = re.compile(r"^diff --git a/(.+) b/(.+)$")
DATE_TIME_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    r"(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)
FORBIDDEN_PATCH_MARKERS = (
    "GIT binary patch",
    "Binary files ",
    "new file mode ",
    "deleted file mode ",
    "old mode ",
    "new mode ",
    "rename from ",
    "rename to ",
    "similarity index ",
    "dissimilarity index ",
    "--- /dev/null",
    "+++ /dev/null",
)
FORBIDDEN_TEST_FRAGMENTS = (
    " ",
    "|",
    ">",
    "<",
    "$(",
    "`",
    "/",
    "\\",
    "curl",
    "wget",
    "sudo",
    "docker",
    "pip",
    "npm",
    "apt",
)
BIDI_OR_FORMAT_RE = re.compile(
    "[\u061c\u200e\u200f\u202a-\u202e\u2066-\u2069]"
)


@dataclass(frozen=True)
class ArtifactBundle:
    data: dict[str, Any]
    metadata: dict[str, Any]
    artifact_id: int
    artifact_name: str
    workflow_run_id: int
    workflow_name: str


@dataclass(frozen=True)
class ApprovalBundle:
    record: dict[str, Any]
    artifact_id: int
    artifact_name: str
    workflow_run_id: int
    workflow_name: str


class PreflightStatus(Exception):
    def __init__(self, status: str, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def required_env(name: str) -> str:
    return stage1.required_env(name)


def github_output(values: dict[str, str]) -> None:
    stage1.github_output(values)


def write_job_summary(text: str) -> None:
    stage1.write_job_summary(text)


def now_utc() -> str:
    return dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")


def read_json_file(path: Path) -> Any:
    return fix.read_json_file(path)


def write_json_file(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def fatal(code: fix.FailureCode, message: str, operation: str) -> fix.FixProposalFailure:
    return fix.fatal(code, message, operation)


def canonical_json_bytes(value: Any) -> bytes:
    return fix.canonical_json_bytes(value)


def sha256_hex_json(value: Any) -> str:
    return fix.sha256_hex_json(value)


def ensure_full_sha(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not SHA_RE.fullmatch(value):
        raise fatal(
            fix.FailureCode.INVALID_MANIFEST,
            f"{field_name} must be a full lowercase commit SHA",
            "sandbox_request_validation",
        )
    return value


def ensure_sha256(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise fatal(
            fix.FailureCode.INVALID_PROPOSAL,
            f"{field_name} must be a lowercase SHA-256 hex digest",
            "sandbox_artifact_validation",
        )
    return value


def load_sandbox_test_ids(policy_path: Path) -> tuple[str, ...]:
    raw = proposal_design.parse_simple_yaml_mapping(
        policy_path.read_text(encoding="utf-8")
    )
    raw_ids = raw.get("sandbox_test_ids", list(DEFAULT_SANDBOX_TEST_IDS))
    if not isinstance(raw_ids, list) or not raw_ids:
        raise fatal(
            fix.FailureCode.WORKFLOW_CONFIGURATION_ERROR,
            "fix policy must define sandbox_test_ids",
            "sandbox_policy",
        )
    test_ids = tuple(str(test_id) for test_id in raw_ids)
    for test_id in test_ids:
        if not re.fullmatch(r"[a-z][a-z0-9_-]*", test_id):
            raise fatal(
                fix.FailureCode.WORKFLOW_CONFIGURATION_ERROR,
                "sandbox test IDs must be simple identifiers",
                "sandbox_policy",
            )
    return test_ids


def validate_request_manifest_shape(manifest: dict[str, Any]) -> None:
    required = {
        "schema_version",
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
            f"sandbox request manifest field mismatch: missing={missing} extra={extra}",
            "sandbox_request_validation",
        )
    if manifest["schema_version"] != REQUEST_SCHEMA_VERSION:
        raise fatal(
            fix.FailureCode.INVALID_MANIFEST,
            "unsupported sandbox request manifest schema",
            "sandbox_request_validation",
        )
    if manifest["repository"] != EXPECTED_REPOSITORY:
        raise fatal(
            fix.FailureCode.REPOSITORY_MISMATCH,
            "sandbox request repository mismatch",
            "sandbox_request_validation",
        )
    if manifest["collector_workflow_name"] != COLLECTOR_WORKFLOW_NAME:
        raise fatal(
            fix.FailureCode.TRUST_BOUNDARY_VIOLATION,
            "sandbox request came from an unexpected collector workflow",
            "sandbox_request_validation",
        )
    if not isinstance(manifest["pull_request_number"], int):
        raise fatal(
            fix.FailureCode.PR_MISMATCH,
            "pull_request_number must be an integer",
            "sandbox_request_validation",
        )
    ensure_full_sha(manifest["base_sha"], "base_sha")
    ensure_full_sha(manifest["head_sha"], "head_sha")
    if not isinstance(manifest["labels"], list):
        raise fatal(
            fix.FailureCode.INVALID_MANIFEST,
            "labels must be an array",
            "sandbox_request_validation",
        )
    if manifest["event_action"] != "labeled" or manifest["event_label"] != VALIDATE_LABEL:
        raise fatal(
            fix.FailureCode.LABEL_MISSING,
            "sandbox preflight requires the ai-fix-validate label event",
            "sandbox_request_validation",
        )
    if manifest["event_name"] != "pull_request":
        raise fatal(
            fix.FailureCode.INVALID_MANIFEST,
            "sandbox preflight request must come from pull_request",
            "sandbox_request_validation",
        )
    if not DATE_TIME_RE.fullmatch(str(manifest["requested_at"])):
        raise fatal(
            fix.FailureCode.INVALID_MANIFEST,
            "requested_at must be an ISO-8601 timestamp",
            "sandbox_request_validation",
        )


def labels_from_request(manifest: dict[str, Any]) -> set[str]:
    labels = manifest.get("labels", [])
    if not isinstance(labels, list):
        return set()
    return {str(label) for label in labels}


def validate_live_gate(
    *,
    manifest: dict[str, Any],
    live_pull: dict[str, Any],
    live_issue: dict[str, Any],
    policy: fix.FixProposalPolicy,
    validation_actor: str,
    validation_actor_permission: str,
) -> set[str]:
    validate_request_manifest_shape(manifest)
    live_labels = approval.labels_from_pull_or_issue(live_issue)
    required_labels = {
        policy.proposal_policy.proposal_label,
        policy.proposal_policy.approval_label,
        VALIDATE_LABEL,
    }
    if validation_actor != str(manifest["actor"]):
        raise fatal(
            fix.FailureCode.TRUST_BOUNDARY_VIOLATION,
            "validation actor mismatch between workflow_run and request artifact",
            "sandbox_live_gate",
        )
    if bool(manifest.get("draft")) or bool(live_pull.get("draft")):
        raise fatal(
            fix.FailureCode.DRAFT_PULL_REQUEST,
            "draft pull requests cannot run sandbox preflight",
            "sandbox_live_gate",
        )
    state = str(live_pull.get("state", ""))
    if state != "open":
        raise PreflightStatus(
            RESULT_STATUS_STALE,
            "PR_NOT_OPEN",
            "pull request is no longer open",
        )
    if manifest.get("base_repository") != EXPECTED_REPOSITORY:
        raise fatal(
            fix.FailureCode.REPOSITORY_MISMATCH,
            "base repository mismatch",
            "sandbox_live_gate",
        )
    if manifest.get("head_repository") != EXPECTED_REPOSITORY:
        raise fatal(
            fix.FailureCode.FORK_PULL_REQUEST,
            "fork pull requests cannot run sandbox preflight",
            "sandbox_live_gate",
        )
    missing_labels = sorted(required_labels.difference(live_labels))
    if missing_labels:
        raise fatal(
            fix.FailureCode.LABEL_MISSING,
            f"live pull request is missing labels: {missing_labels}",
            "sandbox_live_gate",
        )
    request_labels = labels_from_request(manifest)
    if VALIDATE_LABEL not in request_labels:
        raise fatal(
            fix.FailureCode.LABEL_MISSING,
            "request artifact does not contain ai-fix-validate",
            "sandbox_live_gate",
        )
    live_head_sha = str(live_pull.get("head", {}).get("sha", ""))
    live_base_sha = str(live_pull.get("base", {}).get("sha", ""))
    if live_head_sha != manifest["head_sha"]:
        raise PreflightStatus(
            RESULT_STATUS_STALE,
            "REQUEST_HEAD_STALE",
            "live pull request head SHA changed after request collection",
        )
    if live_base_sha != manifest["base_sha"]:
        raise PreflightStatus(
            RESULT_STATUS_STALE,
            "REQUEST_BASE_STALE",
            "live pull request base SHA changed after request collection",
        )
    if int(live_pull.get("number", 0)) != int(manifest["pull_request_number"]):
        raise fatal(
            fix.FailureCode.PR_MISMATCH,
            "live pull request number mismatch",
            "sandbox_live_gate",
        )
    if str(live_pull.get("user", {}).get("type", "")).lower() == "bot":
        raise fatal(
            fix.FailureCode.BOT_PULL_REQUEST,
            "bot pull requests cannot run sandbox preflight",
            "sandbox_live_gate",
        )
    if validation_actor_permission not in ALLOWED_REPOSITORY_PERMISSIONS:
        raise fatal(
            fix.FailureCode.UNAUTHORIZED_ASSOCIATION,
            "validation actor must have repository admin or maintain permission",
            "sandbox_live_gate",
        )
    return live_labels


def is_unavailable_artifact_candidate(error: BaseException) -> bool:
    return approval.is_unavailable_proposal_artifact_candidate(error)


def sorted_successful_workflow_runs(runs: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return approval.sorted_successful_workflow_runs(runs)


def artifact_provenance(
    *,
    artifact_id: int,
    artifact_name: str,
    workflow_run_id: int,
    workflow_name: str,
    repository: str,
    pull_request_number: int,
    head_sha: str,
) -> dict[str, Any]:
    return {
        "artifact_id": artifact_id,
        "artifact_name": artifact_name,
        "workflow_run_id": workflow_run_id,
        "workflow_name": workflow_name,
        "repository": repository,
        "pull_request_number": pull_request_number,
        "head_sha": head_sha,
    }


def find_latest_proposal_artifact(
    *,
    repo: str,
    token: str,
    manifest: dict[str, Any],
    policy: fix.FixProposalPolicy,
    output_dir: Path,
    max_bytes: int,
) -> ArtifactBundle:
    runs_data, _ = stage1.github_json(
        "GET",
        f"/repos/{repo}/actions/workflows/fix-proposal.yml/runs?status=completed&per_page=50",
        token=token,
    )
    runs = runs_data.get("workflow_runs", []) if isinstance(runs_data, dict) else []
    for run in sorted_successful_workflow_runs(runs):
        run_id = int(run.get("id", 0) or 0)
        try:
            artifacts_data, _ = stage1.github_json(
                "GET",
                f"/repos/{repo}/actions/runs/{run_id}/artifacts?per_page=100",
                token=token,
            )
        except BaseException as error:
            if is_unavailable_artifact_candidate(error):
                continue
            raise
        artifacts = (
            artifacts_data.get("artifacts", [])
            if isinstance(artifacts_data, dict)
            else []
        )
        for artifact in artifacts:
            name = str(artifact.get("name", ""))
            if not name.startswith("fix-proposal-"):
                continue
            try:
                artifact_id = fix.download_artifact_by_name(
                    repo=repo,
                    token=token,
                    run_id=str(run_id),
                    artifact_name=name,
                    target_dir=output_dir,
                    expected_files={"fix-proposal.json", "proposal-metadata.json"},
                    max_bytes=max_bytes,
                )
            except BaseException as error:
                if is_unavailable_artifact_candidate(error):
                    continue
                raise
            proposal = read_json_file(output_dir / "fix-proposal.json")
            metadata = read_json_file(output_dir / "proposal-metadata.json")
            if not isinstance(proposal, dict) or not isinstance(metadata, dict):
                raise fatal(
                    fix.FailureCode.INVALID_PROPOSAL,
                    "proposal artifact files must contain JSON objects",
                    "sandbox_proposal_lookup",
                )
            approval.validate_proposal_for_approval(
                manifest=manifest,
                proposal=proposal,
                metadata=metadata,
                policy=policy,
            )
            return ArtifactBundle(
                data=proposal,
                metadata=metadata,
                artifact_id=artifact_id,
                artifact_name=name,
                workflow_run_id=run_id,
                workflow_name=fix.GENERATOR_WORKFLOW_NAME,
            )
    raise fatal(
        fix.FailureCode.PROPOSAL_ARTIFACT_NOT_FOUND,
        "NOT_FOUND: no verified proposal artifact was found for this pull request head",
        "sandbox_proposal_lookup",
    )


def find_latest_approval_artifact(
    *,
    repo: str,
    token: str,
    manifest: dict[str, Any],
    proposal: dict[str, Any],
    metadata: dict[str, Any],
    policy_hash: str,
    output_dir: Path,
    max_bytes: int,
) -> ApprovalBundle:
    runs_data, _ = stage1.github_json(
        "GET",
        f"/repos/{repo}/actions/workflows/fix-approval.yml/runs?status=completed&per_page=50",
        token=token,
    )
    runs = runs_data.get("workflow_runs", []) if isinstance(runs_data, dict) else []
    candidates: list[ApprovalBundle] = []
    for run in sorted_successful_workflow_runs(runs):
        run_id = int(run.get("id", 0) or 0)
        try:
            artifacts_data, _ = stage1.github_json(
                "GET",
                f"/repos/{repo}/actions/runs/{run_id}/artifacts?per_page=100",
                token=token,
            )
        except BaseException as error:
            if is_unavailable_artifact_candidate(error):
                continue
            raise
        artifacts = (
            artifacts_data.get("artifacts", [])
            if isinstance(artifacts_data, dict)
            else []
        )
        for artifact in artifacts:
            name = str(artifact.get("name", ""))
            if not name.startswith("approval-record-"):
                continue
            try:
                artifact_id = fix.download_artifact_by_name(
                    repo=repo,
                    token=token,
                    run_id=str(run_id),
                    artifact_name=name,
                    target_dir=output_dir,
                    expected_files={"approval-record.json"},
                    max_bytes=max_bytes,
                )
            except BaseException as error:
                if is_unavailable_artifact_candidate(error):
                    continue
                raise
            record = read_json_file(output_dir / "approval-record.json")
            if not isinstance(record, dict):
                raise fatal(
                    fix.FailureCode.INVALID_PROPOSAL,
                    "approval artifact must contain a JSON object",
                    "sandbox_approval_lookup",
                )
            approval.validate_approval_record_shape(record)
            if record.get("repository") != manifest["repository"]:
                continue
            if record.get("pull_request_number") != manifest["pull_request_number"]:
                continue
            if record.get("proposal_id") != proposal.get("proposal_id"):
                continue
            if record.get("proposal_hash") != metadata.get("proposal_hash"):
                continue
            if record.get("head_sha") != manifest["head_sha"]:
                continue
            if record.get("policy_hash") != policy_hash:
                raise fatal(
                    fix.FailureCode.TRUST_BOUNDARY_VIOLATION,
                    "approval record policy hash does not match trusted policy",
                    "sandbox_approval_lookup",
                )
            if record.get("status") != approval.APPROVAL_STATUS_APPROVED:
                continue
            candidates.append(
                ApprovalBundle(
                    record=record,
                    artifact_id=artifact_id,
                    artifact_name=name,
                    workflow_run_id=run_id,
                    workflow_name=approval.RECORDER_WORKFLOW_NAME,
                )
            )
    if not candidates:
        raise fatal(
            fix.FailureCode.PROPOSAL_ARTIFACT_NOT_FOUND,
            "NOT_FOUND: no verified approval record artifact was found",
            "sandbox_approval_lookup",
        )
    return max(candidates, key=lambda candidate: str(candidate.record["approved_at"]))


def repo_path_has_forbidden_chars(path: str) -> bool:
    return any(ord(ch) < 32 or ord(ch) == 127 for ch in path) or bool(
        BIDI_OR_FORMAT_RE.search(path)
    )


def normalize_repo_path(path: str) -> str:
    return proposal_design.normalize_repo_path(path)


def is_protected_path(path: str, policy: proposal_design.FixPolicy) -> bool:
    normalized = normalize_repo_path(path)
    return any(
        fnmatch.fnmatch(normalized, pattern)
        for pattern in policy.protected_paths
    )


def validate_patch_path(path: str, policy: proposal_design.FixPolicy) -> str:
    if not isinstance(path, str) or not path:
        raise PreflightStatus(
            RESULT_STATUS_PATCH_REJECTED,
            "INVALID_PATH",
            "patch target path must be a non-empty string",
        )
    normalized = normalize_repo_path(path)
    if path != normalized:
        raise PreflightStatus(
            RESULT_STATUS_PATCH_REJECTED,
            "PATH_TRAVERSAL",
            "patch path must be repository-relative",
        )
    if repo_path_has_forbidden_chars(normalized):
        raise PreflightStatus(
            RESULT_STATUS_PATCH_REJECTED,
            "CONTROL_CHARACTER_PATH",
            "patch path contains control or format characters",
        )
    if normalized.startswith("../") or "/../" in normalized or normalized == "..":
        raise PreflightStatus(
            RESULT_STATUS_PATCH_REJECTED,
            "PATH_TRAVERSAL",
            "patch path may not escape the repository",
        )
    if normalized.startswith(".git/") or normalized == ".git":
        raise PreflightStatus(
            RESULT_STATUS_PATCH_REJECTED,
            "PROTECTED_PATH",
            "patch path may not target .git",
        )
    if is_protected_path(normalized, policy):
        raise PreflightStatus(
            RESULT_STATUS_PATCH_REJECTED,
            "PROTECTED_PATH",
            "patch path is protected by trusted policy",
        )
    return normalized


def parse_patch_file_path(
    *,
    line: str,
    prefix: str,
    policy: proposal_design.FixPolicy,
) -> str:
    if not line.startswith(prefix):
        raise PreflightStatus(
            RESULT_STATUS_PATCH_REJECTED,
            "PATCH_PATH_MISMATCH",
            "patch file header must use repository-relative a/ or b/ paths",
        )
    raw_path = line[len(prefix) :].split("\t", 1)[0]
    return validate_patch_path(raw_path, policy)


def parse_declared_patch_targets(
    *,
    patch: str,
    declared_path: str,
    policy: proposal_design.FixPolicy,
) -> set[str]:
    parsed_paths: set[str] = set()
    saw_diff_header = False
    saw_old_header = False
    saw_new_header = False
    for line in patch.splitlines():
        if line.startswith("diff --git "):
            saw_diff_header = True
            match = DIFF_GIT_RE.fullmatch(line)
            if match is None:
                raise PreflightStatus(
                    RESULT_STATUS_PATCH_REJECTED,
                    "PATCH_PATH_MISMATCH",
                    "diff header must use matching a/ and b/ repository paths",
                )
            old_path = validate_patch_path(match.group(1), policy)
            new_path = validate_patch_path(match.group(2), policy)
            if old_path != declared_path or new_path != declared_path:
                raise PreflightStatus(
                    RESULT_STATUS_PATCH_REJECTED,
                    "PATCH_PATH_MISMATCH",
                    "patch diff header targets an undeclared file",
                )
            parsed_paths.update({old_path, new_path})
        elif line.startswith("--- "):
            saw_old_header = True
            old_path = parse_patch_file_path(
                line=line,
                prefix="--- a/",
                policy=policy,
            )
            if old_path != declared_path:
                raise PreflightStatus(
                    RESULT_STATUS_PATCH_REJECTED,
                    "PATCH_PATH_MISMATCH",
                    "patch old-file header targets an undeclared file",
                )
            parsed_paths.add(old_path)
        elif line.startswith("+++ "):
            saw_new_header = True
            new_path = parse_patch_file_path(
                line=line,
                prefix="+++ b/",
                policy=policy,
            )
            if new_path != declared_path:
                raise PreflightStatus(
                    RESULT_STATUS_PATCH_REJECTED,
                    "PATCH_PATH_MISMATCH",
                    "patch new-file header targets an undeclared file",
                )
            parsed_paths.add(new_path)
    if not (saw_diff_header and saw_old_header and saw_new_header):
        raise PreflightStatus(
            RESULT_STATUS_PATCH_REJECTED,
            "PATCH_PATH_MISMATCH",
            "patch must contain diff, old-file, and new-file headers",
        )
    if parsed_paths != {declared_path}:
        raise PreflightStatus(
            RESULT_STATUS_PATCH_REJECTED,
            "PATCH_PATH_MISMATCH",
            "patch target set must match the proposal change path",
        )
    return parsed_paths


def validate_patch_metadata(
    *,
    proposal: dict[str, Any],
    policy: proposal_design.FixPolicy,
) -> dict[str, Any]:
    changes = proposal.get("changes", [])
    if not isinstance(changes, list) or not changes:
        raise PreflightStatus(
            RESULT_STATUS_PATCH_REJECTED,
            "NO_CHANGES",
            "proposal must contain at least one change",
        )
    if len(changes) > policy.max_changed_files:
        raise PreflightStatus(
            RESULT_STATUS_PATCH_REJECTED,
            "TOO_MANY_FILES",
            "proposal changes exceed trusted policy",
        )
    expected_files: list[str] = []
    parsed_patch_files: set[str] = set()
    patch_bytes_total = 0
    for change in changes:
        if not isinstance(change, dict):
            raise PreflightStatus(
                RESULT_STATUS_PATCH_REJECTED,
                "INVALID_CHANGE",
                "proposal change must be an object",
            )
        path = validate_patch_path(str(change.get("path", "")), policy)
        if change.get("operation") != "modify":
            raise PreflightStatus(
                RESULT_STATUS_PATCH_REJECTED,
                "UNSUPPORTED_PATCH_OPERATION",
                "Stage 2C-A preflight only accepts modify operations",
            )
        patch = change.get("patch")
        if not isinstance(patch, str) or not patch:
            raise PreflightStatus(
                RESULT_STATUS_PATCH_REJECTED,
                "INVALID_PATCH",
                "proposal patch must be a non-empty string",
            )
        patch_bytes = len(patch.encode("utf-8"))
        patch_bytes_total += patch_bytes
        if patch_bytes > policy.max_file_patch_bytes:
            raise PreflightStatus(
                RESULT_STATUS_PATCH_REJECTED,
                "PATCH_TOO_LARGE",
                "file patch exceeds trusted policy",
            )
        if BIDI_OR_FORMAT_RE.search(patch):
            raise PreflightStatus(
                RESULT_STATUS_PATCH_REJECTED,
                "PATCH_CONTROL_CHARACTER",
                "patch text contains hidden Unicode format characters",
            )
        for marker in FORBIDDEN_PATCH_MARKERS:
            if marker in patch:
                raise PreflightStatus(
                    RESULT_STATUS_PATCH_REJECTED,
                    "UNSUPPORTED_PATCH_OPERATION",
                    f"patch contains unsupported marker: {marker.strip()}",
                )
        parsed_patch_files.update(
            parse_declared_patch_targets(
                patch=patch,
                declared_path=path,
                policy=policy,
            )
        )
        expected_files.append(path)
    if parsed_patch_files != set(expected_files):
        raise PreflightStatus(
            RESULT_STATUS_PATCH_REJECTED,
            "PATCH_PATH_MISMATCH",
            "parsed patch paths must exactly match proposal changes",
        )
    if patch_bytes_total > policy.max_patch_bytes:
        raise PreflightStatus(
            RESULT_STATUS_PATCH_REJECTED,
            "PATCH_TOO_LARGE",
            "proposal patch bytes exceed trusted policy",
        )
    return {
        "status": "PASS",
        "message": f"validated metadata for {len(expected_files)} file(s)",
        "expected_files": expected_files,
        "patch_bytes": patch_bytes_total,
    }


def fetch_tree_entries(
    *,
    repo: str,
    head_sha: str,
    token: str,
) -> dict[str, dict[str, Any]]:
    tree_data, _ = stage1.github_json(
        "GET",
        f"/repos/{repo}/git/trees/{head_sha}?recursive=1",
        token=token,
    )
    entries = tree_data.get("tree", []) if isinstance(tree_data, dict) else []
    result: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if isinstance(entry, dict) and isinstance(entry.get("path"), str):
            result[str(entry["path"])] = entry
    return result


def validate_target_blob_shas(
    *,
    proposal: dict[str, Any],
    tree_entries: dict[str, dict[str, Any]],
    policy: proposal_design.FixPolicy,
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for change in proposal.get("changes", []):
        path = validate_patch_path(str(change.get("path", "")), policy)
        expected_sha = str(change.get("original_blob_sha", ""))
        if not SHA_RE.fullmatch(expected_sha):
            raise PreflightStatus(
                RESULT_STATUS_PATCH_REJECTED,
                "INVALID_BLOB_SHA",
                "proposal original_blob_sha must be a full commit-like blob SHA",
            )
        entry = tree_entries.get(path)
        if entry is None:
            raise PreflightStatus(
                RESULT_STATUS_STALE,
                "TARGET_FILE_MISSING",
                f"target file is missing at current head: {path}",
            )
        if entry.get("type") != "blob":
            raise PreflightStatus(
                RESULT_STATUS_PATCH_REJECTED,
                "UNSUPPORTED_FILE_TYPE",
                "target path is not a regular blob",
            )
        if str(entry.get("mode", "")) not in {"100644", "100755"}:
            raise PreflightStatus(
                RESULT_STATUS_PATCH_REJECTED,
                "UNSUPPORTED_FILE_MODE",
                "target file mode is not supported by Stage 2C-A",
            )
        actual_sha = str(entry.get("sha", ""))
        if actual_sha != expected_sha:
            raise PreflightStatus(
                RESULT_STATUS_STALE,
                "BLOB_SHA_MISMATCH",
                "target blob SHA does not match proposal",
            )
        size = int(entry.get("size", 0) or 0)
        if size > policy.max_file_patch_bytes * 20:
            raise PreflightStatus(
                RESULT_STATUS_PATCH_REJECTED,
                "TARGET_FILE_TOO_LARGE",
                "target file exceeds preflight size limit",
            )
        checks.append(
            {
                "path": path,
                "expected_blob_sha": expected_sha,
                "actual_blob_sha": actual_sha,
                "file_type": "blob",
                "mode": str(entry.get("mode", "")),
                "size": size,
                "status": "PASS",
            }
        )
    return checks


def normalize_test_ids(
    tests_recommended: Any,
    *,
    allowed_test_ids: Iterable[str],
) -> tuple[str, ...]:
    if not isinstance(tests_recommended, list):
        raise PreflightStatus(
            RESULT_STATUS_PATCH_REJECTED,
            "INVALID_TEST_PLAN",
            "tests_recommended must be a list",
        )
    allowed = set(allowed_test_ids)
    normalized: list[str] = []
    for item in tests_recommended:
        if not isinstance(item, str):
            raise PreflightStatus(
                RESULT_STATUS_PATCH_REJECTED,
                "INVALID_TEST_PLAN",
                "test recommendation must be a trusted test ID string",
            )
        test_id = item.strip()
        lowered = test_id.lower()
        if any(fragment in lowered for fragment in FORBIDDEN_TEST_FRAGMENTS):
            raise PreflightStatus(
                RESULT_STATUS_PATCH_REJECTED,
                "UNTRUSTED_TEST_COMMAND",
                "test recommendation contains command syntax",
            )
        if test_id not in allowed:
            raise PreflightStatus(
                RESULT_STATUS_PATCH_REJECTED,
                "UNKNOWN_TEST_ID",
                "test recommendation is not present in trusted policy",
            )
        normalized.append(test_id)
    return tuple(dict.fromkeys(normalized))


def test_evidence(test_id: str) -> dict[str, Any]:
    return {
        "test_id": test_id,
        "requested": True,
        "executed": False,
        "status": "SKIPPED",
        "exit_code": None,
        "duration_ms": 0,
        "log_excerpt": "Stage 2C-A preflight records the test plan but does not execute tests.",
    }


def check_result(status: str, message: str) -> dict[str, str]:
    return {
        "status": status,
        "message": message,
    }


def schema_property_names(schema: dict[str, Any]) -> set[str]:
    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        raise fatal(
            fix.FailureCode.WORKFLOW_CONFIGURATION_ERROR,
            "sandbox result schema must declare top-level properties",
            "sandbox_result_schema",
        )
    return set(properties)


def validate_result_against_schema(result: dict[str, Any], schema_path: Path) -> None:
    schema = read_json_file(schema_path)
    if not isinstance(schema, dict):
        raise fatal(
            fix.FailureCode.WORKFLOW_CONFIGURATION_ERROR,
            "sandbox result schema must be a JSON object",
            "sandbox_result_schema",
        )
    required = schema.get("required")
    if not isinstance(required, list):
        raise fatal(
            fix.FailureCode.WORKFLOW_CONFIGURATION_ERROR,
            "sandbox result schema must declare required fields",
            "sandbox_result_schema",
        )
    missing = sorted(set(str(item) for item in required).difference(result))
    extra = sorted(set(result).difference(schema_property_names(schema)))
    if missing or extra:
        raise fatal(
            fix.FailureCode.INVALID_PROPOSAL,
            f"sandbox result shape mismatch missing={missing} extra={extra}",
            "sandbox_result_schema",
        )
    if result.get("schema_version") != RESULT_SCHEMA_VERSION:
        raise fatal(
            fix.FailureCode.INVALID_PROPOSAL,
            "sandbox result schema_version mismatch",
            "sandbox_result_schema",
        )
    status = result.get("status")
    if status not in {
        RESULT_STATUS_PRECHECK_PASSED,
        "SUCCESS",
        RESULT_STATUS_PATCH_REJECTED,
        "TEST_FAILED",
        RESULT_STATUS_STALE,
        RESULT_STATUS_FATAL,
        RESULT_STATUS_INFRA_ERROR,
    }:
        raise fatal(
            fix.FailureCode.INVALID_PROPOSAL,
            "sandbox result status is not allowed",
            "sandbox_result_schema",
        )
    for flag in (
        "persistent_repository_modified",
        "commit_created",
        "push_performed",
        "merge_performed",
    ):
        if result.get(flag) is not False:
            raise fatal(
                fix.FailureCode.INVALID_PROPOSAL,
                f"sandbox result must keep {flag}=false",
                "sandbox_result_schema",
            )
    if status == RESULT_STATUS_PRECHECK_PASSED:
        precheck_expectations = {
            "phase": RESULT_PHASE_PREFLIGHT,
            "failure_class": None,
            "failure_code": None,
            "sandbox_worktree_modified": False,
            "sandbox_checkout_performed": False,
            "patch_check_performed": False,
            "patch_applied": False,
            "test_execution_performed": False,
            "sandbox_destroyed": True,
        }
        for key, expected in precheck_expectations.items():
            if result.get(key) != expected:
                raise fatal(
                    fix.FailureCode.INVALID_PROPOSAL,
                    f"PRECHECK_PASSED requires {key}={expected!r}",
                    "sandbox_result_schema",
                )
        for check_name, expected_status in (
            ("patch_check", "SKIPPED"),
            ("patch_apply", "SKIPPED"),
            ("protected_path_check", "PASS"),
            ("blob_sha_check", "PASS"),
            ("patch_metadata_check", "PASS"),
        ):
            check = result.get(check_name)
            if not isinstance(check, dict) or check.get("status") != expected_status:
                raise fatal(
                    fix.FailureCode.INVALID_PROPOSAL,
                    f"PRECHECK_PASSED requires {check_name}.{expected_status}",
                    "sandbox_result_schema",
                )
        for test in result.get("tests_requested", []):
            if (
                not isinstance(test, dict)
                or test.get("requested") is not True
                or test.get("executed") is not False
                or test.get("status") != "SKIPPED"
            ):
                raise fatal(
                    fix.FailureCode.INVALID_PROPOSAL,
                    "PRECHECK_PASSED requires requested tests to be skipped",
                    "sandbox_result_schema",
                )
        if result.get("tests_executed") or result.get("test_results"):
            raise fatal(
                fix.FailureCode.INVALID_PROPOSAL,
                "PRECHECK_PASSED must not contain executed tests",
                "sandbox_result_schema",
            )
        return
    if result.get("failure_class") != status:
        raise fatal(
            fix.FailureCode.INVALID_PROPOSAL,
            "non-success sandbox result must bind failure_class to status",
            "sandbox_result_schema",
        )
    if not result.get("failure_code"):
        raise fatal(
            fix.FailureCode.INVALID_PROPOSAL,
            "non-success sandbox result must include failure_code",
            "sandbox_result_schema",
        )


def validation_id_for(
    *,
    repository: str,
    pull_request_number: int,
    head_sha: str,
    proposal_id: str,
    proposal_hash: str,
    approval_id: str,
    approval_record_hash: str,
    validation_request_actor: str,
    policy_hash: str,
    test_plan_hash: str,
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
            "validation_request_actor": validation_request_actor,
            "policy_hash": policy_hash,
            "phase": RESULT_PHASE_PREFLIGHT,
            "test_plan_hash": test_plan_hash,
        }
    )[:32]


def build_precheck_result(
    *,
    manifest: dict[str, Any],
    proposal_bundle: ArtifactBundle,
    approval_bundle: ApprovalBundle,
    validation_actor: str,
    validation_actor_permission: str,
    validation_actor_role: str | None,
    live_labels: Iterable[str],
    target_blob_checks: list[dict[str, Any]],
    patch_metadata_check: dict[str, Any],
    test_ids: tuple[str, ...],
    status: str = RESULT_STATUS_PRECHECK_PASSED,
    failure_class: str | None = None,
    failure_code: str | None = None,
    completed_at: str | None = None,
) -> dict[str, Any]:
    completed = completed_at or now_utc()
    proposal = proposal_bundle.data
    metadata = proposal_bundle.metadata
    record = approval_bundle.record
    test_plan_hash = sha256_hex_json(
        {
            "phase": RESULT_PHASE_PREFLIGHT,
            "test_ids": list(test_ids),
        }
    )
    validation_id = validation_id_for(
        repository=manifest["repository"],
        pull_request_number=int(manifest["pull_request_number"]),
        head_sha=manifest["head_sha"],
        proposal_id=str(metadata["proposal_id"]),
        proposal_hash=str(metadata["proposal_hash"]),
        approval_id=str(record["approval_id"]),
        approval_record_hash=str(record["approval_record_hash"]),
        validation_request_actor=validation_actor,
        policy_hash=str(metadata["policy_hash"]),
        test_plan_hash=test_plan_hash,
    )
    tests_requested = [test_evidence(test_id) for test_id in test_ids]
    expected_files = list(patch_metadata_check.get("expected_files", []))
    return {
        "schema_version": RESULT_SCHEMA_VERSION,
        "validation_id": validation_id,
        "phase": RESULT_PHASE_PREFLIGHT,
        "repository": manifest["repository"],
        "pull_request_number": int(manifest["pull_request_number"]),
        "base_sha": manifest["base_sha"],
        "head_sha": manifest["head_sha"],
        "proposal_id": str(metadata["proposal_id"]),
        "proposal_hash": str(metadata["proposal_hash"]),
        "approval_id": str(record["approval_id"]),
        "approval_record_hash": str(record["approval_record_hash"]),
        "approved_by": str(record["approved_by"]),
        "approved_by_repository_permission": str(record["approved_by_repository_permission"]),
        "approved_by_repository_role": record.get("approved_by_repository_role"),
        "validation_request_actor": validation_actor,
        "validation_request_actor_repository_permission": validation_actor_permission,
        "validation_request_actor_repository_role": validation_actor_role,
        "live_labels": sorted(set(str(label) for label in live_labels)),
        "proposal_artifact": artifact_provenance(
            artifact_id=proposal_bundle.artifact_id,
            artifact_name=proposal_bundle.artifact_name,
            workflow_run_id=proposal_bundle.workflow_run_id,
            workflow_name=proposal_bundle.workflow_name,
            repository=manifest["repository"],
            pull_request_number=int(manifest["pull_request_number"]),
            head_sha=str(proposal["head_sha"]),
        ),
        "approval_artifact": artifact_provenance(
            artifact_id=approval_bundle.artifact_id,
            artifact_name=approval_bundle.artifact_name,
            workflow_run_id=approval_bundle.workflow_run_id,
            workflow_name=approval_bundle.workflow_name,
            repository=manifest["repository"],
            pull_request_number=int(manifest["pull_request_number"]),
            head_sha=str(record["head_sha"]),
        ),
        "schema_versions": {
            "proposal": str(proposal["schema_version"]),
            "approval": str(record["schema_version"]),
            "validation_result": RESULT_SCHEMA_VERSION,
        },
        "policy_hash": str(metadata["policy_hash"]),
        "test_plan_hash": test_plan_hash,
        "started_at": completed,
        "completed_at": completed,
        "status": status,
        "failure_class": failure_class,
        "failure_code": failure_code,
        "patch_check": check_result(
            "SKIPPED",
            "Stage 2C-A does not run patch applicability checks.",
        ),
        "patch_apply": check_result(
            "SKIPPED",
            "Stage 2C-A does not apply patches.",
        ),
        "expected_files": expected_files,
        "actual_changed_files": [],
        "protected_path_check": check_result(
            "PASS",
            "No protected paths were targeted.",
        ),
        "blob_sha_check": check_result(
            "PASS",
            "Target blob SHAs match current pull request head.",
        ),
        "target_blob_checks": target_blob_checks,
        "patch_metadata_check": {
            "status": patch_metadata_check["status"],
            "message": patch_metadata_check["message"],
            "patch_bytes": patch_metadata_check["patch_bytes"],
        },
        "tests_requested": tests_requested,
        "tests_executed": [],
        "test_results": [],
        "changed_files_match_expected": True,
        "persistent_repository_modified": False,
        "sandbox_worktree_modified": False,
        "sandbox_checkout_performed": False,
        "patch_check_performed": False,
        "patch_applied": False,
        "test_execution_performed": False,
        "commit_created": False,
        "push_performed": False,
        "merge_performed": False,
        "sandbox_destroyed": True,
    }


def validate_final_head(
    *,
    repo: str,
    pr_number: int,
    expected_head_sha: str,
    token: str,
) -> None:
    live_pull = approval.fetch_live_pull(
        repo=repo,
        pr_number=pr_number,
        token=token,
    )
    if str(live_pull.get("head", {}).get("sha", "")) != expected_head_sha:
        raise PreflightStatus(
            RESULT_STATUS_STALE,
            "FINAL_HEAD_STALE",
            "pull request head changed before preflight completion",
        )


def write_preflight_artifact(
    *,
    output_dir: Path,
    result: dict[str, Any],
    proposal_bundle: ArtifactBundle,
    approval_bundle: ApprovalBundle,
    target_blob_checks: list[dict[str, Any]],
    patch_metadata_check: dict[str, Any],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json_file(output_dir / "sandbox-validation-result.json", result)
    write_json_file(
        output_dir / "selected-proposal-manifest.json",
        {
            "artifact_id": proposal_bundle.artifact_id,
            "artifact_name": proposal_bundle.artifact_name,
            "workflow_run_id": proposal_bundle.workflow_run_id,
            "proposal_id": proposal_bundle.metadata.get("proposal_id"),
            "proposal_hash": proposal_bundle.metadata.get("proposal_hash"),
            "head_sha": proposal_bundle.metadata.get("head_sha"),
        },
    )
    write_json_file(
        output_dir / "selected-approval-manifest.json",
        {
            "artifact_id": approval_bundle.artifact_id,
            "artifact_name": approval_bundle.artifact_name,
            "workflow_run_id": approval_bundle.workflow_run_id,
            "approval_id": approval_bundle.record.get("approval_id"),
            "approval_record_hash": approval_bundle.record.get("approval_record_hash"),
            "head_sha": approval_bundle.record.get("head_sha"),
        },
    )
    write_json_file(output_dir / "target-blob-checks.json", target_blob_checks)
    write_json_file(output_dir / "patch-metadata-check.json", patch_metadata_check)


def sandbox_comment_body(
    *,
    result: dict[str, Any],
    workflow_run_id: str,
    repo: str,
) -> str:
    run_url = f"https://github.com/{repo}/actions/runs/{workflow_run_id}"
    live_gate = "PASS" if result["status"] == RESULT_STATUS_PRECHECK_PASSED else result["status"]
    planned_tests = ", ".join(
        f"`{test['test_id']}`" for test in result.get("tests_requested", [])
    ) or "None"
    return "\n".join(
        [
            SANDBOX_MARKER,
            "",
            "## AI Sandbox Validation Preflight",
            "",
            "> Stage 2C-A preflight completed. No sandbox checkout, patch application, tests, commit, push, or merge were performed.",
            "",
            f"- Phase: `{result['phase']}`",
            f"- Status: `{result['status']}`",
            f"- Validation ID: `{result['validation_id']}`",
            f"- Proposal ID: `{result['proposal_id']}`",
            f"- Approval ID: `{result['approval_id']}`",
            f"- HEAD SHA: `{result['head_sha']}`",
            f"- Approval Actor: `{result['approved_by']}`",
            f"- Validation Requested By: `{result['validation_request_actor']}`",
            f"- Live Gate: `{live_gate}`",
            f"- Artifact Validation: `PASS`",
            f"- Blob SHA Check: `{result['blob_sha_check']['status']}`",
            f"- Patch Metadata Check: `{result['patch_metadata_check']['status']}`",
            f"- Planned Tests: {planned_tests}",
            f"- Workflow run: {run_url}",
            "",
            "### Safety",
            "",
            "- Sandbox Checkout Performed: `No`",
            "- Patch Applied: `No`",
            "- Tests Executed: `No`",
            "- Persistent Repository Modified: `No`",
            "- Commit Created: `No`",
            "- Push Performed: `No`",
            "- Merge Performed: `No`",
        ]
    )


def post_or_update_sandbox_comment(
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
        if SANDBOX_MARKER in str(comment.get("body", ""))
    ]
    if marker_comments:
        comment_id = str(marker_comments[0]["id"])
        stage1.github_json(
            "PATCH",
            f"/repos/{repo}/issues/comments/{comment_id}",
            token=token,
            payload={"body": body},
        )
        return comment_id, "update"
    comment, _ = stage1.github_json(
        "POST",
        f"/repos/{repo}/issues/{issue_number}/comments",
        token=token,
        payload={"body": body},
    )
    if not isinstance(comment, dict) or "id" not in comment:
        raise fatal(
            fix.FailureCode.PERMISSION_ERROR,
            "GitHub issue comment create response was malformed",
            "github_sandbox_comment_create",
        )
    return str(comment["id"]), "create"


def command_download_request_artifact(_: argparse.Namespace) -> int:
    try:
        artifact_id = fix.run_with_retry(
            "github_sandbox_request_artifact",
            lambda: fix.download_artifact_by_name(
                repo=required_env("GITHUB_REPOSITORY"),
                token=required_env("GITHUB_TOKEN"),
                run_id=required_env("COLLECTOR_RUN_ID"),
                artifact_name=required_env("ARTIFACT_NAME"),
                target_dir=Path(required_env("SANDBOX_REQUEST_DIR")),
                expected_files={"manifest.json"},
                max_bytes=int(required_env("MAX_ARTIFACT_BYTES")),
            ),
        ).value
        github_output({"request_artifact_id": str(artifact_id)})
        return 0
    except BaseException as error:
        return fix.fail_command(error)


def command_validate_request(_: argparse.Namespace) -> int:
    try:
        manifest = read_json_file(Path(required_env("SANDBOX_REQUEST_DIR")) / "manifest.json")
        if not isinstance(manifest, dict):
            raise fatal(
                fix.FailureCode.INVALID_MANIFEST,
                "sandbox request manifest must be a JSON object",
                "sandbox_request_validation",
            )
        validate_request_manifest_shape(manifest)
        github_output(
            {
                "pr_number": str(manifest["pull_request_number"]),
                "head_sha": str(manifest["head_sha"]),
                "base_sha": str(manifest["base_sha"]),
            }
        )
        return 0
    except BaseException as error:
        return fix.fail_command(error)


def command_preflight(_: argparse.Namespace) -> int:
    try:
        repo = required_env("GITHUB_REPOSITORY")
        token = required_env("GITHUB_TOKEN")
        request_dir = Path(required_env("SANDBOX_REQUEST_DIR"))
        proposal_dir = Path(required_env("PROPOSAL_ARTIFACT_DIR"))
        approval_dir = Path(required_env("APPROVAL_ARTIFACT_DIR"))
        output_dir = Path(required_env("PREFLIGHT_RESULT_DIR"))
        policy_path = Path(required_env("FIX_POLICY"))
        result_schema_path = Path(required_env("SANDBOX_RESULT_SCHEMA"))
        max_bytes = int(os.environ.get("MAX_ARTIFACT_BYTES", str(MAX_ARTIFACT_BYTES)))
        validation_actor = required_env("VALIDATION_ACTOR")
        manifest = read_json_file(request_dir / "manifest.json")
        if not isinstance(manifest, dict):
            raise fatal(
                fix.FailureCode.INVALID_MANIFEST,
                "sandbox request manifest must be a JSON object",
                "sandbox_preflight",
            )
        validate_request_manifest_shape(manifest)
        policy = fix.load_fix_proposal_policy(policy_path)
        allowed_test_ids = load_sandbox_test_ids(policy_path)
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
        validation_permission = approval.approval_actor_repository_permission(
            repo=repo,
            actor=validation_actor,
            token=token,
        )
        validation_permission_name = str(validation_permission["permission"])
        validation_role = validation_permission.get("role_name")
        live_labels = validate_live_gate(
            manifest=manifest,
            live_pull=live_pull,
            live_issue=live_issue,
            policy=policy,
            validation_actor=validation_actor,
            validation_actor_permission=validation_permission_name,
        )
        proposal_bundle = find_latest_proposal_artifact(
            repo=repo,
            token=token,
            manifest=manifest,
            policy=policy,
            output_dir=proposal_dir,
            max_bytes=max_bytes,
        )
        approval_bundle = find_latest_approval_artifact(
            repo=repo,
            token=token,
            manifest=manifest,
            proposal=proposal_bundle.data,
            metadata=proposal_bundle.metadata,
            policy_hash=policy.policy_hash,
            output_dir=approval_dir,
            max_bytes=max_bytes,
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
                "approved actor no longer has repository admin or maintain permission",
                "sandbox_approval_actor_permission",
            )
        patch_metadata_check: dict[str, Any] | None = None
        target_blob_checks: list[dict[str, Any]] = []
        test_ids: tuple[str, ...] = ()
        status = RESULT_STATUS_PRECHECK_PASSED
        failure_class: str | None = None
        failure_code: str | None = None
        try:
            tree_entries = fetch_tree_entries(
                repo=repo,
                head_sha=str(manifest["head_sha"]),
                token=token,
            )
            patch_metadata_check = validate_patch_metadata(
                proposal=proposal_bundle.data,
                policy=policy.proposal_policy,
            )
            target_blob_checks = validate_target_blob_shas(
                proposal=proposal_bundle.data,
                tree_entries=tree_entries,
                policy=policy.proposal_policy,
            )
            test_ids = normalize_test_ids(
                proposal_bundle.data.get("tests_recommended", []),
                allowed_test_ids=allowed_test_ids,
            )
            validate_final_head(
                repo=repo,
                pr_number=int(manifest["pull_request_number"]),
                expected_head_sha=str(manifest["head_sha"]),
                token=token,
            )
        except PreflightStatus as status_error:
            status = status_error.status
            failure_class = status_error.status
            failure_code = status_error.code
            if patch_metadata_check is None:
                patch_metadata_check = {
                    "status": "FAIL",
                    "message": status_error.message,
                    "expected_files": [],
                    "patch_bytes": 0,
                }
        result = build_precheck_result(
            manifest=manifest,
            proposal_bundle=proposal_bundle,
            approval_bundle=approval_bundle,
            validation_actor=validation_actor,
            validation_actor_permission=validation_permission_name,
            validation_actor_role=validation_role,
            live_labels=live_labels,
            target_blob_checks=target_blob_checks,
            patch_metadata_check=patch_metadata_check,
            test_ids=test_ids,
            status=status,
            failure_class=failure_class,
            failure_code=failure_code,
        )
        if failure_code in {
            "BLOB_SHA_MISMATCH",
            "TARGET_FILE_MISSING",
            "UNSUPPORTED_FILE_TYPE",
            "UNSUPPORTED_FILE_MODE",
            "TARGET_FILE_TOO_LARGE",
        }:
            result["blob_sha_check"] = check_result("FAIL", failure_code)
        if failure_code == "PROTECTED_PATH":
            result["protected_path_check"] = check_result("FAIL", failure_code)
        validate_result_against_schema(result, result_schema_path)
        write_preflight_artifact(
            output_dir=output_dir,
            result=result,
            proposal_bundle=proposal_bundle,
            approval_bundle=approval_bundle,
            target_blob_checks=target_blob_checks,
            patch_metadata_check=patch_metadata_check,
        )
        artifact_name = f"sandbox-validation-preflight-{result['validation_id']}"
        github_output(
            {
                "preflight_ready": "true",
                "should_comment": "true",
                "artifact_name": artifact_name,
                "validation_id": str(result["validation_id"]),
                "pr_number": str(result["pull_request_number"]),
                "head_sha": str(result["head_sha"]),
                "status": str(result["status"]),
            }
        )
        write_job_summary(
            "\n".join(
                [
                    "## Sandbox Validation Preflight",
                    "",
                    f"- status: `{result['status']}`",
                    f"- validation ID: `{result['validation_id']}`",
                    f"- proposal ID: `{result['proposal_id']}`",
                    f"- approval ID: `{result['approval_id']}`",
                    f"- failure class: `{result['failure_class']}`",
                    f"- failure code: `{result['failure_code']}`",
                    "- sandbox checkout performed: `false`",
                    "- patch applied: `false`",
                    "- tests executed: `false`",
                ]
            )
        )
        return 0
    except BaseException as error:
        return fix.fail_command(error)


def command_post_comment(_: argparse.Namespace) -> int:
    try:
        repo = required_env("GITHUB_REPOSITORY")
        token = required_env("GITHUB_TOKEN")
        pr_number = required_env("PR_NUMBER")
        head_sha = required_env("HEAD_SHA")
        result_path = Path(required_env("SANDBOX_RESULT_PATH"))
        workflow_run_id = required_env("WORKFLOW_RUN_ID")
        result = read_json_file(result_path)
        if not isinstance(result, dict):
            raise fatal(
                fix.FailureCode.INVALID_PROPOSAL,
                "sandbox validation result must be a JSON object",
                "sandbox_comment",
            )
        schema_path = os.environ.get("SANDBOX_RESULT_SCHEMA")
        if schema_path:
            validate_result_against_schema(result, Path(schema_path))
        stage1.validate_comment_target(repo, pr_number, head_sha, token)
        body = sandbox_comment_body(
            result=result,
            workflow_run_id=workflow_run_id,
            repo=repo,
        )
        comment_id, action = post_or_update_sandbox_comment(
            repo=repo,
            issue_number=pr_number,
            token=token,
            body=body,
        )
        github_output(
            {
                "comment_id": comment_id,
                "comment_action": action,
            }
        )
        return 0
    except BaseException as error:
        return fix.fail_command(error)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("download-request-artifact").set_defaults(
        func=command_download_request_artifact
    )
    subparsers.add_parser("validate-request").set_defaults(func=command_validate_request)
    subparsers.add_parser("preflight").set_defaults(func=command_preflight)
    subparsers.add_parser("post-comment").set_defaults(func=command_post_comment)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
