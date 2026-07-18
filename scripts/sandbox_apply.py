#!/usr/bin/env python3
"""Stage 2C-B1 ephemeral sandbox patch apply helpers.

This module verifies an approved fix proposal inside a temporary sandbox
working tree. It may check out the exact pull request HEAD into the sandbox,
run fixed `git apply` argv, inspect the resulting diff, and write result
artifacts. It must never run recommended tests, commit, push, merge, update PR
contents, use code suggestions, install packages, or persist repository
changes.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import stat
import subprocess
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import approval_record as approval
import architect_review_retry as stage1
import check_fix_proposal_design as proposal_design
import fix_proposal_generator as fix
import sandbox_validation as preflight


EXPECTED_REPOSITORY = "Vectology-cloud-team/namma-rogue-agent"
COLLECTOR_WORKFLOW_NAME = "Sandbox Apply Request Collector"
APPLY_WORKFLOW_NAME = "Sandbox Apply Validator"
REQUEST_SCHEMA_VERSION = "sandbox-apply-request-v1"
REQUEST_STAGE = "SANDBOX_APPLY_REQUEST"
RESULT_PHASE_SANDBOX_APPLY = "SANDBOX_APPLY"
RESULT_STATUS_APPLY_PASSED = "APPLY_PASSED"
RESULT_STATUS_PATCH_REJECTED = "PATCH_REJECTED"
RESULT_STATUS_STALE = "STALE"
RESULT_STATUS_FATAL = "FATAL"
RESULT_STATUS_INFRA_ERROR = "INFRA_ERROR"
APPLY_LABEL = "ai-fix-apply-sandbox"
SANDBOX_APPLY_MARKER = "<!-- namma-ai-sandbox-apply -->"
MAX_ARTIFACT_BYTES = 100000
ALLOWED_REPOSITORY_PERMISSIONS = {"admin", "maintain"}
APPLY_CONTEXT_FILE = "sandbox-apply-context.json"
PREFLIGHT_ARTIFACT_MEMBERS = frozenset(
    {
        "sandbox-validation-result.json",
        "selected-proposal-manifest.json",
        "selected-approval-manifest.json",
        "target-blob-checks.json",
        "patch-metadata-check.json",
    }
)

GIT_APPLY_CHECK_ARGV = (
    "git",
    "apply",
    "--check",
    "--verbose",
    "--recount",
    "--whitespace=error-all",
)
GIT_APPLY_ARGV = (
    "git",
    "apply",
    "--verbose",
    "--recount",
    "--whitespace=error-all",
)
FORBIDDEN_GIT_APPLY_OPTIONS = {
    "--unsafe-paths",
    "--allow-binary-replacement",
    "--index",
    "--cached",
    "--3way",
    "--reject",
    "--directory",
    "--include",
    "--exclude",
}


@dataclass(frozen=True)
class PreflightBundle:
    result: dict[str, Any]
    result_hash: str
    artifact_id: int
    artifact_name: str
    workflow_run_id: int
    workflow_name: str


class ApplyStatus(Exception):
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
    return preflight.now_utc()


def read_json_file(path: Path) -> Any:
    return fix.read_json_file(path)


def write_json_file(path: Path, value: Any) -> None:
    preflight.write_json_file(path, value)


class SchemaValidationError(ValueError):
    """Raised when a result does not match the trusted JSON Schema subset."""


def _resolve_schema_ref(root: dict[str, Any], ref: str) -> dict[str, Any]:
    if not ref.startswith("#/"):
        raise SchemaValidationError(f"unsupported schema ref {ref}")
    node: Any = root
    for raw_part in ref[2:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, dict) or part not in node:
            raise SchemaValidationError(f"unresolved schema ref {ref}")
        node = node[part]
    if not isinstance(node, dict):
        raise SchemaValidationError(f"schema ref {ref} does not resolve to an object")
    return node


def _value_matches_type(value: Any, type_name: str) -> bool:
    if type_name == "object":
        return isinstance(value, dict)
    if type_name == "array":
        return isinstance(value, list)
    if type_name == "string":
        return isinstance(value, str)
    if type_name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if type_name == "boolean":
        return isinstance(value, bool)
    if type_name == "null":
        return value is None
    return False


def _validate_json_schema_node(
    value: Any,
    schema_node: dict[str, Any],
    root: dict[str, Any],
    path: str,
) -> None:
    if "$ref" in schema_node:
        schema_node = _resolve_schema_ref(root, str(schema_node["$ref"]))
    if "allOf" in schema_node:
        all_of = schema_node["allOf"]
        if not isinstance(all_of, list):
            raise SchemaValidationError(f"{path}: allOf must be an array")
        for index, entry in enumerate(all_of):
            if not isinstance(entry, dict):
                raise SchemaValidationError(f"{path}: allOf[{index}] must be an object")
            if "if" in entry and "then" in entry:
                if _json_schema_condition_matches(value, entry["if"], root, path):
                    then_schema = entry["then"]
                    if not isinstance(then_schema, dict):
                        raise SchemaValidationError(f"{path}: then must be an object")
                    _validate_json_schema_node(value, then_schema, root, path)
            else:
                _validate_json_schema_node(value, entry, root, path)
    if "const" in schema_node and value != schema_node["const"]:
        raise SchemaValidationError(
            f"{path}: expected const {schema_node['const']!r}, got {value!r}"
        )
    if "enum" in schema_node and value not in schema_node["enum"]:
        raise SchemaValidationError(f"{path}: {value!r} is not in enum")
    if "type" in schema_node:
        expected_type = schema_node["type"]
        expected_types = expected_type if isinstance(expected_type, list) else [expected_type]
        if not any(_value_matches_type(value, str(type_name)) for type_name in expected_types):
            raise SchemaValidationError(f"{path}: value has unexpected type")
    if "pattern" in schema_node and isinstance(value, str):
        if re.fullmatch(str(schema_node["pattern"]), value) is None:
            raise SchemaValidationError(f"{path}: value does not match pattern")
    if "minLength" in schema_node and isinstance(value, str):
        if len(value) < int(schema_node["minLength"]):
            raise SchemaValidationError(f"{path}: value is shorter than minLength")
    if "maxLength" in schema_node and isinstance(value, str):
        if len(value) > int(schema_node["maxLength"]):
            raise SchemaValidationError(f"{path}: value exceeds maxLength")
    if "minimum" in schema_node and isinstance(value, int) and not isinstance(value, bool):
        if value < int(schema_node["minimum"]):
            raise SchemaValidationError(f"{path}: value is below minimum")
    if isinstance(value, dict):
        properties = schema_node.get("properties", {})
        if properties is not None and not isinstance(properties, dict):
            raise SchemaValidationError(f"{path}: properties must be an object")
        required = schema_node.get("required", [])
        if not isinstance(required, list):
            raise SchemaValidationError(f"{path}: required must be an array")
        missing = [field for field in required if field not in value]
        if missing:
            raise SchemaValidationError(f"{path}: missing required fields {missing}")
        if schema_node.get("additionalProperties") is False:
            extra = sorted(set(value).difference(properties))
            if extra:
                raise SchemaValidationError(f"{path}: unexpected fields {extra}")
        for key, child_schema in properties.items():
            if key in value:
                if not isinstance(child_schema, dict):
                    raise SchemaValidationError(f"{path}.{key}: schema must be an object")
                _validate_json_schema_node(value[key], child_schema, root, f"{path}.{key}")
    if isinstance(value, list):
        if "maxItems" in schema_node and len(value) > int(schema_node["maxItems"]):
            raise SchemaValidationError(f"{path}: array exceeds maxItems")
        if schema_node.get("uniqueItems") is True:
            canonical_items = [json.dumps(item, sort_keys=True) for item in value]
            if len(set(canonical_items)) != len(canonical_items):
                raise SchemaValidationError(f"{path}: array items are not unique")
        item_schema = schema_node.get("items")
        if item_schema is not None:
            if not isinstance(item_schema, dict):
                raise SchemaValidationError(f"{path}: items must be an object")
            for index, item in enumerate(value):
                _validate_json_schema_node(item, item_schema, root, f"{path}[{index}]")


def _json_schema_condition_matches(
    value: Any,
    schema_node: Any,
    root: dict[str, Any],
    path: str,
) -> bool:
    if not isinstance(schema_node, dict):
        raise SchemaValidationError(f"{path}: if schema must be an object")
    try:
        _validate_json_schema_node(value, schema_node, root, path)
    except SchemaValidationError:
        return False
    return True


def validate_json_schema_subset(value: Any, schema: dict[str, Any]) -> None:
    _validate_json_schema_node(value, schema, schema, "$")


def fatal(code: fix.FailureCode, message: str, operation: str) -> fix.FixProposalFailure:
    return fix.fatal(code, message, operation)


def sha256_hex_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_hex_json(value: Any) -> str:
    return fix.sha256_hex_json(value)


def canonical_json_bytes(value: Any) -> bytes:
    return fix.canonical_json_bytes(value)


def check_result(status: str, message: str) -> dict[str, str]:
    return preflight.check_result(status, message)


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
            f"sandbox apply request manifest field mismatch: missing={missing} extra={extra}",
            "sandbox_apply_request_validation",
        )
    if manifest["schema_version"] != REQUEST_SCHEMA_VERSION:
        raise fatal(
            fix.FailureCode.INVALID_MANIFEST,
            "unsupported sandbox apply request manifest schema",
            "sandbox_apply_request_validation",
        )
    if manifest["request_stage"] != REQUEST_STAGE:
        raise fatal(
            fix.FailureCode.TRUST_BOUNDARY_VIOLATION,
            "sandbox apply request came from an unexpected stage",
            "sandbox_apply_request_validation",
        )
    if manifest["collector_workflow_name"] != COLLECTOR_WORKFLOW_NAME:
        raise fatal(
            fix.FailureCode.TRUST_BOUNDARY_VIOLATION,
            "sandbox apply request came from an unexpected collector workflow",
            "sandbox_apply_request_validation",
        )
    if manifest["repository"] != EXPECTED_REPOSITORY:
        raise fatal(
            fix.FailureCode.REPOSITORY_MISMATCH,
            "sandbox apply request repository mismatch",
            "sandbox_apply_request_validation",
        )
    if not isinstance(manifest["pull_request_number"], int):
        raise fatal(
            fix.FailureCode.PR_MISMATCH,
            "pull_request_number must be an integer",
            "sandbox_apply_request_validation",
        )
    preflight.ensure_full_sha(manifest["base_sha"], "base_sha")
    preflight.ensure_full_sha(manifest["head_sha"], "head_sha")
    if not isinstance(manifest["labels"], list):
        raise fatal(
            fix.FailureCode.INVALID_MANIFEST,
            "labels must be an array",
            "sandbox_apply_request_validation",
        )
    if manifest["event_action"] != "labeled" or manifest["event_label"] != APPLY_LABEL:
        raise fatal(
            fix.FailureCode.LABEL_MISSING,
            "sandbox apply requires the ai-fix-apply-sandbox label event",
            "sandbox_apply_request_validation",
        )
    if manifest["event_name"] != "pull_request":
        raise fatal(
            fix.FailureCode.INVALID_MANIFEST,
            "sandbox apply request must come from pull_request",
            "sandbox_apply_request_validation",
        )
    if not preflight.DATE_TIME_RE.fullmatch(str(manifest["requested_at"])):
        raise fatal(
            fix.FailureCode.INVALID_MANIFEST,
            "requested_at must be an ISO-8601 timestamp",
            "sandbox_apply_request_validation",
        )


def labels_from_request(manifest: dict[str, Any]) -> set[str]:
    return preflight.labels_from_request(manifest)


def validate_live_apply_gate(
    *,
    manifest: dict[str, Any],
    live_pull: dict[str, Any],
    live_issue: dict[str, Any],
    policy: fix.FixProposalPolicy,
    apply_actor: str,
    apply_actor_permission: str,
) -> set[str]:
    validate_request_manifest_shape(manifest)
    live_labels = approval.labels_from_pull_or_issue(live_issue)
    required_labels = {
        policy.proposal_policy.proposal_label,
        policy.proposal_policy.approval_label,
        preflight.VALIDATE_LABEL,
        APPLY_LABEL,
    }
    if apply_actor != str(manifest["actor"]):
        raise fatal(
            fix.FailureCode.TRUST_BOUNDARY_VIOLATION,
            "apply actor mismatch between workflow_run and request artifact",
            "sandbox_apply_live_gate",
        )
    if bool(manifest.get("draft")) or bool(live_pull.get("draft")):
        raise fatal(
            fix.FailureCode.DRAFT_PULL_REQUEST,
            "draft pull requests cannot run sandbox apply",
            "sandbox_apply_live_gate",
        )
    if str(live_pull.get("state", "")) != "open":
        raise ApplyStatus(
            RESULT_STATUS_STALE,
            "PR_NOT_OPEN",
            "pull request is no longer open",
        )
    if manifest.get("base_repository") != EXPECTED_REPOSITORY:
        raise fatal(
            fix.FailureCode.REPOSITORY_MISMATCH,
            "base repository mismatch",
            "sandbox_apply_live_gate",
        )
    if manifest.get("head_repository") != EXPECTED_REPOSITORY:
        raise fatal(
            fix.FailureCode.FORK_PULL_REQUEST,
            "fork pull requests cannot run sandbox apply",
            "sandbox_apply_live_gate",
        )
    missing = sorted(required_labels.difference(live_labels))
    if missing:
        raise fatal(
            fix.FailureCode.LABEL_MISSING,
            f"live pull request is missing labels: {missing}",
            "sandbox_apply_live_gate",
        )
    request_labels = labels_from_request(manifest)
    if APPLY_LABEL not in request_labels:
        raise fatal(
            fix.FailureCode.LABEL_MISSING,
            "request artifact does not contain ai-fix-apply-sandbox",
            "sandbox_apply_live_gate",
        )
    live_head_sha = str(live_pull.get("head", {}).get("sha", ""))
    live_base_sha = str(live_pull.get("base", {}).get("sha", ""))
    if live_head_sha != manifest["head_sha"]:
        raise ApplyStatus(
            RESULT_STATUS_STALE,
            "REQUEST_HEAD_STALE",
            "live pull request head SHA changed after apply request collection",
        )
    if live_base_sha != manifest["base_sha"]:
        raise ApplyStatus(
            RESULT_STATUS_STALE,
            "REQUEST_BASE_STALE",
            "live pull request base SHA changed after apply request collection",
        )
    if int(live_pull.get("number", 0)) != int(manifest["pull_request_number"]):
        raise fatal(
            fix.FailureCode.PR_MISMATCH,
            "live pull request number mismatch",
            "sandbox_apply_live_gate",
        )
    if str(live_pull.get("user", {}).get("type", "")).lower() == "bot":
        raise fatal(
            fix.FailureCode.BOT_PULL_REQUEST,
            "bot pull requests cannot run sandbox apply",
            "sandbox_apply_live_gate",
        )
    if apply_actor_permission not in ALLOWED_REPOSITORY_PERMISSIONS:
        raise fatal(
            fix.FailureCode.UNAUTHORIZED_ASSOCIATION,
            "sandbox apply actor must have repository admin or maintain permission",
            "sandbox_apply_live_gate",
        )
    return live_labels


def preflight_result_targets_apply_request(
    *,
    result: dict[str, Any],
    manifest: dict[str, Any],
    proposal_bundle: preflight.ArtifactBundle,
    approval_bundle: preflight.ApprovalBundle,
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
    )


def _is_unsafe_zip_member_name(name: str) -> bool:
    if not name:
        return True
    if "\x00" in name or "\\" in name:
        return True
    if name.startswith("/") or name.startswith("../") or "/../" in name:
        return True
    if re.match(r"^[A-Za-z]:", name) is not None or name.startswith("//"):
        return True
    if "/" in name:
        return True
    for character in name:
        category = unicodedata.category(character)
        if category in {"Cc", "Cf"}:
            return True
    if name.lower().endswith(".zip"):
        return True
    return False


def safe_extract_canonical_preflight_zip(
    zip_bytes: bytes,
    target_dir: Path,
    *,
    max_bytes: int,
) -> None:
    if len(zip_bytes) > max_bytes:
        raise fix.retryable(
            fix.FailureCode.ARTIFACT_TRANSIENT_ERROR,
            "downloaded preflight artifact zip exceeds configured maximum",
            "artifact_download",
        )
    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    root = target_dir.resolve()
    seen: set[str] = set()
    normalized_seen: set[str] = set()
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        for member in archive.infolist():
            name = member.filename
            if member.is_dir():
                raise fatal(
                    fix.FailureCode.INVALID_MANIFEST,
                    "preflight artifact directory entries are not allowed",
                    "artifact_download",
                )
            if _is_unsafe_zip_member_name(name):
                raise fatal(
                    fix.FailureCode.INVALID_MANIFEST,
                    f"unsafe preflight artifact member: {name}",
                    "artifact_download",
                )
            normalized_name = unicodedata.normalize("NFC", name).casefold()
            if name in seen or normalized_name in normalized_seen:
                raise fatal(
                    fix.FailureCode.INVALID_MANIFEST,
                    f"duplicate preflight artifact member: {name}",
                    "artifact_download",
                )
            seen.add(name)
            normalized_seen.add(normalized_name)
            mode = member.external_attr >> 16
            file_type = stat.S_IFMT(mode)
            if file_type and not stat.S_ISREG(mode):
                raise fatal(
                    fix.FailureCode.INVALID_MANIFEST,
                    f"unsupported preflight artifact member type: {name}",
                    "artifact_download",
                )
            if name not in PREFLIGHT_ARTIFACT_MEMBERS:
                raise fatal(
                    fix.FailureCode.INVALID_MANIFEST,
                    f"unexpected preflight artifact member: {name}",
                    "artifact_download",
                )
            if member.file_size > max_bytes:
                raise fatal(
                    fix.FailureCode.INVALID_MANIFEST,
                    "preflight artifact member exceeds configured maximum",
                    "artifact_download",
                )
            destination = (target_dir / name).resolve()
            if root != destination and root not in destination.parents:
                raise fatal(
                    fix.FailureCode.PATH_TRAVERSAL,
                    "preflight artifact path traversal detected",
                    "artifact_download",
                )
            with archive.open(member) as source, destination.open("wb") as output:
                output.write(source.read())
    if seen != set(PREFLIGHT_ARTIFACT_MEMBERS):
        missing = sorted(set(PREFLIGHT_ARTIFACT_MEMBERS).difference(seen))
        extra = sorted(seen.difference(PREFLIGHT_ARTIFACT_MEMBERS))
        raise fatal(
            fix.FailureCode.INVALID_MANIFEST,
            f"preflight artifact member set mismatch: missing={missing} extra={extra}",
            "artifact_download",
        )


def download_preflight_artifact_by_name(
    *,
    repo: str,
    token: str,
    run_id: str,
    artifact_name: str,
    target_dir: Path,
    max_bytes: int,
) -> int:
    listing, _ = stage1.github_json(
        "GET",
        f"/repos/{repo}/actions/runs/{run_id}/artifacts?per_page=100",
        token=token,
    )
    artifacts = listing.get("artifacts", []) if isinstance(listing, dict) else []
    matching = [artifact for artifact in artifacts if artifact.get("name") == artifact_name]
    if not matching:
        raise fix.retryable(
            fix.FailureCode.ARTIFACT_TRANSIENT_ERROR,
            f"preflight artifact {artifact_name} was not available yet",
            "artifact_download",
        )
    artifact_id = int(matching[0]["id"])
    data, _ = stage1.github_api_request(
        "GET",
        f"/repos/{repo}/actions/artifacts/{artifact_id}/zip",
        token=token,
        max_response_bytes=max_bytes,
    )
    safe_extract_canonical_preflight_zip(
        data,
        target_dir,
        max_bytes=max_bytes,
    )
    return artifact_id


def _require_dict(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise fatal(
            fix.FailureCode.INVALID_MANIFEST,
            f"{name} must be a JSON object",
            "sandbox_preflight_lookup",
        )
    return value


def _require_list(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise fatal(
            fix.FailureCode.INVALID_MANIFEST,
            f"{name} must be a JSON array",
            "sandbox_preflight_lookup",
        )
    return value


def validate_preflight_sidecars(
    *,
    result: dict[str, Any],
    proposal_manifest: dict[str, Any],
    approval_manifest: dict[str, Any],
    target_blob_checks: list[Any],
    patch_metadata_check: dict[str, Any],
    manifest: dict[str, Any],
    proposal_bundle: preflight.ArtifactBundle,
    approval_bundle: preflight.ApprovalBundle,
    policy_hash: str,
) -> None:
    validate_preflight_result(
        result=result,
        manifest=manifest,
        proposal_bundle=proposal_bundle,
        approval_bundle=approval_bundle,
        policy_hash=policy_hash,
    )
    expected_files = expected_change_paths(proposal_bundle.data)
    if result.get("expected_files") != expected_files:
        raise fatal(
            fix.FailureCode.TRUST_BOUNDARY_VIOLATION,
            "preflight expected files do not match proposal changes",
            "sandbox_preflight_lookup",
        )
    proposal_artifact = _require_dict(result.get("proposal_artifact"), "proposal_artifact")
    approval_artifact = _require_dict(result.get("approval_artifact"), "approval_artifact")
    expected_proposal_manifest = {
        "artifact_id": proposal_bundle.artifact_id,
        "artifact_name": proposal_bundle.artifact_name,
        "workflow_run_id": proposal_bundle.workflow_run_id,
        "proposal_id": proposal_bundle.metadata.get("proposal_id"),
        "proposal_hash": proposal_bundle.metadata.get("proposal_hash"),
        "head_sha": proposal_bundle.metadata.get("head_sha"),
    }
    expected_approval_manifest = {
        "artifact_id": approval_bundle.artifact_id,
        "artifact_name": approval_bundle.artifact_name,
        "workflow_run_id": approval_bundle.workflow_run_id,
        "approval_id": approval_bundle.record.get("approval_id"),
        "approval_record_hash": approval_bundle.record.get("approval_record_hash"),
        "head_sha": approval_bundle.record.get("head_sha"),
    }
    if proposal_manifest != expected_proposal_manifest:
        raise fatal(
            fix.FailureCode.TRUST_BOUNDARY_VIOLATION,
            "selected proposal sidecar does not match selected proposal artifact",
            "sandbox_preflight_lookup",
        )
    if approval_manifest != expected_approval_manifest:
        raise fatal(
            fix.FailureCode.TRUST_BOUNDARY_VIOLATION,
            "selected approval sidecar does not match selected approval artifact",
            "sandbox_preflight_lookup",
        )
    for key in ("artifact_id", "artifact_name", "workflow_run_id", "head_sha"):
        if proposal_artifact.get(key) != proposal_manifest.get(key):
            raise fatal(
                fix.FailureCode.TRUST_BOUNDARY_VIOLATION,
                f"preflight proposal artifact reference mismatch for {key}",
                "sandbox_preflight_lookup",
            )
        if approval_artifact.get(key) != approval_manifest.get(key):
            raise fatal(
                fix.FailureCode.TRUST_BOUNDARY_VIOLATION,
                f"preflight approval artifact reference mismatch for {key}",
                "sandbox_preflight_lookup",
            )
    for artifact_ref in (proposal_artifact, approval_artifact):
        if artifact_ref.get("repository") != manifest["repository"]:
            raise fatal(
                fix.FailureCode.REPOSITORY_MISMATCH,
                "preflight artifact repository reference mismatch",
                "sandbox_preflight_lookup",
            )
        if artifact_ref.get("pull_request_number") != manifest["pull_request_number"]:
            raise fatal(
                fix.FailureCode.PR_MISMATCH,
                "preflight artifact PR reference mismatch",
                "sandbox_preflight_lookup",
            )
    if proposal_artifact.get("workflow_name") != fix.GENERATOR_WORKFLOW_NAME:
        raise fatal(
            fix.FailureCode.TRUST_BOUNDARY_VIOLATION,
            "preflight proposal artifact workflow mismatch",
            "sandbox_preflight_lookup",
        )
    if approval_artifact.get("workflow_name") != approval.RECORDER_WORKFLOW_NAME:
        raise fatal(
            fix.FailureCode.TRUST_BOUNDARY_VIOLATION,
            "preflight approval artifact workflow mismatch",
            "sandbox_preflight_lookup",
        )
    result_blob_checks = _require_list(
        result.get("target_blob_checks"),
        "target_blob_checks",
    )
    if target_blob_checks != result_blob_checks:
        raise fatal(
            fix.FailureCode.TRUST_BOUNDARY_VIOLATION,
            "target blob sidecar does not match preflight result",
            "sandbox_preflight_lookup",
        )
    check_paths = [str(entry.get("path", "")) for entry in target_blob_checks if isinstance(entry, dict)]
    if check_paths != expected_files or len(check_paths) != len(target_blob_checks):
        raise fatal(
            fix.FailureCode.TRUST_BOUNDARY_VIOLATION,
            "target blob sidecar paths do not match expected files",
            "sandbox_preflight_lookup",
        )
    blob_by_path = {
        str(change["path"]): str(change["original_blob_sha"])
        for change in proposal_bundle.data.get("changes", [])
    }
    for entry in target_blob_checks:
        item = _require_dict(entry, "target_blob_check")
        path = str(item.get("path", ""))
        if item.get("status") != "PASS":
            raise fatal(
                fix.FailureCode.TRUST_BOUNDARY_VIOLATION,
                "target blob sidecar contains a non-PASS status",
                "sandbox_preflight_lookup",
            )
        if item.get("file_type") != "blob" or str(item.get("mode", "")) not in {"100644", "100755"}:
            raise fatal(
                fix.FailureCode.TRUST_BOUNDARY_VIOLATION,
                "target blob sidecar contains unsupported file metadata",
                "sandbox_preflight_lookup",
            )
        if item.get("expected_blob_sha") != item.get("actual_blob_sha"):
            raise fatal(
                fix.FailureCode.TRUST_BOUNDARY_VIOLATION,
                "target blob sidecar expected and actual SHAs differ",
                "sandbox_preflight_lookup",
            )
        if item.get("expected_blob_sha") != blob_by_path.get(path):
            raise fatal(
                fix.FailureCode.TRUST_BOUNDARY_VIOLATION,
                "target blob sidecar SHA does not match proposal original blob",
                "sandbox_preflight_lookup",
            )
    result_patch_metadata = _require_dict(
        result.get("patch_metadata_check"),
        "patch_metadata_check",
    )
    if patch_metadata_check.get("status") != "PASS":
        raise fatal(
            fix.FailureCode.TRUST_BOUNDARY_VIOLATION,
            "patch metadata sidecar is not PASS",
            "sandbox_preflight_lookup",
        )
    if result_patch_metadata.get("status") != "PASS":
        raise fatal(
            fix.FailureCode.TRUST_BOUNDARY_VIOLATION,
            "preflight result patch metadata is not PASS",
            "sandbox_preflight_lookup",
        )
    if patch_metadata_check.get("expected_files") != expected_files:
        raise fatal(
            fix.FailureCode.TRUST_BOUNDARY_VIOLATION,
            "patch metadata sidecar files do not match expected files",
            "sandbox_preflight_lookup",
        )
    patch_bytes = len(combined_patch_text(proposal_bundle.data).encode("utf-8"))
    if patch_metadata_check.get("patch_bytes") != patch_bytes:
        raise fatal(
            fix.FailureCode.TRUST_BOUNDARY_VIOLATION,
            "patch metadata sidecar byte count does not match proposal patch",
            "sandbox_preflight_lookup",
        )
    for key in ("status", "message", "patch_bytes"):
        if result_patch_metadata.get(key) != patch_metadata_check.get(key):
            raise fatal(
                fix.FailureCode.TRUST_BOUNDARY_VIOLATION,
                f"patch metadata sidecar mismatch for {key}",
                "sandbox_preflight_lookup",
            )
    for check_name in ("protected_path_check", "blob_sha_check"):
        check = _require_dict(result.get(check_name), check_name)
        if check.get("status") != "PASS":
            raise fatal(
                fix.FailureCode.TRUST_BOUNDARY_VIOLATION,
                f"{check_name} is not PASS",
                "sandbox_preflight_lookup",
            )


def validate_preflight_result(
    *,
    result: dict[str, Any],
    manifest: dict[str, Any],
    proposal_bundle: preflight.ArtifactBundle,
    approval_bundle: preflight.ApprovalBundle,
    policy_hash: str,
) -> None:
    if not preflight_result_targets_apply_request(
        result=result,
        manifest=manifest,
        proposal_bundle=proposal_bundle,
        approval_bundle=approval_bundle,
    ):
        raise fatal(
            fix.FailureCode.TRUST_BOUNDARY_VIOLATION,
            "preflight result identity does not match apply request",
            "sandbox_preflight_lookup",
        )
    expected = {
        "phase": preflight.RESULT_PHASE_PREFLIGHT,
        "status": preflight.RESULT_STATUS_PRECHECK_PASSED,
        "policy_hash": policy_hash,
        "persistent_repository_modified": False,
        "sandbox_checkout_performed": False,
        "patch_applied": False,
        "test_execution_performed": False,
        "commit_created": False,
        "push_performed": False,
        "merge_performed": False,
    }
    for key, value in expected.items():
        if result.get(key) != value:
            raise fatal(
                fix.FailureCode.TRUST_BOUNDARY_VIOLATION,
                f"preflight result requires {key}={value!r}",
                "sandbox_preflight_lookup",
            )
    if result.get("validation_id") is None:
        raise fatal(
            fix.FailureCode.INVALID_PROPOSAL,
            "preflight result must contain a validation ID",
            "sandbox_preflight_lookup",
        )


def find_latest_preflight_artifact(
    *,
    repo: str,
    token: str,
    manifest: dict[str, Any],
    proposal_bundle: preflight.ArtifactBundle,
    approval_bundle: preflight.ApprovalBundle,
    policy_hash: str,
    output_dir: Path,
    max_bytes: int,
) -> PreflightBundle:
    runs_data, _ = stage1.github_json(
        "GET",
        f"/repos/{repo}/actions/workflows/fix-sandbox.yml/runs?status=completed&per_page=50",
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
        artifacts = (
            artifacts_data.get("artifacts", [])
            if isinstance(artifacts_data, dict)
            else []
        )
        for artifact in artifacts:
            name = str(artifact.get("name", ""))
            if not name.startswith("sandbox-validation-preflight-"):
                continue
            try:
                artifact_id = download_preflight_artifact_by_name(
                    repo=repo,
                    token=token,
                    run_id=str(run_id),
                    artifact_name=name,
                    target_dir=output_dir,
                    max_bytes=max_bytes,
                )
            except BaseException as error:
                if preflight.is_unavailable_artifact_candidate(error):
                    continue
                raise
            result = read_json_file(output_dir / "sandbox-validation-result.json")
            proposal_manifest = read_json_file(
                output_dir / "selected-proposal-manifest.json"
            )
            approval_manifest = read_json_file(
                output_dir / "selected-approval-manifest.json"
            )
            target_blob_checks = read_json_file(output_dir / "target-blob-checks.json")
            patch_metadata_check = read_json_file(output_dir / "patch-metadata-check.json")
            result = _require_dict(result, "sandbox-validation-result.json")
            proposal_manifest = _require_dict(
                proposal_manifest,
                "selected-proposal-manifest.json",
            )
            approval_manifest = _require_dict(
                approval_manifest,
                "selected-approval-manifest.json",
            )
            target_blob_checks = _require_list(
                target_blob_checks,
                "target-blob-checks.json",
            )
            patch_metadata_check = _require_dict(
                patch_metadata_check,
                "patch-metadata-check.json",
            )
            validate_preflight_sidecars(
                result=result,
                proposal_manifest=proposal_manifest,
                approval_manifest=approval_manifest,
                target_blob_checks=target_blob_checks,
                patch_metadata_check=patch_metadata_check,
                manifest=manifest,
                proposal_bundle=proposal_bundle,
                approval_bundle=approval_bundle,
                policy_hash=policy_hash,
            )
            return PreflightBundle(
                result=result,
                result_hash=sha256_hex_json(result),
                artifact_id=artifact_id,
                artifact_name=name,
                workflow_run_id=run_id,
                workflow_name=preflight.VALIDATOR_WORKFLOW_NAME,
            )
    raise fatal(
        fix.FailureCode.PROPOSAL_ARTIFACT_NOT_FOUND,
        "NOT_FOUND: no verified preflight result artifact was found",
        "sandbox_preflight_lookup",
    )


def combined_patch_text(proposal: dict[str, Any]) -> str:
    patches: list[str] = []
    for change in proposal.get("changes", []):
        patch = str(change.get("patch", ""))
        patches.append(patch.rstrip("\n"))
    return "\n".join(patches) + "\n"


def expected_change_paths(proposal: dict[str, Any]) -> list[str]:
    return [str(change["path"]) for change in proposal.get("changes", [])]


def planned_test_ids_from_preflight(result: dict[str, Any]) -> tuple[str, ...]:
    tests = result.get("tests_requested", [])
    ids = [
        str(item.get("test_id"))
        for item in tests
        if isinstance(item, dict) and item.get("requested") is True
    ]
    return tuple(dict.fromkeys(ids))


def test_evidence_b1(test_id: str) -> dict[str, Any]:
    return {
        "test_id": test_id,
        "requested": True,
        "executed": False,
        "status": "SKIPPED",
        "exit_code": None,
        "duration_ms": 0,
        "log_excerpt": "Stage 2C-B1 records planned tests but does not execute tests.",
    }


def apply_id_for(
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
    apply_request_actor: str,
    policy_hash: str,
    test_plan_hash: str,
    patch_file_hash: str,
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
            "apply_request_actor": apply_request_actor,
            "policy_hash": policy_hash,
            "phase": RESULT_PHASE_SANDBOX_APPLY,
            "test_plan_hash": test_plan_hash,
            "patch_file_hash": patch_file_hash,
        }
    )[:32]


def build_apply_context(
    *,
    manifest: dict[str, Any],
    proposal_bundle: preflight.ArtifactBundle,
    approval_bundle: preflight.ApprovalBundle,
    preflight_bundle: PreflightBundle,
    apply_actor: str,
    apply_actor_permission: str,
    apply_actor_role: str | None,
    validation_actor_permission: str,
    validation_actor_role: str | None,
    approval_actor_permission: str,
    approval_actor_role: str | None,
    live_labels: Iterable[str],
) -> dict[str, Any]:
    proposal = proposal_bundle.data
    metadata = proposal_bundle.metadata
    record = approval_bundle.record
    precheck = preflight_bundle.result
    patch_text = combined_patch_text(proposal)
    patch_hash = sha256_hex_bytes(patch_text.encode("utf-8"))
    planned_test_ids = planned_test_ids_from_preflight(precheck)
    test_plan_hash = precheck.get(
        "test_plan_hash",
        sha256_hex_json({"phase": RESULT_PHASE_SANDBOX_APPLY, "test_ids": planned_test_ids}),
    )
    apply_id = apply_id_for(
        repository=manifest["repository"],
        pull_request_number=int(manifest["pull_request_number"]),
        head_sha=manifest["head_sha"],
        proposal_id=str(metadata["proposal_id"]),
        proposal_hash=str(metadata["proposal_hash"]),
        approval_id=str(record["approval_id"]),
        approval_record_hash=str(record["approval_record_hash"]),
        preflight_validation_id=str(precheck["validation_id"]),
        preflight_result_hash=preflight_bundle.result_hash,
        apply_request_actor=apply_actor,
        policy_hash=str(metadata["policy_hash"]),
        test_plan_hash=str(test_plan_hash),
        patch_file_hash=patch_hash,
    )
    return {
        "schema_version": "sandbox-apply-context-v1",
        "apply_id": apply_id,
        "manifest": manifest,
        "proposal": proposal,
        "proposal_metadata": metadata,
        "approval_record": record,
        "preflight_result": precheck,
        "preflight_result_hash": preflight_bundle.result_hash,
        "preflight_artifact": preflight.artifact_provenance(
            artifact_id=preflight_bundle.artifact_id,
            artifact_name=preflight_bundle.artifact_name,
            workflow_run_id=preflight_bundle.workflow_run_id,
            workflow_name=preflight_bundle.workflow_name,
            repository=manifest["repository"],
            pull_request_number=int(manifest["pull_request_number"]),
            head_sha=str(precheck["head_sha"]),
        ),
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
        "apply_request_actor": apply_actor,
        "apply_request_actor_repository_permission": apply_actor_permission,
        "apply_request_actor_repository_role": apply_actor_role,
        "validation_request_actor": str(precheck["validation_request_actor"]),
        "validation_request_actor_repository_permission": validation_actor_permission,
        "validation_request_actor_repository_role": validation_actor_role,
        "approved_by_repository_permission": approval_actor_permission,
        "approved_by_repository_role": approval_actor_role,
        "live_labels": sorted(set(str(label) for label in live_labels)),
        "expected_files": expected_change_paths(proposal),
        "patch_text": patch_text,
        "patch_file_hash": patch_hash,
        "planned_test_ids": list(planned_test_ids),
        "test_plan_hash": str(test_plan_hash),
        "started_at": now_utc(),
    }


def run_git(
    worktree: Path,
    args: Iterable[str],
    *,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    argv = list(args)
    if not argv or argv[0] != "git":
        raise ApplyStatus(RESULT_STATUS_FATAL, "UNSAFE_GIT_ARGV", "git argv is not fixed")
    completed = subprocess.run(
        argv,
        cwd=worktree,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if check and completed.returncode != 0:
        raise ApplyStatus(
            RESULT_STATUS_PATCH_REJECTED,
            "GIT_COMMAND_FAILED",
            (completed.stderr or completed.stdout).strip()[:800],
        )
    return completed


def ensure_clean_worktree(worktree: Path, code: str = "DIRTY_WORKTREE") -> None:
    status = run_git(
        worktree,
        ("git", "status", "--porcelain=v1", "-z"),
    ).stdout
    if status:
        raise ApplyStatus(
            RESULT_STATUS_PATCH_REJECTED,
            code,
            "sandbox working tree is not clean",
        )


def verify_checkout(worktree: Path, expected_sha: str) -> dict[str, Any]:
    head = run_git(worktree, ("git", "rev-parse", "HEAD")).stdout.strip()
    if head != expected_sha:
        raise ApplyStatus(
            RESULT_STATUS_STALE,
            "CHECKOUT_SHA_MISMATCH",
            "sandbox checkout HEAD does not match expected SHA",
        )
    branch = run_git(worktree, ("git", "branch", "--show-current")).stdout.strip()
    if branch:
        raise ApplyStatus(
            RESULT_STATUS_FATAL,
            "NOT_DETACHED_HEAD",
            "sandbox checkout is not detached",
        )
    ensure_clean_worktree(worktree, "DIRTY_INITIAL_TREE")
    remote_url = run_git(
        worktree,
        ("git", "config", "--get", "remote.origin.url"),
        check=False,
    ).stdout.strip()
    if "@" in remote_url.split("github.com", 1)[0] or "://" in remote_url and "@" in remote_url:
        raise ApplyStatus(
            RESULT_STATUS_FATAL,
            "CREDENTIAL_PERSISTED",
            "remote URL contains embedded credentials",
        )
    extra_header = run_git(
        worktree,
        ("git", "config", "--get-regexp", r"http\..*\.extraheader"),
        check=False,
    )
    if extra_header.returncode == 0 and extra_header.stdout.strip():
        raise ApplyStatus(
            RESULT_STATUS_FATAL,
            "CREDENTIAL_PERSISTED",
            "checkout persisted HTTP authorization headers",
        )
    run_git(worktree, ("git", "remote", "remove", "origin"), check=False)
    return {
        "status": "PASS",
        "head_sha": head,
        "detached_head": True,
        "clean": True,
        "credentials_persisted": False,
        "remote_removed": True,
    }


def materialize_patch(context: dict[str, Any], patch_path: Path) -> str:
    patch_text = str(context["patch_text"])
    patch_path.parent.mkdir(parents=True, exist_ok=True)
    patch_path.write_text(patch_text, encoding="utf-8", newline="\n")
    patch_hash = sha256_hex_bytes(patch_path.read_bytes())
    if patch_hash != context["patch_file_hash"]:
        raise ApplyStatus(
            RESULT_STATUS_FATAL,
            "PATCH_HASH_MISMATCH",
            "materialized patch hash does not match apply context",
        )
    return patch_hash


def patch_line_stats(patch_text: str) -> dict[str, dict[str, int]]:
    stats: dict[str, dict[str, int]] = {}
    current_path: str | None = None
    for line in patch_text.splitlines():
        if line.startswith("diff --git "):
            match = preflight.DIFF_GIT_RE.fullmatch(line)
            current_path = match.group(2) if match else None
            if current_path:
                stats.setdefault(current_path, {"additions": 0, "deletions": 0})
            continue
        if current_path is None:
            continue
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            stats[current_path]["additions"] += 1
        elif line.startswith("-"):
            stats[current_path]["deletions"] += 1
    return stats


def parse_status_z(raw: str) -> list[dict[str, str]]:
    parts = [part for part in raw.split("\0") if part]
    entries: list[dict[str, str]] = []
    for part in parts:
        status = part[:2]
        path = part[3:]
        entries.append({"status": status, "path": path})
    return entries


def parse_name_status_z(raw: str) -> list[dict[str, str]]:
    parts = [part for part in raw.split("\0") if part]
    entries: list[dict[str, str]] = []
    i = 0
    while i < len(parts):
        status = parts[i]
        path = parts[i + 1] if i + 1 < len(parts) else ""
        entries.append({"status": status, "path": path})
        i += 2
    return entries


def parse_numstat(raw: str) -> dict[str, dict[str, int]]:
    stats: dict[str, dict[str, int]] = {}
    for line in raw.splitlines():
        if not line:
            continue
        added, deleted, path = line.split("\t", 2)
        if not added.isdigit() or not deleted.isdigit():
            raise ApplyStatus(
                RESULT_STATUS_PATCH_REJECTED,
                "BINARY_DIFF",
                "binary diff is not supported",
            )
        stats[path] = {
            "additions": int(added),
            "deletions": int(deleted),
        }
    return stats


def resulting_file_hashes(worktree: Path, paths: Iterable[str]) -> list[dict[str, str]]:
    hashes: list[dict[str, str]] = []
    for path in paths:
        digest = run_git(worktree, ("git", "hash-object", "--", path)).stdout.strip()
        hashes.append({"path": path, "resulting_blob_sha": digest})
    return hashes


def verify_changed_files(
    *,
    worktree: Path,
    context: dict[str, Any],
) -> tuple[list[str], dict[str, Any], list[dict[str, str]]]:
    expected = sorted(str(path) for path in context["expected_files"])
    status_entries = parse_status_z(
        run_git(worktree, ("git", "status", "--porcelain=v1", "-z")).stdout
    )
    if not status_entries:
        raise ApplyStatus(
            RESULT_STATUS_PATCH_REJECTED,
            "NO_CHANGES",
            "patch apply produced no changed files",
        )
    for entry in status_entries:
        status = entry["status"]
        if status != " M":
            raise ApplyStatus(
                RESULT_STATUS_PATCH_REJECTED,
                "UNEXPECTED_CHANGE_STATUS",
                f"unsupported working tree status {status!r} for {entry['path']}",
            )
    actual = sorted(entry["path"] for entry in status_entries)
    if actual != expected:
        raise ApplyStatus(
            RESULT_STATUS_PATCH_REJECTED,
            "UNEXPECTED_CHANGED_FILE",
            f"changed files {actual} do not match expected {expected}",
        )
    name_status = parse_name_status_z(
        run_git(worktree, ("git", "diff", "--name-status", "-z")).stdout
    )
    for entry in name_status:
        if entry["status"] != "M":
            raise ApplyStatus(
                RESULT_STATUS_PATCH_REJECTED,
                "UNSUPPORTED_DIFF_OPERATION",
                f"unsupported diff operation {entry['status']}",
            )
    run_git(worktree, ("git", "diff", "--check"))
    numstat = parse_numstat(run_git(worktree, ("git", "diff", "--numstat")).stdout)
    expected_stats = patch_line_stats(str(context["patch_text"]))
    if numstat != expected_stats:
        raise ApplyStatus(
            RESULT_STATUS_PATCH_REJECTED,
            "DIFF_BINDING_MISMATCH",
            "applied diff line counts do not match proposal patch",
        )
    hashes = resulting_file_hashes(worktree, actual)
    diff_binding = {
        "status": "PASS",
        "expected_paths": expected,
        "actual_paths": actual,
        "numstat": numstat,
        "patch_line_stats": expected_stats,
        "message": "applied diff paths and line counts match proposal patch",
    }
    return actual, diff_binding, hashes


def cleanup_paths(paths: Iterable[Path]) -> dict[str, Any]:
    removed: list[str] = []
    errors: list[str] = []
    for path in paths:
        try:
            if path.is_dir():
                def retry_remove(func: Any, failing_path: str, _: Any) -> None:
                    try:
                        os.chmod(failing_path, stat.S_IWRITE)
                        func(failing_path)
                    except OSError as exc:
                        errors.append(f"{failing_path}: {exc}")

                shutil.rmtree(path, onerror=retry_remove)
                removed.append(str(path))
            elif path.exists():
                path.unlink()
                removed.append(str(path))
        except OSError as exc:
            errors.append(f"{path}: {exc}")
    if errors:
        return check_result(
            "FAIL",
            f"cleanup failed for {len(errors)} path(s): {'; '.join(errors)[:1500]}",
        )
    return check_result("PASS", f"removed {len(removed)} temporary path(s)")


def changed_paths_best_effort(worktree: Path) -> list[str]:
    try:
        status_entries = parse_status_z(
            run_git(worktree, ("git", "status", "--porcelain=v1", "-z")).stdout
        )
    except ApplyStatus:
        return []
    return sorted(entry["path"] for entry in status_entries)


def base_apply_result(
    *,
    context: dict[str, Any],
    status: str,
    failure_class: str | None,
    failure_code: str | None,
    completed_at: str | None = None,
) -> dict[str, Any]:
    manifest = context["manifest"]
    proposal = context["proposal"]
    metadata = context["proposal_metadata"]
    record = context["approval_record"]
    precheck = context["preflight_result"]
    tests_requested = [
        test_evidence_b1(test_id)
        for test_id in context.get("planned_test_ids", [])
    ]
    completed = completed_at or now_utc()
    return {
        "schema_version": preflight.RESULT_SCHEMA_VERSION,
        "validation_id": context["apply_id"],
        "phase": RESULT_PHASE_SANDBOX_APPLY,
        "repository": manifest["repository"],
        "pull_request_number": int(manifest["pull_request_number"]),
        "base_sha": manifest["base_sha"],
        "head_sha": manifest["head_sha"],
        "proposal_id": str(metadata["proposal_id"]),
        "proposal_hash": str(metadata["proposal_hash"]),
        "approval_id": str(record["approval_id"]),
        "approval_record_hash": str(record["approval_record_hash"]),
        "approved_by": str(record["approved_by"]),
        "approved_by_repository_permission": context["approved_by_repository_permission"],
        "approved_by_repository_role": context["approved_by_repository_role"],
        "validation_request_actor": context["validation_request_actor"],
        "validation_request_actor_repository_permission": context[
            "validation_request_actor_repository_permission"
        ],
        "validation_request_actor_repository_role": context[
            "validation_request_actor_repository_role"
        ],
        "live_labels": sorted(set(str(label) for label in context["live_labels"])),
        "proposal_artifact": context["proposal_artifact"],
        "approval_artifact": context["approval_artifact"],
        "schema_versions": {
            "proposal": str(proposal["schema_version"]),
            "approval": str(record["schema_version"]),
            "validation_result": preflight.RESULT_SCHEMA_VERSION,
        },
        "policy_hash": str(metadata["policy_hash"]),
        "test_plan_hash": context["test_plan_hash"],
        "started_at": context.get("started_at", completed),
        "completed_at": completed,
        "status": status,
        "failure_class": failure_class,
        "failure_code": failure_code,
        "patch_check": check_result("SKIPPED", "git apply --check has not run yet."),
        "patch_apply": check_result("SKIPPED", "patch apply has not run yet."),
        "expected_files": list(context["expected_files"]),
        "actual_changed_files": [],
        "protected_path_check": precheck["protected_path_check"],
        "blob_sha_check": precheck["blob_sha_check"],
        "target_blob_checks": precheck["target_blob_checks"],
        "patch_metadata_check": precheck["patch_metadata_check"],
        "tests_requested": tests_requested,
        "tests_executed": [],
        "test_results": [],
        "changed_files_match_expected": False,
        "persistent_repository_modified": False,
        "sandbox_worktree_modified": False,
        "sandbox_checkout_performed": False,
        "patch_check_performed": False,
        "patch_applied": False,
        "test_execution_performed": False,
        "commit_created": False,
        "push_performed": False,
        "merge_performed": False,
        "sandbox_destroyed": False,
        "apply_request_actor": context["apply_request_actor"],
        "apply_request_actor_repository_permission": context[
            "apply_request_actor_repository_permission"
        ],
        "apply_request_actor_repository_role": context[
            "apply_request_actor_repository_role"
        ],
        "preflight_validation_id": str(precheck["validation_id"]),
        "preflight_result_hash": context["preflight_result_hash"],
        "preflight_artifact": context["preflight_artifact"],
        "checkout_performed": False,
        "checkout_sha": None,
        "detached_head": False,
        "credentials_persisted": False,
        "patch_file_hash": context["patch_file_hash"],
        "git_apply_check": check_result("SKIPPED", "git apply --check not run."),
        "git_apply": check_result("SKIPPED", "git apply not run."),
        "expected_changed_files": list(context["expected_files"]),
        "resulting_file_hashes": [],
        "diff_binding": check_result("SKIPPED", "diff binding not evaluated."),
        "tests_planned": list(context.get("planned_test_ids", [])),
        "sandbox_cleanup": check_result("SKIPPED", "cleanup not yet run."),
    }


def validate_apply_result_against_schema(result: dict[str, Any], schema_path: Path) -> None:
    schema = read_json_file(schema_path)
    if not isinstance(schema, dict):
        raise fatal(
            fix.FailureCode.WORKFLOW_CONFIGURATION_ERROR,
            "sandbox result schema must be a JSON object",
            "sandbox_apply_result_schema",
        )
    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        raise fatal(
            fix.FailureCode.WORKFLOW_CONFIGURATION_ERROR,
            "sandbox result schema must declare properties",
            "sandbox_apply_result_schema",
        )
    try:
        validate_json_schema_subset(result, schema)
    except SchemaValidationError as exc:
        raise fatal(
            fix.FailureCode.INVALID_PROPOSAL,
            f"sandbox apply result does not match schema: {exc}",
            "sandbox_apply_result_schema",
        ) from exc
    extra = sorted(set(result).difference(properties))
    if extra:
        raise fatal(
            fix.FailureCode.INVALID_PROPOSAL,
            f"sandbox apply result contains unknown fields: {extra}",
            "sandbox_apply_result_schema",
        )
    if result.get("phase") != RESULT_PHASE_SANDBOX_APPLY:
        raise fatal(
            fix.FailureCode.INVALID_PROPOSAL,
            "sandbox apply result must use SANDBOX_APPLY phase",
            "sandbox_apply_result_schema",
        )
    if result.get("persistent_repository_modified") is not False:
        raise fatal(
            fix.FailureCode.INVALID_PROPOSAL,
            "sandbox apply must not persist repository changes",
            "sandbox_apply_result_schema",
        )
    for flag in ("commit_created", "push_performed", "merge_performed"):
        if result.get(flag) is not False:
            raise fatal(
                fix.FailureCode.INVALID_PROPOSAL,
                f"sandbox apply must keep {flag}=false",
                "sandbox_apply_result_schema",
            )
    if result.get("test_execution_performed") is not False:
        raise fatal(
            fix.FailureCode.INVALID_PROPOSAL,
            "Stage 2C-B1 must not execute tests",
            "sandbox_apply_result_schema",
        )
    if result.get("status") == RESULT_STATUS_APPLY_PASSED:
        expectations = {
            "failure_class": None,
            "failure_code": None,
            "checkout_performed": True,
            "sandbox_checkout_performed": True,
            "patch_check_performed": True,
            "patch_applied": True,
            "sandbox_destroyed": True,
            "changed_files_match_expected": True,
        }
        for key, expected in expectations.items():
            if result.get(key) != expected:
                raise fatal(
                    fix.FailureCode.INVALID_PROPOSAL,
                    f"APPLY_PASSED requires {key}={expected!r}",
                    "sandbox_apply_result_schema",
                )
        if result.get("tests_executed") or result.get("test_results"):
            raise fatal(
                fix.FailureCode.INVALID_PROPOSAL,
                "APPLY_PASSED must not include executed tests",
                "sandbox_apply_result_schema",
            )
    elif result.get("status") in {
        RESULT_STATUS_PATCH_REJECTED,
        RESULT_STATUS_STALE,
        RESULT_STATUS_FATAL,
        RESULT_STATUS_INFRA_ERROR,
    }:
        if result.get("failure_class") != result.get("status"):
            raise fatal(
                fix.FailureCode.INVALID_PROPOSAL,
                "non-success apply result must bind failure_class to status",
                "sandbox_apply_result_schema",
            )
        if not result.get("failure_code"):
            raise fatal(
                fix.FailureCode.INVALID_PROPOSAL,
                "non-success apply result must include failure_code",
                "sandbox_apply_result_schema",
            )
    else:
        raise fatal(
            fix.FailureCode.INVALID_PROPOSAL,
            "sandbox apply result status is not allowed",
            "sandbox_apply_result_schema",
        )


def write_apply_artifact(
    *,
    output_dir: Path,
    result: dict[str, Any],
    checkout_verification: dict[str, Any],
    patch_apply_check: dict[str, Any],
    changed_files: list[str],
    resulting_hashes: list[dict[str, str]],
    diff_binding: dict[str, Any],
    git_apply_log: str,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json_file(output_dir / "sandbox-validation-result.json", result)
    write_json_file(output_dir / "checkout-verification.json", checkout_verification)
    write_json_file(output_dir / "patch-apply-check.json", patch_apply_check)
    write_json_file(output_dir / "changed-files.json", {"changed_files": changed_files})
    write_json_file(output_dir / "resulting-file-hashes.json", resulting_hashes)
    write_json_file(output_dir / "diff-binding.json", diff_binding)
    (output_dir / "git-apply.log").write_text(git_apply_log[-4000:], encoding="utf-8")


def validate_final_head(
    *,
    repo: str,
    pr_number: int,
    expected_head_sha: str,
    token: str,
    code: str,
) -> None:
    live_pull = approval.fetch_live_pull(repo=repo, pr_number=pr_number, token=token)
    if str(live_pull.get("head", {}).get("sha", "")) != expected_head_sha:
        raise ApplyStatus(
            RESULT_STATUS_STALE,
            code,
            "pull request head changed during sandbox apply",
        )


def sandbox_apply_comment_body(
    *,
    result: dict[str, Any],
    workflow_run_id: str,
    repo: str,
) -> str:
    run_url = f"https://github.com/{repo}/actions/runs/{workflow_run_id}"
    planned_tests = ", ".join(f"`{test}`" for test in result.get("tests_planned", [])) or "None"
    return "\n".join(
        [
            SANDBOX_APPLY_MARKER,
            "",
            "## AI Sandbox Apply Validation",
            "",
            "> Stage 2C-B1 applied the approved proposal only inside an ephemeral sandbox. No tests, commit, push, or merge were performed.",
            "",
            f"- Phase: `{result['phase']}`",
            f"- Status: `{result['status']}`",
            f"- Apply/Validation ID: `{result['validation_id']}`",
            f"- Proposal ID: `{result['proposal_id']}`",
            f"- Approval ID: `{result['approval_id']}`",
            f"- Preflight Validation ID: `{result['preflight_validation_id']}`",
            f"- HEAD SHA: `{result['head_sha']}`",
            f"- Requested By: `{result['apply_request_actor']}`",
            f"- Checkout SHA: `{result.get('checkout_sha')}`",
            f"- Detached HEAD: `{'Yes' if result.get('detached_head') else 'No'}`",
            f"- Patch Check: `{result['git_apply_check']['status']}`",
            f"- Patch Apply: `{result['git_apply']['status']}`",
            f"- Changed Files: `{len(result.get('actual_changed_files', []))}`",
            f"- Diff Binding: `{result['diff_binding']['status']}`",
            f"- Planned Tests: {planned_tests}",
            f"- Tests Executed: `No`",
            f"- Workflow run: {run_url}",
            "",
            "### Safety",
            "",
            "- Persistent Repository Modified: `No`",
            "- Commit Created: `No`",
            "- Push Performed: `No`",
            "- Merge Performed: `No`",
            f"- Sandbox Destroyed: `{'Yes' if result.get('sandbox_destroyed') else 'No'}`",
        ]
    )


def post_or_update_apply_comment(
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
        if SANDBOX_APPLY_MARKER in str(comment.get("body", ""))
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
            "github_sandbox_apply_comment_create",
        )
    return str(comment["id"]), "create"


def command_download_request_artifact(_: argparse.Namespace) -> int:
    try:
        artifact_id = fix.run_with_retry(
            "github_sandbox_apply_request_artifact",
            lambda: fix.download_artifact_by_name(
                repo=required_env("GITHUB_REPOSITORY"),
                token=required_env("GITHUB_TOKEN"),
                run_id=required_env("COLLECTOR_RUN_ID"),
                artifact_name=required_env("ARTIFACT_NAME"),
                target_dir=Path(required_env("APPLY_REQUEST_DIR")),
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
        manifest = read_json_file(Path(required_env("APPLY_REQUEST_DIR")) / "manifest.json")
        if not isinstance(manifest, dict):
            raise fatal(
                fix.FailureCode.INVALID_MANIFEST,
                "sandbox apply request manifest must be a JSON object",
                "sandbox_apply_request_validation",
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
        request_dir = Path(required_env("APPLY_REQUEST_DIR"))
        context_dir = Path(required_env("APPLY_CONTEXT_DIR"))
        proposal_dir = Path(required_env("PROPOSAL_ARTIFACT_DIR"))
        approval_dir = Path(required_env("APPROVAL_ARTIFACT_DIR"))
        preflight_dir = Path(required_env("PREFLIGHT_ARTIFACT_DIR"))
        policy_path = Path(required_env("FIX_POLICY"))
        manifest = read_json_file(request_dir / "manifest.json")
        if not isinstance(manifest, dict):
            raise fatal(
                fix.FailureCode.INVALID_MANIFEST,
                "sandbox apply request manifest must be a JSON object",
                "sandbox_apply_prepare",
            )
        validate_request_manifest_shape(manifest)
        apply_actor = required_env("APPLY_ACTOR")
        policy = fix.load_fix_proposal_policy(policy_path)
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
        apply_permission = approval.approval_actor_repository_permission(
            repo=repo,
            actor=apply_actor,
            token=token,
        )
        live_labels = validate_live_apply_gate(
            manifest=manifest,
            live_pull=live_pull,
            live_issue=live_issue,
            policy=policy,
            apply_actor=apply_actor,
            apply_actor_permission=str(apply_permission["permission"]),
        )
        proposal_bundle = preflight.find_latest_proposal_artifact(
            repo=repo,
            token=token,
            manifest=manifest,
            policy=policy,
            output_dir=proposal_dir,
            max_bytes=int(required_env("MAX_ARTIFACT_BYTES")),
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
                "sandbox_apply_approval_actor_permission",
            )
        validation_actor = str(approval_bundle.record.get("validation_request_actor", ""))
        preflight_bundle = find_latest_preflight_artifact(
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
                "sandbox_apply_validation_actor_permission",
            )
        context = build_apply_context(
            manifest=manifest,
            proposal_bundle=proposal_bundle,
            approval_bundle=approval_bundle,
            preflight_bundle=preflight_bundle,
            apply_actor=apply_actor,
            apply_actor_permission=str(apply_permission["permission"]),
            apply_actor_role=apply_permission.get("role_name"),
            validation_actor_permission=str(validation_permission["permission"]),
            validation_actor_role=validation_permission.get("role_name"),
            approval_actor_permission=str(approval_permission["permission"]),
            approval_actor_role=approval_permission.get("role_name"),
            live_labels=live_labels,
        )
        validate_final_head(
            repo=repo,
            pr_number=int(manifest["pull_request_number"]),
            expected_head_sha=str(manifest["head_sha"]),
            token=token,
            code="PRE_CHECKOUT_HEAD_STALE",
        )
        context_dir.mkdir(parents=True, exist_ok=True)
        write_json_file(context_dir / APPLY_CONTEXT_FILE, context)
        artifact_name = f"sandbox-apply-result-{context['apply_id']}"
        github_output(
            {
                "apply_ready": "true",
                "should_comment": "true",
                "artifact_name": artifact_name,
                "pr_number": str(manifest["pull_request_number"]),
                "head_sha": str(manifest["head_sha"]),
                "apply_id": str(context["apply_id"]),
            }
        )
        write_job_summary(
            "\n".join(
                [
                    "## Sandbox Apply Prepare",
                    "",
                    f"- status: `READY`",
                    f"- apply ID: `{context['apply_id']}`",
                    f"- head SHA: `{manifest['head_sha']}`",
                    "- checkout: not yet performed",
                    "- tests executed: `false`",
                ]
            )
        )
        return 0
    except ApplyStatus as status_error:
        raise SystemExit(
            fix.fail_command(
                fatal(
                    fix.FailureCode.STALE_ARTIFACT,
                    status_error.message,
                    "sandbox_apply_prepare",
                )
            )
        )
    except fix.FixProposalFailure as error:
        return fix.fail_command(error)


def command_apply(_: argparse.Namespace) -> int:
    context_path = Path(required_env("APPLY_CONTEXT_DIR")) / APPLY_CONTEXT_FILE
    output_dir = Path(required_env("APPLY_RESULT_DIR"))
    worktree = Path(required_env("SANDBOX_WORKTREE"))
    patch_path = Path(required_env("PATCH_FILE"))
    schema_path = Path(required_env("SANDBOX_RESULT_SCHEMA"))
    repo = required_env("GITHUB_REPOSITORY")
    token = required_env("GITHUB_TOKEN")
    context = read_json_file(context_path)
    if not isinstance(context, dict):
        raise SystemExit(1)
    checkout_verification: dict[str, Any] = check_result("SKIPPED", "checkout not verified")
    patch_apply_check: dict[str, Any] = check_result("SKIPPED", "patch not checked")
    changed_files: list[str] = []
    resulting_hashes: list[dict[str, str]] = []
    diff_binding: dict[str, Any] = check_result("SKIPPED", "diff binding not evaluated")
    git_apply_log = ""
    step_state: dict[str, Any] = {
        "patch_check": check_result("SKIPPED", "git apply --check has not run yet."),
        "patch_apply": check_result("SKIPPED", "patch apply has not run yet."),
        "sandbox_worktree_modified": False,
        "sandbox_checkout_performed": False,
        "patch_check_performed": False,
        "patch_applied": False,
        "checkout_performed": False,
        "checkout_sha": None,
        "detached_head": False,
        "credentials_persisted": False,
        "git_apply_check": check_result("SKIPPED", "git apply --check not run."),
        "git_apply": check_result("SKIPPED", "git apply not run."),
        "diff_binding": check_result("SKIPPED", "diff binding not evaluated."),
    }
    patch_check_started = False
    patch_apply_started = False
    result = base_apply_result(
        context=context,
        status=RESULT_STATUS_FATAL,
        failure_class=RESULT_STATUS_FATAL,
        failure_code="INCOMPLETE",
    )
    cleanup = check_result("SKIPPED", "cleanup not started")
    try:
        validate_final_head(
            repo=repo,
            pr_number=int(context["manifest"]["pull_request_number"]),
            expected_head_sha=str(context["manifest"]["head_sha"]),
            token=token,
            code="POST_CHECKOUT_HEAD_STALE",
        )
        checkout_verification = verify_checkout(worktree, str(context["manifest"]["head_sha"]))
        step_state.update(
            {
                "sandbox_checkout_performed": True,
                "checkout_performed": True,
                "checkout_sha": checkout_verification["head_sha"],
                "detached_head": True,
                "credentials_persisted": False,
            }
        )
        patch_hash = materialize_patch(context, patch_path)
        if patch_hash != context["patch_file_hash"]:
            raise ApplyStatus(
                RESULT_STATUS_FATAL,
                "PATCH_HASH_MISMATCH",
                "patch hash changed after materialization",
            )
        validate_final_head(
            repo=repo,
            pr_number=int(context["manifest"]["pull_request_number"]),
            expected_head_sha=str(context["manifest"]["head_sha"]),
            token=token,
            code="PRE_APPLY_HEAD_STALE",
        )
        before_check_status = run_git(
            worktree,
            ("git", "status", "--porcelain=v1", "-z"),
        ).stdout
        patch_check_started = True
        check = run_git(worktree, (*GIT_APPLY_CHECK_ARGV, str(patch_path)))
        git_apply_log += check.stdout + check.stderr
        after_check_status = run_git(
            worktree,
            ("git", "status", "--porcelain=v1", "-z"),
        ).stdout
        if after_check_status != before_check_status:
            raise ApplyStatus(
                RESULT_STATUS_PATCH_REJECTED,
                "APPLY_CHECK_MUTATED_TREE",
                "git apply --check changed the sandbox worktree",
            )
        step_state.update(
            {
                "patch_check": check_result("PASS", "git apply --check succeeded."),
                "patch_check_performed": True,
                "git_apply_check": check_result("PASS", "git apply --check succeeded."),
            }
        )
        patch_apply_started = True
        apply = run_git(worktree, (*GIT_APPLY_ARGV, str(patch_path)))
        git_apply_log += apply.stdout + apply.stderr
        step_state.update(
            {
                "patch_apply": check_result("PASS", "git apply succeeded."),
                "sandbox_worktree_modified": True,
                "patch_applied": True,
                "git_apply": check_result("PASS", "git apply succeeded."),
            }
        )
        changed_files, diff_binding, resulting_hashes = verify_changed_files(
            worktree=worktree,
            context=context,
        )
        step_state["diff_binding"] = check_result(
            str(diff_binding["status"]),
            str(diff_binding["message"]),
        )
        validate_final_head(
            repo=repo,
            pr_number=int(context["manifest"]["pull_request_number"]),
            expected_head_sha=str(context["manifest"]["head_sha"]),
            token=token,
            code="FINAL_HEAD_STALE",
        )
        patch_apply_check = {
            "status": "PASS",
            "git_apply_check": "PASS",
            "git_apply": "PASS",
            "message": "fixed git apply argv succeeded",
        }
        result = base_apply_result(
            context=context,
            status=RESULT_STATUS_APPLY_PASSED,
            failure_class=None,
            failure_code=None,
        )
        result.update(
            {
                "actual_changed_files": changed_files,
                "changed_files_match_expected": True,
                "resulting_file_hashes": resulting_hashes,
                **step_state,
            }
        )
    except ApplyStatus as status_error:
        if status_error.status == RESULT_STATUS_PATCH_REJECTED:
            failed_check = check_result("FAIL", status_error.message)
            if patch_check_started and not step_state["patch_check_performed"]:
                step_state["patch_check"] = failed_check
                step_state["git_apply_check"] = failed_check
            elif patch_apply_started and not step_state["patch_applied"]:
                step_state["patch_apply"] = failed_check
                step_state["git_apply"] = failed_check
            elif step_state["patch_applied"]:
                changed_files = changed_paths_best_effort(worktree)
                step_state["diff_binding"] = failed_check
                diff_binding = failed_check
        result = base_apply_result(
            context=context,
            status=status_error.status,
            failure_class=status_error.status,
            failure_code=status_error.code,
        )
        patch_apply_check = {
            "status": "FAIL" if status_error.status == RESULT_STATUS_PATCH_REJECTED else "SKIPPED",
            "git_apply_check": str(step_state["git_apply_check"]["status"]),
            "git_apply": str(step_state["git_apply"]["status"]),
            "message": status_error.message,
        }
        result.update(
            {
                "actual_changed_files": changed_files,
                **step_state,
            }
        )
    finally:
        cleanup = cleanup_paths((patch_path, worktree))
        result["sandbox_cleanup"] = cleanup
        result["sandbox_destroyed"] = cleanup["status"] == "PASS"
        if cleanup["status"] != "PASS" and result["status"] == RESULT_STATUS_APPLY_PASSED:
            result["status"] = RESULT_STATUS_FATAL
            result["failure_class"] = RESULT_STATUS_FATAL
            result["failure_code"] = "SANDBOX_CLEANUP_FAILED"
        validate_apply_result_against_schema(result, schema_path)
        write_apply_artifact(
            output_dir=output_dir,
            result=result,
            checkout_verification=checkout_verification,
            patch_apply_check=patch_apply_check,
            changed_files=changed_files,
            resulting_hashes=resulting_hashes,
            diff_binding=diff_binding,
            git_apply_log=git_apply_log,
        )
        github_output(
            {
                "result_ready": "true",
                "should_comment": "true",
                "status": str(result["status"]),
                "apply_id": str(result["validation_id"]),
            }
        )
        write_job_summary(
            "\n".join(
                [
                    "## Sandbox Apply Result",
                    "",
                    f"- status: `{result['status']}`",
                    f"- apply ID: `{result['validation_id']}`",
                    f"- patch applied: `{result['patch_applied']}`",
                    "- tests executed: `false`",
                    f"- sandbox destroyed: `{result['sandbox_destroyed']}`",
                ]
            )
        )
    return 0


def command_post_comment(_: argparse.Namespace) -> int:
    try:
        repo = required_env("GITHUB_REPOSITORY")
        result_path = Path(required_env("APPLY_RESULT_PATH"))
        result = read_json_file(result_path)
        if not isinstance(result, dict):
            raise fatal(
                fix.FailureCode.INVALID_PROPOSAL,
                "sandbox apply result must be a JSON object",
                "sandbox_apply_comment",
            )
        validate_apply_result_against_schema(
            result,
            Path(required_env("SANDBOX_RESULT_SCHEMA")),
        )
        preflight.validate_final_head(
            repo=repo,
            pr_number=int(required_env("PR_NUMBER")),
            expected_head_sha=required_env("HEAD_SHA"),
            token=required_env("GITHUB_TOKEN"),
        )
        body = sandbox_apply_comment_body(
            result=result,
            workflow_run_id=required_env("WORKFLOW_RUN_ID"),
            repo=repo,
        )
        comment_id, action = post_or_update_apply_comment(
            repo=repo,
            issue_number=required_env("PR_NUMBER"),
            token=required_env("GITHUB_TOKEN"),
            body=body,
        )
        github_output({"comment_id": comment_id, "comment_action": action})
        return 0
    except preflight.PreflightStatus as status_error:
        raise SystemExit(
            fix.fail_command(
                fatal(
                    fix.FailureCode.STALE_ARTIFACT,
                    status_error.message,
                    "sandbox_apply_comment",
                )
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
    subparsers.add_parser("apply").set_defaults(func=command_apply)
    subparsers.add_parser("post-comment").set_defaults(func=command_post_comment)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
