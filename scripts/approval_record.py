#!/usr/bin/env python3
"""Stage 2B approval-record helpers.

This module records a human approval for an already verified Stage 2A fix
proposal. It must never apply patches, edit repository files, run recommended
tests, commit, push, merge, or create pull requests.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import urllib.error
from pathlib import Path
from typing import Any, Iterable

import architect_review_retry as stage1
import check_fix_proposal_design as proposal_design
import fix_proposal_generator as fix


EXPECTED_REPOSITORY = "Vectology-cloud-team/namma-rogue-agent"
COLLECTOR_WORKFLOW_NAME = "Fix Approval Request Collect"
RECORDER_WORKFLOW_NAME = "Fix Approval Recorder"
APPROVAL_REQUEST_SCHEMA_VERSION = "fix-approval-request-v1"
APPROVAL_RECORD_SCHEMA_VERSION = "approval-record-v3"
APPROVAL_MARKER = "<!-- namma-ai-approval -->"
APPROVAL_SOURCE_LABEL = "ai-fix-approved-label"
APPROVAL_STATUS_APPROVED = "APPROVED"
APPROVAL_STATUS_PENDING = "PENDING"
APPROVAL_STATUS_STALE = "STALE"
MAX_ARTIFACT_BYTES = 100000
ALLOWED_REPOSITORY_PERMISSIONS = {"admin", "maintain"}
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def required_env(name: str) -> str:
    return stage1.required_env(name)


def github_output(values: dict[str, str]) -> None:
    stage1.github_output(values)


def write_job_summary(text: str) -> None:
    stage1.write_job_summary(text)


def read_json_file(path: Path) -> Any:
    return fix.read_json_file(path)


def fatal(
    code: fix.FailureCode,
    message: str,
    operation: str,
) -> fix.FixProposalFailure:
    return fix.fatal(code, message, operation)


def canonical_json_bytes(value: Any) -> bytes:
    return fix.canonical_json_bytes(value)


def sha256_hex_json(value: Any) -> str:
    return fix.sha256_hex_json(value)


def labels_from_pull_or_issue(data: dict[str, Any]) -> set[str]:
    labels = data.get("labels", [])
    if not isinstance(labels, list):
        return set()
    return {
        str(label.get("name", ""))
        for label in labels
        if isinstance(label, dict) and label.get("name")
    }


def labels_from_request(request: dict[str, Any]) -> set[str]:
    labels = request.get("labels", [])
    if not isinstance(labels, list):
        return set()
    return {str(label) for label in labels}


def ensure_full_sha(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not SHA_RE.fullmatch(value):
        raise fatal(
            fix.FailureCode.INVALID_MANIFEST,
            f"{field_name} must be a full lowercase commit SHA",
            "approval_request_validation",
        )
    return value


def ensure_sha256(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise fatal(
            fix.FailureCode.INVALID_PROPOSAL,
            f"{field_name} must be a lowercase SHA-256 hex digest",
            "approval_validation",
        )
    return value


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
        "event_label",
        "collector_workflow_name",
        "collector_workflow_run_id",
    }
    missing = sorted(required.difference(manifest))
    extra = sorted(set(manifest).difference(required))
    if missing or extra:
        raise fatal(
            fix.FailureCode.INVALID_MANIFEST,
            f"approval request manifest field mismatch: missing={missing}, extra={extra}",
            "approval_request_validation",
        )
    if manifest["schema_version"] != APPROVAL_REQUEST_SCHEMA_VERSION:
        raise fatal(
            fix.FailureCode.INVALID_MANIFEST,
            "unsupported approval request manifest schema",
            "approval_request_validation",
        )
    if manifest["repository"] != EXPECTED_REPOSITORY:
        raise fatal(
            fix.FailureCode.REPOSITORY_MISMATCH,
            "approval request repository mismatch",
            "approval_request_validation",
        )
    if manifest["collector_workflow_name"] != COLLECTOR_WORKFLOW_NAME:
        raise fatal(
            fix.FailureCode.TRUST_BOUNDARY_VIOLATION,
            "approval request came from an unexpected collector workflow",
            "approval_request_validation",
        )
    if not isinstance(manifest["pull_request_number"], int):
        raise fatal(
            fix.FailureCode.PR_MISMATCH,
            "pull_request_number must be an integer",
            "approval_request_validation",
        )
    ensure_full_sha(manifest["base_sha"], "base_sha")
    ensure_full_sha(manifest["head_sha"], "head_sha")
    if not isinstance(manifest["labels"], list):
        raise fatal(
            fix.FailureCode.INVALID_MANIFEST,
            "labels must be an array",
            "approval_request_validation",
        )


def validate_approval_record_schema_file(path: Path) -> None:
    schema = read_json_file(path)
    if not isinstance(schema, dict):
        raise fatal(
            fix.FailureCode.WORKFLOW_CONFIGURATION_ERROR,
            "approval record schema must be a JSON object",
            "approval_schema",
        )
    required = schema.get("required")
    if not isinstance(required, list):
        raise fatal(
            fix.FailureCode.WORKFLOW_CONFIGURATION_ERROR,
            "approval record schema must declare required fields",
            "approval_schema",
        )
    for key in APPROVAL_RECORD_KEYS:
        if key not in required:
            raise fatal(
                fix.FailureCode.WORKFLOW_CONFIGURATION_ERROR,
                f"approval record schema missing required field: {key}",
                "approval_schema",
            )
    status_enum = (
        schema.get("properties", {})
        .get("status", {})
        .get("enum", [])
    )
    if set(status_enum) != {
        APPROVAL_STATUS_PENDING,
        APPROVAL_STATUS_APPROVED,
        APPROVAL_STATUS_STALE,
    }:
        raise fatal(
            fix.FailureCode.WORKFLOW_CONFIGURATION_ERROR,
            "approval record schema must restrict status values",
            "approval_schema",
        )


APPROVAL_RECORD_KEYS = {
    "schema_version",
    "approval_id",
    "approval_record_hash",
    "proposal_id",
    "proposal_hash",
    "repository",
    "pull_request_number",
    "base_sha",
    "head_sha",
    "approved_by",
    "approved_by_repository_permission",
    "approved_by_repository_role",
    "approved_at",
    "approval_source",
    "policy_hash",
    "generator_model",
    "generator_effort",
    "human_approval_required",
    "status",
}


def approval_record_hash_source(record: dict[str, Any]) -> dict[str, Any]:
    hash_source = dict(record)
    hash_source.pop("approval_record_hash", None)
    return hash_source


def approval_record_hash(record: dict[str, Any]) -> str:
    return sha256_hex_json(approval_record_hash_source(record))


def validate_approval_record_hash(record: dict[str, Any]) -> None:
    expected_hash = ensure_sha256(
        record.get("approval_record_hash"),
        "approval_record_hash",
    )
    actual_hash = approval_record_hash(record)
    if actual_hash != expected_hash:
        raise fatal(
            fix.FailureCode.INVALID_PROPOSAL,
            "approval record hash does not match canonical approval record content",
            "approval_record_validation",
        )


def validate_approval_record_shape(record: dict[str, Any]) -> None:
    missing = sorted(APPROVAL_RECORD_KEYS.difference(record))
    extra = sorted(set(record).difference(APPROVAL_RECORD_KEYS))
    if missing or extra:
        raise fatal(
            fix.FailureCode.INVALID_PROPOSAL,
            f"approval record shape mismatch missing={missing} extra={extra}",
            "approval_record_validation",
        )
    if record["schema_version"] != APPROVAL_RECORD_SCHEMA_VERSION:
        raise fatal(
            fix.FailureCode.INVALID_PROPOSAL,
            "approval record schema_version mismatch",
            "approval_record_validation",
        )
    if not re.fullmatch(r"[0-9a-f]{32}", str(record["approval_id"])):
        raise fatal(
            fix.FailureCode.INVALID_PROPOSAL,
            "approval_id must be a 32 character lowercase hex prefix",
            "approval_record_validation",
        )
    if record["status"] not in {
        APPROVAL_STATUS_PENDING,
        APPROVAL_STATUS_APPROVED,
        APPROVAL_STATUS_STALE,
    }:
        raise fatal(
            fix.FailureCode.INVALID_PROPOSAL,
            "approval status is not allowed",
            "approval_record_validation",
        )
    ensure_sha256(record["proposal_hash"], "proposal_hash")
    validate_approval_record_hash(record)
    ensure_sha256(record["policy_hash"], "policy_hash")
    ensure_full_sha(record["base_sha"], "base_sha")
    ensure_full_sha(record["head_sha"], "head_sha")
    if str(record["approved_by_repository_permission"]) not in {"admin", "maintain"}:
        raise fatal(
            fix.FailureCode.UNAUTHORIZED_ASSOCIATION,
            "approved_by_repository_permission must be admin or maintain",
            "approval_record_validation",
        )
    role = record["approved_by_repository_role"]
    if role is not None and not isinstance(role, str):
        raise fatal(
            fix.FailureCode.INVALID_PROPOSAL,
            "approved_by_repository_role must be a string or null",
            "approval_record_validation",
        )
    if record["approval_source"] != APPROVAL_SOURCE_LABEL:
        raise fatal(
            fix.FailureCode.INVALID_PROPOSAL,
            "approval_source must bind to the approval label",
            "approval_record_validation",
        )
    if record["human_approval_required"] is not True:
        raise fatal(
            fix.FailureCode.INVALID_PROPOSAL,
            "approval record must preserve human_approval_required",
            "approval_record_validation",
        )


def fetch_live_pull(
    *,
    repo: str,
    pr_number: int,
    token: str,
) -> dict[str, Any]:
    pull, _ = stage1.github_json(
        "GET",
        f"/repos/{repo}/pulls/{pr_number}",
        token=token,
    )
    if not isinstance(pull, dict):
        raise fatal(
            fix.FailureCode.PR_MISMATCH,
            "GitHub pull request response was not an object",
            "github_pull_lookup",
        )
    return pull


def fetch_live_issue(
    *,
    repo: str,
    pr_number: int,
    token: str,
) -> dict[str, Any]:
    issue, _ = stage1.github_json(
        "GET",
        f"/repos/{repo}/issues/{pr_number}",
        token=token,
    )
    if not isinstance(issue, dict):
        raise fatal(
            fix.FailureCode.PR_MISMATCH,
            "GitHub issue response was not an object",
            "github_issue_lookup",
        )
    return issue


def validate_approval_gate(
    *,
    manifest: dict[str, Any],
    live_pull: dict[str, Any],
    live_issue: dict[str, Any],
    policy: fix.FixProposalPolicy,
    approval_actor: str,
    approval_actor_repository_permission: str,
) -> None:
    validate_request_manifest_shape(manifest)
    proposal_label = policy.proposal_policy.proposal_label
    approval_label = policy.proposal_policy.approval_label
    request_labels = labels_from_request(manifest)
    live_labels = labels_from_pull_or_issue(live_issue)
    if approval_actor != str(manifest["actor"]):
        raise fatal(
            fix.FailureCode.TRUST_BOUNDARY_VIOLATION,
            "approval actor mismatch between trusted workflow_run data and request artifact",
            "approval_gate",
        )
    if manifest.get("event_action") != "labeled":
        raise fatal(
            fix.FailureCode.LABEL_MISSING,
            "approval record requires the approval label event",
            "approval_gate",
        )
    if manifest.get("event_label") != approval_label:
        raise fatal(
            fix.FailureCode.LABEL_MISSING,
            "approval record requires the ai-fix-approved label event",
            "approval_gate",
        )
    if approval_label not in request_labels:
        raise fatal(
            fix.FailureCode.LABEL_MISSING,
            "approval request does not contain the approval label",
            "approval_gate",
        )
    if approval_label not in live_labels:
        raise fatal(
            fix.FailureCode.LABEL_MISSING,
            "live pull request does not contain the approval label",
            "approval_gate",
        )
    if proposal_label not in request_labels:
        raise fatal(
            fix.FailureCode.LABEL_MISSING,
            "approval request does not contain the proposal label",
            "approval_gate",
        )
    if proposal_label not in live_labels:
        raise fatal(
            fix.FailureCode.LABEL_MISSING,
            "live pull request does not contain the proposal label",
            "approval_gate",
        )
    if bool(manifest.get("draft")) or bool(live_pull.get("draft")):
        raise fatal(
            fix.FailureCode.DRAFT_PULL_REQUEST,
            "draft pull requests cannot produce approval records",
            "approval_gate",
        )
    if manifest.get("base_repository") != EXPECTED_REPOSITORY:
        raise fatal(
            fix.FailureCode.REPOSITORY_MISMATCH,
            "base repository mismatch",
            "approval_gate",
        )
    if manifest.get("head_repository") != EXPECTED_REPOSITORY:
        raise fatal(
            fix.FailureCode.FORK_PULL_REQUEST,
            "fork pull requests cannot produce approval records",
            "approval_gate",
        )
    live_head_sha = str(live_pull.get("head", {}).get("sha", ""))
    live_base_sha = str(live_pull.get("base", {}).get("sha", ""))
    if live_head_sha != manifest["head_sha"]:
        raise fatal(
            fix.FailureCode.SHA_MISMATCH,
            "live pull request head SHA changed after approval request collection",
            "approval_gate",
        )
    if live_base_sha != manifest["base_sha"]:
        raise fatal(
            fix.FailureCode.SHA_MISMATCH,
            "live pull request base SHA changed after approval request collection",
            "approval_gate",
        )
    if int(live_pull.get("number", 0)) != int(manifest["pull_request_number"]):
        raise fatal(
            fix.FailureCode.PR_MISMATCH,
            "live pull request number mismatch",
            "approval_gate",
        )
    if str(live_pull.get("user", {}).get("type", "")).lower() == "bot":
        raise fatal(
            fix.FailureCode.BOT_PULL_REQUEST,
            "bot pull requests cannot produce approval records",
            "approval_gate",
        )
    if approval_actor_repository_permission not in ALLOWED_REPOSITORY_PERMISSIONS:
        raise fatal(
            fix.FailureCode.UNAUTHORIZED_ASSOCIATION,
            "approval actor must have repository admin or maintain permission",
            "approval_gate",
        )


def approval_actor_repository_permission(
    *,
    repo: str,
    actor: str,
    token: str,
) -> dict[str, str | None]:
    try:
        response, _ = stage1.github_json(
            "GET",
            f"/repos/{repo}/collaborators/{actor}/permission",
            token=token,
        )
    except urllib.error.HTTPError as error:
        if error.code in (401, 403):
            raise fatal(
                fix.FailureCode.PERMISSION_ERROR,
                "repository permission could not be confirmed for approval actor",
                "github_approval_actor_repository_permission",
            ) from error
        if error.code == 404:
            raise fatal(
                fix.FailureCode.UNAUTHORIZED_ASSOCIATION,
                "approval actor is not a repository collaborator",
                "github_approval_actor_repository_permission",
            ) from error
        raise fix.classify_github_operation(
            error,
            "github_approval_actor_repository_permission",
        ) from error
    except BaseException as error:
        raise fix.classify_github_operation(
            error,
            "github_approval_actor_repository_permission",
        ) from error
    if not isinstance(response, dict):
        raise fatal(
            fix.FailureCode.UNAUTHORIZED_ASSOCIATION,
            "repository permission response was malformed",
            "github_approval_actor_repository_permission",
        )
    user = response.get("user")
    if not isinstance(user, dict) or user.get("login") != actor:
        raise fatal(
            fix.FailureCode.TRUST_BOUNDARY_VIOLATION,
            "repository permission response actor mismatch",
            "github_approval_actor_repository_permission",
        )
    permission = response.get("permission")
    if not isinstance(permission, str) or not permission:
        raise fatal(
            fix.FailureCode.UNAUTHORIZED_ASSOCIATION,
            "repository permission response missing permission",
            "github_approval_actor_repository_permission",
        )
    role_name = response.get("role_name")
    if role_name is None and isinstance(user.get("role_name"), str):
        role_name = user["role_name"]
    if role_name is not None and not isinstance(role_name, str):
        role_name = None
    return {
        "permission": permission.lower(),
        "role_name": role_name,
    }


def proposal_hash_for_approval(
    *,
    proposal: dict[str, Any],
    metadata: dict[str, Any],
) -> str:
    hash_source = {
        "repository": proposal.get("repository"),
        "pull_request_number": proposal.get("pull_request_number"),
        "base_sha": proposal.get("base_sha"),
        "head_sha": proposal.get("head_sha"),
        "policy_hash": metadata.get("policy_hash"),
        "proposal_input_hash": metadata.get("proposal_input_hash"),
        "review_result_hash": metadata.get("source_review_hash"),
        "source_review_run_id": proposal.get("source_review_run_id"),
        "source_review_artifact_id": proposal.get("source_review_artifact_id"),
        "reviewed_at": proposal.get("reviewed_at"),
        "generator": proposal.get("generator"),
        "canonical_changes": proposal.get("changes", []),
        "findings_addressed": proposal.get("findings_addressed", []),
        "summary": proposal.get("summary", ""),
        "tests_recommended": proposal.get("tests_recommended", []),
        "risks": proposal.get("risks", []),
    }
    return sha256_hex_json(hash_source)


def validate_proposal_for_approval(
    *,
    manifest: dict[str, Any],
    proposal: dict[str, Any],
    metadata: dict[str, Any],
    policy: fix.FixProposalPolicy,
) -> None:
    if metadata.get("schema_version") != fix.PROPOSAL_METADATA_SCHEMA_VERSION:
        raise fatal(
            fix.FailureCode.INVALID_PROPOSAL,
            "proposal metadata schema mismatch",
            "approval_proposal_validation",
        )
    if metadata.get("status") != fix.PROPOSAL_STATUS_READY:
        raise fatal(
            fix.FailureCode.STALE_ARTIFACT,
            "proposal is not ready for approval",
            "approval_proposal_validation",
        )
    if proposal.get("human_approval_required") is not True:
        raise fatal(
            fix.FailureCode.INVALID_PROPOSAL,
            "proposal must require human approval",
            "approval_proposal_validation",
        )
    expected_pairs = (
        ("repository", "repository"),
        ("pull_request_number", "pull_request_number"),
        ("base_sha", "base_sha"),
        ("head_sha", "head_sha"),
        ("proposal_id", "proposal_id"),
    )
    for proposal_key, metadata_key in expected_pairs:
        if proposal.get(proposal_key) != metadata.get(metadata_key):
            raise fatal(
                fix.FailureCode.INVALID_PROPOSAL,
                f"proposal field {proposal_key} does not match metadata",
                "approval_proposal_validation",
            )
    if proposal.get("repository") != manifest["repository"]:
        raise fatal(
            fix.FailureCode.REPOSITORY_MISMATCH,
            "proposal repository mismatch",
            "approval_proposal_validation",
        )
    if proposal.get("pull_request_number") != manifest["pull_request_number"]:
        raise fatal(
            fix.FailureCode.PR_MISMATCH,
            "proposal pull request number mismatch",
            "approval_proposal_validation",
        )
    if proposal.get("base_sha") != manifest["base_sha"]:
        raise fatal(
            fix.FailureCode.SHA_MISMATCH,
            "proposal base SHA mismatch",
            "approval_proposal_validation",
        )
    if proposal.get("head_sha") != manifest["head_sha"]:
        raise fatal(
            fix.FailureCode.SHA_MISMATCH,
            "proposal head SHA mismatch",
            "approval_proposal_validation",
        )
    proposal_hash = ensure_sha256(metadata.get("proposal_hash"), "proposal_hash")
    recomputed_hash = proposal_hash_for_approval(
        proposal=proposal,
        metadata=metadata,
    )
    if recomputed_hash != proposal_hash:
        raise fatal(
            fix.FailureCode.INVALID_PROPOSAL,
            "proposal hash does not match canonical proposal content",
            "approval_proposal_validation",
        )
    if str(proposal.get("proposal_id", "")) != proposal_hash[:32]:
        raise fatal(
            fix.FailureCode.INVALID_PROPOSAL,
            "proposal ID does not match proposal hash prefix",
            "approval_proposal_validation",
        )
    if metadata.get("policy_hash") != policy.policy_hash:
        raise fatal(
            fix.FailureCode.TRUST_BOUNDARY_VIOLATION,
            "proposal policy hash does not match trusted policy",
            "approval_proposal_validation",
        )
    generator = proposal.get("generator", {})
    if not isinstance(generator, dict):
        raise fatal(
            fix.FailureCode.INVALID_PROPOSAL,
            "proposal generator metadata must be an object",
            "approval_proposal_validation",
        )
    if generator.get("model") != metadata.get("generator_model"):
        raise fatal(
            fix.FailureCode.INVALID_PROPOSAL,
            "proposal generator model mismatch",
            "approval_proposal_validation",
        )
    if generator.get("reasoning_effort") != metadata.get("reasoning_effort"):
        raise fatal(
            fix.FailureCode.INVALID_PROPOSAL,
            "proposal generator effort mismatch",
            "approval_proposal_validation",
        )
    if generator.get("policy_version") != policy.policy_hash:
        raise fatal(
            fix.FailureCode.TRUST_BOUNDARY_VIOLATION,
            "proposal generator policy version mismatch",
            "approval_proposal_validation",
        )
    try:
        proposal_design.validate_schema_file()
        proposal_design.validate_fix_proposal(
            proposal,
            policy.proposal_policy,
            current_head_sha=manifest["head_sha"],
            expected_repository=manifest["repository"],
        )
    except proposal_design.ProposalValidationError as exc:
        raise fatal(
            fix.FailureCode.INVALID_PROPOSAL,
            f"proposal validation failed before approval: {exc.code}",
            "approval_proposal_validation",
        ) from exc


def build_approval_record(
    *,
    manifest: dict[str, Any],
    proposal: dict[str, Any],
    metadata: dict[str, Any],
    approved_by: str | None = None,
    approved_by_repository_permission: str,
    approved_by_repository_role: str | None,
    approved_at: str | None = None,
) -> dict[str, Any]:
    if approved_at is None:
        approved_at = dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")
    record = {
        "schema_version": APPROVAL_RECORD_SCHEMA_VERSION,
        "approval_id": "",
        "approval_record_hash": "",
        "proposal_id": str(metadata["proposal_id"]),
        "proposal_hash": str(metadata["proposal_hash"]),
        "repository": str(metadata["repository"]),
        "pull_request_number": int(metadata["pull_request_number"]),
        "base_sha": str(metadata["base_sha"]),
        "head_sha": str(metadata["head_sha"]),
        "approved_by": str(approved_by or manifest["actor"]),
        "approved_by_repository_permission": approved_by_repository_permission,
        "approved_by_repository_role": approved_by_repository_role,
        "approved_at": approved_at,
        "approval_source": APPROVAL_SOURCE_LABEL,
        "policy_hash": str(metadata["policy_hash"]),
        "generator_model": str(metadata["generator_model"]),
        "generator_effort": str(metadata["reasoning_effort"]),
        "human_approval_required": bool(proposal["human_approval_required"]),
        "status": APPROVAL_STATUS_APPROVED,
    }
    hash_source = dict(record)
    del hash_source["approval_id"]
    record["approval_id"] = sha256_hex_json(hash_source)[:32]
    record["approval_record_hash"] = approval_record_hash(record)
    validate_approval_record_shape(record)
    return record


def write_approval_artifact(
    *,
    output_dir: Path,
    record: dict[str, Any],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "approval-record.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def is_unavailable_proposal_artifact_candidate(error: BaseException) -> bool:
    if isinstance(error, urllib.error.HTTPError) and error.code in {404, 410}:
        return True
    if not isinstance(error, fix.FixProposalFailure):
        return False
    if error.failure_class is not fix.FailureClass.RETRYABLE:
        return False
    if error.code is not fix.FailureCode.ARTIFACT_TRANSIENT_ERROR:
        return False
    message = error.message.lower()
    return any(
        fragment in message
        for fragment in (
            "not available yet",
            "not found",
            "expired",
            "temporarily unavailable",
            "404",
        )
    )


def sorted_successful_workflow_runs(runs: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    successful_runs = [run for run in runs if run.get("conclusion") == "success"]
    return sorted(
        successful_runs,
        key=lambda run: (
            str(run.get("created_at", "")),
            int(run.get("id", 0) or 0),
        ),
        reverse=True,
    )


def find_latest_proposal_artifact(
    *,
    repo: str,
    token: str,
    manifest: dict[str, Any],
    policy: fix.FixProposalPolicy,
    output_dir: Path,
    max_bytes: int,
) -> tuple[dict[str, Any], dict[str, Any], int]:
    runs_data, _ = stage1.github_json(
        "GET",
        f"/repos/{repo}/actions/workflows/fix-proposal.yml/runs?status=completed&per_page=50",
        token=token,
    )
    runs = runs_data.get("workflow_runs", []) if isinstance(runs_data, dict) else []
    skipped_candidates: list[str] = []
    for run in sorted_successful_workflow_runs(runs):
        run_id = str(run.get("id", ""))
        try:
            artifacts_data, _ = stage1.github_json(
                "GET",
                f"/repos/{repo}/actions/runs/{run_id}/artifacts?per_page=100",
                token=token,
            )
        except BaseException as error:
            if is_unavailable_proposal_artifact_candidate(error):
                skipped_candidates.append(f"run {run_id}: artifacts unavailable")
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
                    run_id=run_id,
                    artifact_name=name,
                    target_dir=output_dir,
                    expected_files={"fix-proposal.json", "proposal-metadata.json"},
                    max_bytes=max_bytes,
                )
            except BaseException as error:
                if is_unavailable_proposal_artifact_candidate(error):
                    skipped_candidates.append(f"run {run_id} artifact {name}: unavailable")
                    continue
                raise
            proposal = read_json_file(output_dir / "fix-proposal.json")
            metadata = read_json_file(output_dir / "proposal-metadata.json")
            if not isinstance(proposal, dict) or not isinstance(metadata, dict):
                raise fatal(
                    fix.FailureCode.INVALID_PROPOSAL,
                    "proposal artifact files must contain JSON objects",
                    "proposal_artifact_lookup",
                )
            validate_proposal_for_approval(
                manifest=manifest,
                proposal=proposal,
                metadata=metadata,
                policy=policy,
            )
            return proposal, metadata, artifact_id
    detail = ""
    if skipped_candidates:
        detail = f" Skipped unavailable candidates: {', '.join(skipped_candidates)}."
    raise fatal(
        fix.FailureCode.PROPOSAL_ARTIFACT_NOT_FOUND,
        f"NOT_FOUND: no verified proposal artifact was found for this pull request head.{detail}",
        "proposal_artifact_lookup",
    )


def approval_comment_body(
    *,
    record: dict[str, Any],
    workflow_run_id: str,
    repo: str,
) -> str:
    return "\n".join(
        [
            APPROVAL_MARKER,
            "",
            "## AI Fix Approval",
            "",
            "> Human Approval Recorded. No repository changes, patch application, tests, commit, push, or merge were performed.",
            "",
            f"- Status: `{record['status']}`",
            f"- Approval ID: `{record['approval_id']}`",
            f"- Approval record hash: `{record['approval_record_hash']}`",
            f"- Proposal ID: `{record['proposal_id']}`",
            f"- Proposal hash: `{record['proposal_hash']}`",
            f"- HEAD SHA: `{record['head_sha']}`",
            f"- Approved By: `{record['approved_by']}`",
            f"- Approved Repository Permission: `{record['approved_by_repository_permission']}`",
            f"- Approved Repository Role: `{record['approved_by_repository_role'] or 'not provided'}`",
            f"- Approved At: `{record['approved_at']}`",
            f"- Workflow run: [{workflow_run_id}](https://github.com/{repo}/actions/runs/{workflow_run_id})",
            "",
            "Repository変更なし。",
            "Commitなし。",
            "Pushなし。",
            "Mergeなし。",
        ]
    )


def iter_approval_comments(
    repo: str,
    issue_number: str,
    token: str,
) -> Iterable[dict[str, Any]]:
    for comment in stage1.iter_issue_comments(repo, issue_number, token):
        body = comment.get("body")
        if isinstance(body, str) and APPROVAL_MARKER in body:
            yield comment


def list_existing_approval_comments(
    *,
    repo: str,
    issue_number: str,
    token: str,
) -> list[dict[str, Any]]:
    try:
        return list(iter_approval_comments(repo, issue_number, token))
    except BaseException as error:
        raise fix.classify_github_operation(
            error,
            "github_approval_comments_list",
        ) from error


def create_issue_comment(
    *,
    repo: str,
    issue_number: str,
    token: str,
    body: str,
) -> None:
    try:
        stage1.github_json(
            "POST",
            f"/repos/{repo}/issues/{issue_number}/comments",
            token=token,
            body={"body": body},
        )
    except BaseException as error:
        raise fix.classify_github_operation(
            error,
            "github_approval_comment_create",
        ) from error


def update_issue_comment(
    *,
    repo: str,
    comment_id: str,
    token: str,
    body: str,
) -> None:
    try:
        stage1.github_json(
            "PATCH",
            f"/repos/{repo}/issues/comments/{comment_id}",
            token=token,
            body={"body": body},
        )
    except BaseException as error:
        raise fix.classify_github_operation(
            error,
            "github_approval_comment_update",
        ) from error


def post_or_update_approval_comment(
    *,
    repo: str,
    issue_number: str,
    token: str,
    body: str,
) -> None:
    comments = list_existing_approval_comments(
        repo=repo,
        issue_number=issue_number,
        token=token,
    )
    if comments:
        update_issue_comment(
            repo=repo,
            comment_id=str(comments[0]["id"]),
            token=token,
            body=body,
        )
    else:
        create_issue_comment(
            repo=repo,
            issue_number=issue_number,
            token=token,
            body=body,
        )


def publish_approval_comment(
    *,
    repo: str,
    issue_number: str,
    head_sha: str,
    token: str,
    body: str,
) -> None:
    try:
        stage1.validate_comment_target(repo, issue_number, head_sha, token)
    except BaseException as error:
        raise fix.classify_github_operation(
            error,
            "github_approval_comment_target",
        ) from error
    post_or_update_approval_comment(
        repo=repo,
        issue_number=issue_number,
        token=token,
        body=body,
    )


def command_download_request_artifact(_: argparse.Namespace) -> int:
    try:
        artifact_id = fix.run_with_retry(
            "github_approval_request_artifact",
            lambda: fix.download_artifact_by_name(
                repo=required_env("GITHUB_REPOSITORY"),
                token=required_env("GITHUB_TOKEN"),
                run_id=required_env("COLLECTOR_RUN_ID"),
                artifact_name=required_env("ARTIFACT_NAME"),
                target_dir=Path(required_env("APPROVAL_REQUEST_DIR")),
                expected_files={"manifest.json"},
                max_bytes=int(required_env("MAX_ARTIFACT_BYTES")),
            ),
        ).value
        github_output({"approval_request_artifact_id": str(artifact_id)})
        return 0
    except BaseException as error:
        return fix.fail_command(error)


def command_validate_request(_: argparse.Namespace) -> int:
    try:
        manifest = read_json_file(Path(required_env("APPROVAL_REQUEST_DIR")) / "manifest.json")
        if not isinstance(manifest, dict):
            raise fatal(
                fix.FailureCode.INVALID_MANIFEST,
                "approval request manifest must be an object",
                "approval_request_validation",
            )
        validate_request_manifest_shape(manifest)
        github_output(
            {
                "pr_number": str(manifest["pull_request_number"]),
                "base_sha": str(manifest["base_sha"]),
                "head_sha": str(manifest["head_sha"]),
            }
        )
        return 0
    except BaseException as error:
        return fix.fail_command(error)


def command_record_approval(_: argparse.Namespace) -> int:
    try:
        repo = required_env("GITHUB_REPOSITORY")
        token = required_env("GITHUB_TOKEN")
        request_dir = Path(required_env("APPROVAL_REQUEST_DIR"))
        proposal_dir = Path(required_env("PROPOSAL_ARTIFACT_DIR"))
        record_dir = Path(required_env("APPROVAL_RECORD_DIR"))
        manifest = read_json_file(request_dir / "manifest.json")
        if not isinstance(manifest, dict):
            raise fatal(
                fix.FailureCode.INVALID_MANIFEST,
                "approval request manifest must be an object",
                "approval_record",
            )
        policy = fix.load_fix_proposal_policy(Path(required_env("FIX_POLICY")))
        validate_approval_record_schema_file(Path(required_env("APPROVAL_RECORD_SCHEMA")))
        live_pull = fetch_live_pull(
            repo=repo,
            pr_number=int(manifest["pull_request_number"]),
            token=token,
        )
        live_issue = fetch_live_issue(
            repo=repo,
            pr_number=int(manifest["pull_request_number"]),
            token=token,
        )
        approval_actor = required_env("APPROVAL_ACTOR")
        actor_permission = approval_actor_repository_permission(
            repo=repo,
            actor=approval_actor,
            token=token,
        )
        validate_approval_gate(
            manifest=manifest,
            live_pull=live_pull,
            live_issue=live_issue,
            policy=policy,
            approval_actor=approval_actor,
            approval_actor_repository_permission=str(actor_permission["permission"]),
        )
        proposal, metadata, proposal_artifact_id = fix.run_with_retry(
            "github_verified_proposal_artifact",
            lambda: find_latest_proposal_artifact(
                repo=repo,
                token=token,
                manifest=manifest,
                policy=policy,
                output_dir=proposal_dir,
                max_bytes=int(required_env("MAX_ARTIFACT_BYTES")),
            ),
        ).value
        record = build_approval_record(
            manifest=manifest,
            proposal=proposal,
            metadata=metadata,
            approved_by=approval_actor,
            approved_by_repository_permission=str(actor_permission["permission"]),
            approved_by_repository_role=actor_permission["role_name"],
        )
        write_approval_artifact(output_dir=record_dir, record=record)
        github_output(
            {
                "approval_ready": "true",
                "approval_id": record["approval_id"],
                "proposal_id": record["proposal_id"],
                "proposal_hash": record["proposal_hash"],
                "proposal_artifact_id": str(proposal_artifact_id),
                "artifact_name": f"approval-record-{record['approval_id']}",
            }
        )
        write_job_summary(
            "\n".join(
                [
                    "## Fix Approval Record",
                    "",
                    f"- Status: `{record['status']}`",
                    f"- Approval ID: `{record['approval_id']}`",
                    f"- Proposal ID: `{record['proposal_id']}`",
                    f"- Proposal hash: `{record['proposal_hash'][:16]}`",
                    f"- Head SHA: `{record['head_sha']}`",
                    f"- Approved By: `{record['approved_by']}`",
                    f"- Repository Permission: `{record['approved_by_repository_permission']}`",
                    "",
                    "No patch application, repository write, commit, push, or merge was performed.",
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
        issue_number = required_env("PR_NUMBER")
        workflow_run_id = required_env("WORKFLOW_RUN_ID")
        record = read_json_file(Path(required_env("APPROVAL_RECORD_PATH")))
        if not isinstance(record, dict):
            raise fatal(
                fix.FailureCode.INVALID_PROPOSAL,
                "approval record artifact must contain an object",
                "approval_comment",
            )
        validate_approval_record_shape(record)
        body = approval_comment_body(
            record=record,
            workflow_run_id=workflow_run_id,
            repo=repo,
        )
        fix.run_with_retry(
            "github_approval_comment",
            lambda: publish_approval_comment(
                repo=repo,
                issue_number=issue_number,
                head_sha=required_env("HEAD_SHA"),
                token=token,
                body=body,
            ),
        )
        return 0
    except BaseException as error:
        return fix.fail_command(error)


def command_self_check(_: argparse.Namespace) -> int:
    text = Path(__file__).read_text(encoding="utf-8")
    forbidden = [
        token
        for token in fix.FORBIDDEN_AUTOMATION_TOKENS
        if token.lower() in text.lower()
    ]
    if forbidden:
        raise SystemExit(f"approval record script contains forbidden tokens: {forbidden}")
    print("Stage 2B approval record self-check passed.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("download-request-artifact").set_defaults(
        func=command_download_request_artifact
    )
    subparsers.add_parser("validate-request").set_defaults(func=command_validate_request)
    subparsers.add_parser("record-approval").set_defaults(func=command_record_approval)
    subparsers.add_parser("post-comment").set_defaults(func=command_post_comment)
    subparsers.add_parser("self-check").set_defaults(func=command_self_check)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
