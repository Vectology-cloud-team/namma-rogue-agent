#!/usr/bin/env python3
"""Stage 2A fix proposal generation helpers.

This module is intentionally proposal-only. It may validate inputs, call the
trusted Codex proposal generator through the workflow, write proposal artifacts,
and update the fix-proposal sticky comment. It must never apply patches, edit
repository files, run proposal-recommended tests, commit, push, merge, or open
pull requests.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import json
import os
import re
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Iterable

import architect_review_retry as stage1
import check_fix_proposal_design as proposal_design


EXPECTED_REPOSITORY = "Vectology-cloud-team/namma-rogue-agent"
REPO_ROOT = Path(__file__).resolve().parents[1]
COLLECTOR_WORKFLOW_NAME = "Fix Proposal Request Collect"
GENERATOR_WORKFLOW_NAME = "Fix Proposal Generator"
REQUEST_SCHEMA_VERSION = "fix-proposal-request-v1"
REVIEW_RESULT_SCHEMA_VERSION = "architect-review-result-v1"
PROPOSAL_METADATA_SCHEMA_VERSION = "fix-proposal-metadata-v1"
PROPOSAL_MARKER = "<!-- namma-ai-fix-proposal -->"
PROPOSAL_STATUS_READY = "PROPOSAL_READY"
PROPOSAL_STATUS_SKIPPED = "SKIPPED"
PROPOSAL_STATUS_STALE = "STALE"
PROPOSAL_STATUS_FAILED = "FAILED"
MAX_ATTEMPTS = 3
RETRY_DELAYS_SECONDS = (30, 60, 120)
ALLOWED_AUTHOR_ASSOCIATIONS = {"OWNER", "MEMBER", "COLLABORATOR"}
BLOCKING_SEVERITIES = {"critical", "high"}
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
FORBIDDEN_AUTOMATION_TOKENS = (
    "git push",
    "git merge",
    "gh pr merge",
    "gh pr create",
    "createCommitOnBranch",
    "createPullRequest",
    "createReviewComment",
)


class FailureClass(str, Enum):
    RETRYABLE = "RETRYABLE"
    FATAL = "FATAL"
    SUCCESS = "SUCCESS"


class FailureCode(str, Enum):
    API_TIMEOUT = "API_TIMEOUT"
    RATE_LIMIT = "RATE_LIMIT"
    OPENAI_5XX = "OPENAI_5XX"
    GITHUB_429 = "GITHUB_429"
    GITHUB_5XX = "GITHUB_5XX"
    NETWORK_ERROR = "NETWORK_ERROR"
    ARTIFACT_TRANSIENT_ERROR = "ARTIFACT_TRANSIENT_ERROR"
    TRUSTED_PROMPT_MISSING = "TRUSTED_PROMPT_MISSING"
    INVALID_MANIFEST = "INVALID_MANIFEST"
    INVALID_JSON = "INVALID_JSON"
    REPOSITORY_MISMATCH = "REPOSITORY_MISMATCH"
    PR_MISMATCH = "PR_MISMATCH"
    SHA_MISMATCH = "SHA_MISMATCH"
    STALE_ARTIFACT = "STALE_ARTIFACT"
    PERMISSION_ERROR = "PERMISSION_ERROR"
    TRUST_BOUNDARY_VIOLATION = "TRUST_BOUNDARY_VIOLATION"
    PATH_TRAVERSAL = "PATH_TRAVERSAL"
    WORKFLOW_CONFIGURATION_ERROR = "WORKFLOW_CONFIGURATION_ERROR"
    LABEL_MISSING = "LABEL_MISSING"
    DRAFT_PULL_REQUEST = "DRAFT_PULL_REQUEST"
    FORK_PULL_REQUEST = "FORK_PULL_REQUEST"
    BOT_PULL_REQUEST = "BOT_PULL_REQUEST"
    UNAUTHORIZED_ASSOCIATION = "UNAUTHORIZED_ASSOCIATION"
    REVIEW_NOT_READY = "REVIEW_NOT_READY"
    NO_BLOCKING_FINDINGS = "NO_BLOCKING_FINDINGS"
    DUPLICATE_PROPOSAL = "DUPLICATE_PROPOSAL"
    INVALID_PROPOSAL = "INVALID_PROPOSAL"
    PROTECTED_PATH = "PROTECTED_PATH"
    ORIGINAL_BLOB_MISMATCH = "ORIGINAL_BLOB_MISMATCH"
    FINDING_MISMATCH = "FINDING_MISMATCH"
    PATCH_DOES_NOT_APPLY = "PATCH_DOES_NOT_APPLY"


@dataclass(frozen=True)
class FixProposalFailure(Exception):
    failure_class: FailureClass
    code: FailureCode
    message: str
    operation: str

    def __str__(self) -> str:
        return f"{self.failure_class.value}/{self.code.value}: {self.message}"


@dataclass(frozen=True)
class FixProposalPolicy:
    proposal_policy: proposal_design.FixPolicy
    model: str
    reasoning_effort: str
    prompt_version: str
    max_prompt_bytes: int
    max_comment_patch_bytes: int
    policy_hash: str


@dataclass(frozen=True)
class GateDecision:
    should_generate: bool
    status: str
    code: str
    message: str
    input_hash: str = ""


@dataclass(frozen=True)
class RetrySuccess:
    value: Any
    attempts: int


class RetryExhausted(Exception):
    def __init__(self, failure: FixProposalFailure, attempts: int):
        super().__init__(failure.message)
        self.failure = failure
        self.attempts = attempts


def retryable(code: FailureCode, message: str, operation: str) -> FixProposalFailure:
    return FixProposalFailure(FailureClass.RETRYABLE, code, message, operation)


def fatal(code: FailureCode, message: str, operation: str) -> FixProposalFailure:
    return FixProposalFailure(FailureClass.FATAL, code, message, operation)


def from_stage1_failure(error: stage1.ReviewFailure) -> FixProposalFailure:
    failure_class = FailureClass(error.failure_class.value)
    code = FailureCode.__members__.get(error.code.name, FailureCode.NETWORK_ERROR)
    return FixProposalFailure(failure_class, code, error.message, error.operation)


def classify_exception(error: BaseException, operation: str) -> FixProposalFailure:
    if isinstance(error, FixProposalFailure):
        return error
    if isinstance(error, stage1.ReviewFailure):
        return from_stage1_failure(error)
    stage1_failure = stage1.classify_exception(error, operation)
    return from_stage1_failure(stage1_failure)


def run_with_retry(
    operation: str,
    func,
    *,
    max_attempts: int = MAX_ATTEMPTS,
    sleep_func=stage1.time.sleep,
) -> RetrySuccess:
    last_failure: FixProposalFailure | None = None
    for attempt in range(1, max_attempts + 1):
        print(f"{operation}: attempt {attempt}/{max_attempts}")
        try:
            return RetrySuccess(func(), attempt)
        except BaseException as error:
            failure = classify_exception(error, operation)
            last_failure = failure
            print(
                f"{operation}: {failure.failure_class.value} "
                f"{failure.code.value}: {sanitize_error(failure.message)}"
            )
            if failure.failure_class is FailureClass.FATAL:
                raise failure
            if attempt >= max_attempts:
                break
            delay = RETRY_DELAYS_SECONDS[attempt - 1]
            print(f"{operation}: waiting {delay} seconds before retry")
            sleep_func(delay)
    assert last_failure is not None
    raise RetryExhausted(last_failure, max_attempts)


def sanitize_error(message: str) -> str:
    sanitized = re.sub(r"gh[pousr]_[A-Za-z0-9_]+", "[redacted-token]", str(message))
    sanitized = re.sub(r"sk-[A-Za-z0-9_-]+", "[redacted-key]", sanitized)
    return sanitized[:500]


def github_output(values: dict[str, str]) -> None:
    stage1.github_output(values)


def write_job_summary(text: str) -> None:
    stage1.write_job_summary(text)


def required_env(name: str) -> str:
    return stage1.required_env(name)


def parse_simple_yaml_mapping(text: str) -> dict[str, Any]:
    return proposal_design.parse_simple_yaml_mapping(text)


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_hex_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_hex_json(value: Any) -> str:
    return sha256_hex_bytes(canonical_json_bytes(value))


def read_json_file(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise fatal(
            FailureCode.INVALID_JSON,
            f"{path.name} is not valid JSON: {exc.msg}",
            "json_parse",
        ) from exc


def load_fix_proposal_policy(path: Path) -> FixProposalPolicy:
    text = path.read_text(encoding="utf-8")
    raw = parse_simple_yaml_mapping(text)
    generator = raw.get("generator")
    limits = raw.get("limits")
    if not isinstance(generator, dict):
        raise fatal(
            FailureCode.WORKFLOW_CONFIGURATION_ERROR,
            "fix policy must define generator.model and generator.reasoning_effort",
            "fix_policy",
        )
    if not isinstance(limits, dict):
        raise fatal(
            FailureCode.WORKFLOW_CONFIGURATION_ERROR,
            "fix policy must define limits",
            "fix_policy",
        )
    model = str(generator.get("model", "")).strip()
    effort = str(generator.get("reasoning_effort", "")).strip()
    prompt_version = str(generator.get("prompt_version", "fix-proposal-v1")).strip()
    if not model:
        raise fatal(
            FailureCode.WORKFLOW_CONFIGURATION_ERROR,
            "fix policy generator.model is required",
            "fix_policy",
        )
    if not effort:
        raise fatal(
            FailureCode.WORKFLOW_CONFIGURATION_ERROR,
            "fix policy generator.reasoning_effort is required",
            "fix_policy",
        )
    policy = proposal_design.load_fix_policy(path)
    return FixProposalPolicy(
        proposal_policy=policy,
        model=model,
        reasoning_effort=effort,
        prompt_version=prompt_version,
        max_prompt_bytes=int(limits.get("max_prompt_bytes", 200000)),
        max_comment_patch_bytes=int(limits.get("max_comment_patch_bytes", 4000)),
        policy_hash=sha256_hex_bytes(text.encode("utf-8")),
    )


def labels_from_pull(pull: dict[str, Any]) -> set[str]:
    return {
        str(label.get("name", ""))
        for label in pull.get("labels", [])
        if isinstance(label, dict)
    }


def labels_from_request(request: dict[str, Any]) -> set[str]:
    raw_labels = request.get("labels", [])
    if not isinstance(raw_labels, list):
        return set()
    return {str(label) for label in raw_labels}


def ensure_full_sha(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not SHA_RE.fullmatch(value):
        raise fatal(
            FailureCode.INVALID_MANIFEST,
            f"{field_name} must be a full lowercase commit SHA",
            "manifest_validation",
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
        "collector_workflow_name",
        "collector_workflow_run_id",
    }
    if set(manifest) != required:
        raise fatal(
            FailureCode.INVALID_MANIFEST,
            "fix proposal request manifest has unexpected shape",
            "manifest_validation",
        )
    if manifest["schema_version"] != REQUEST_SCHEMA_VERSION:
        raise fatal(
            FailureCode.INVALID_MANIFEST,
            "unsupported fix proposal request schema",
            "manifest_validation",
        )
    if manifest["repository"] != EXPECTED_REPOSITORY:
        raise fatal(
            FailureCode.REPOSITORY_MISMATCH,
            "request repository does not match expected repository",
            "manifest_validation",
        )
    if not isinstance(manifest["pull_request_number"], int):
        raise fatal(
            FailureCode.INVALID_MANIFEST,
            "pull_request_number must be an integer",
            "manifest_validation",
        )
    ensure_full_sha(manifest["base_sha"], "base_sha")
    ensure_full_sha(manifest["head_sha"], "head_sha")
    if manifest["collector_workflow_name"] != COLLECTOR_WORKFLOW_NAME:
        raise fatal(
            FailureCode.WORKFLOW_CONFIGURATION_ERROR,
            "unexpected collector workflow name",
            "manifest_validation",
        )
    if not isinstance(manifest["labels"], list):
        raise fatal(
            FailureCode.INVALID_MANIFEST,
            "labels must be a list",
            "manifest_validation",
        )


def blocking_findings(review_result: dict[str, Any]) -> list[dict[str, Any]]:
    findings = review_result.get("findings", [])
    if not isinstance(findings, list):
        return []
    blocking: list[dict[str, Any]] = []
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        if finding.get("blocking") is True:
            blocking.append(finding)
            continue
        if str(finding.get("severity", "")).lower() in BLOCKING_SEVERITIES:
            blocking.append(finding)
    return blocking


def proposal_input_hash(
    *,
    request_manifest: dict[str, Any],
    review_result: dict[str, Any],
    policy_hash: str,
) -> str:
    return sha256_hex_json(
        {
            "repository": request_manifest["repository"],
            "pull_request_number": request_manifest["pull_request_number"],
            "base_sha": request_manifest["base_sha"],
            "head_sha": request_manifest["head_sha"],
            "policy_hash": policy_hash,
            "review_result_hash": sha256_hex_json(review_result),
            "blocking_findings": blocking_findings(review_result),
        }
    )


def existing_proposal_matches(
    proposals: Iterable[dict[str, Any]],
    *,
    head_sha: str,
    input_hash: str,
) -> bool:
    for proposal in proposals:
        metadata = proposal.get("metadata", proposal)
        if (
            metadata.get("head_sha") == head_sha
            and metadata.get("proposal_input_hash") == input_hash
            and metadata.get("status") == PROPOSAL_STATUS_READY
        ):
            return True
    return False


def evaluate_generation_gate(
    *,
    request_manifest: dict[str, Any],
    pull: dict[str, Any],
    review_result: dict[str, Any],
    policy: FixProposalPolicy,
    existing_proposals: Iterable[dict[str, Any]] = (),
) -> GateDecision:
    validate_request_manifest_shape(request_manifest)
    pull_number = int(pull.get("number", 0))
    request_number = int(request_manifest["pull_request_number"])
    if pull_number != request_number:
        raise fatal(FailureCode.PR_MISMATCH, "pull request number mismatch", "gate")
    current_head = str(pull.get("head", {}).get("sha", ""))
    current_base = str(pull.get("base", {}).get("sha", ""))
    if current_head != request_manifest["head_sha"] or current_base != request_manifest["base_sha"]:
        return GateDecision(False, PROPOSAL_STATUS_SKIPPED, FailureCode.STALE_ARTIFACT.value, "request artifact is stale")
    if policy.proposal_policy.proposal_label not in labels_from_pull(pull):
        return GateDecision(False, PROPOSAL_STATUS_SKIPPED, FailureCode.LABEL_MISSING.value, "ai-fix-proposal label is not present")
    if bool(pull.get("draft")):
        return GateDecision(False, PROPOSAL_STATUS_SKIPPED, FailureCode.DRAFT_PULL_REQUEST.value, "draft pull requests are skipped")
    if str(pull.get("head", {}).get("repo", {}).get("full_name", "")) != EXPECTED_REPOSITORY:
        return GateDecision(False, PROPOSAL_STATUS_SKIPPED, FailureCode.FORK_PULL_REQUEST.value, "fork pull requests are skipped")
    if str(pull.get("user", {}).get("type", "")) == "Bot":
        return GateDecision(False, PROPOSAL_STATUS_SKIPPED, FailureCode.BOT_PULL_REQUEST.value, "bot pull requests are skipped")
    if str(pull.get("author_association", "")) not in ALLOWED_AUTHOR_ASSOCIATIONS:
        return GateDecision(False, PROPOSAL_STATUS_SKIPPED, FailureCode.UNAUTHORIZED_ASSOCIATION.value, "author association is not allowed")
    if review_result.get("schema_version") != REVIEW_RESULT_SCHEMA_VERSION:
        raise fatal(FailureCode.INVALID_MANIFEST, "review result schema is invalid", "gate")
    if review_result.get("repository") != EXPECTED_REPOSITORY:
        raise fatal(FailureCode.REPOSITORY_MISMATCH, "review result repository mismatch", "gate")
    if int(review_result.get("pull_request_number", 0)) != request_number:
        raise fatal(FailureCode.PR_MISMATCH, "review result PR number mismatch", "gate")
    if review_result.get("reviewed_head_sha") != current_head:
        return GateDecision(False, PROPOSAL_STATUS_SKIPPED, FailureCode.SHA_MISMATCH.value, "Stage 1 reviewed SHA does not match current head")
    if review_result.get("base_sha") != current_base:
        return GateDecision(False, PROPOSAL_STATUS_SKIPPED, FailureCode.SHA_MISMATCH.value, "Stage 1 base SHA does not match current base")
    if review_result.get("review_status") != "completed":
        return GateDecision(False, PROPOSAL_STATUS_SKIPPED, FailureCode.REVIEW_NOT_READY.value, "Stage 1 review did not complete normally")
    if review_result.get("verdict") != "CHANGES_REQUESTED":
        return GateDecision(False, PROPOSAL_STATUS_SKIPPED, FailureCode.REVIEW_NOT_READY.value, "Stage 1 review verdict does not request changes")
    if not blocking_findings(review_result):
        return GateDecision(False, PROPOSAL_STATUS_SKIPPED, FailureCode.NO_BLOCKING_FINDINGS.value, "Stage 1 review has no blocking findings")
    input_hash = proposal_input_hash(
        request_manifest=request_manifest,
        review_result=review_result,
        policy_hash=policy.policy_hash,
    )
    if existing_proposal_matches(
        existing_proposals,
        head_sha=current_head,
        input_hash=input_hash,
    ):
        return GateDecision(False, PROPOSAL_STATUS_SKIPPED, FailureCode.DUPLICATE_PROPOSAL.value, "proposal already exists for this head and input")
    return GateDecision(True, "READY", "READY", "all Stage 2A gates passed", input_hash)


def parse_codex_json(final_message: str) -> dict[str, Any]:
    try:
        parsed = json.loads(final_message)
    except json.JSONDecodeError as exc:
        raise fatal(
            FailureCode.INVALID_JSON,
            "Codex fix proposal output must be JSON only",
            "proposal_parse",
        ) from exc
    if not isinstance(parsed, dict):
        raise fatal(
            FailureCode.INVALID_PROPOSAL,
            "Codex fix proposal output must be a JSON object",
            "proposal_parse",
        )
    return parsed


def canonicalize_proposal(
    proposal: dict[str, Any],
    *,
    request_manifest: dict[str, Any],
    review_result: dict[str, Any],
    policy: FixProposalPolicy,
    proposal_input_hash_value: str,
    generator_metadata: dict[str, Any],
) -> tuple[dict[str, Any], str, str]:
    canonical = json.loads(json.dumps(proposal, sort_keys=True))
    canonical["repository"] = request_manifest["repository"]
    canonical["pull_request_number"] = request_manifest["pull_request_number"]
    canonical["base_sha"] = request_manifest["base_sha"]
    canonical["head_sha"] = request_manifest["head_sha"]
    hash_source = {
        "repository": request_manifest["repository"],
        "pull_request_number": request_manifest["pull_request_number"],
        "base_sha": request_manifest["base_sha"],
        "head_sha": request_manifest["head_sha"],
        "policy_hash": policy.policy_hash,
        "proposal_input_hash": proposal_input_hash_value,
        "review_result_hash": sha256_hex_json(review_result),
        "generator_metadata": generator_metadata,
        "canonical_changes": canonical.get("changes", []),
        "findings_addressed": canonical.get("findings_addressed", []),
        "summary": canonical.get("summary", ""),
        "tests_recommended": canonical.get("tests_recommended", []),
        "risks": canonical.get("risks", []),
    }
    proposal_hash = sha256_hex_json(hash_source)
    canonical["proposal_id"] = proposal_hash[:32]
    return canonical, proposal_hash[:32], proposal_hash


def finding_ids(review_result: dict[str, Any]) -> set[str]:
    return {
        str(finding.get("finding_id", ""))
        for finding in blocking_findings(review_result)
        if isinstance(finding, dict)
    }


def validate_original_blobs(
    proposal: dict[str, Any],
    original_blob_shas: dict[str, str],
) -> None:
    for change in proposal.get("changes", []):
        path = str(change.get("path", ""))
        expected = original_blob_shas.get(path)
        if expected is None:
            raise fatal(
                FailureCode.ORIGINAL_BLOB_MISMATCH,
                f"no trusted blob SHA was supplied for {path}",
                "proposal_validation",
            )
        if expected != change.get("original_blob_sha"):
            raise fatal(
                FailureCode.ORIGINAL_BLOB_MISMATCH,
                f"original blob SHA mismatch for {path}",
                "proposal_validation",
            )


def blocking_finding_paths(review_result: dict[str, Any]) -> set[str]:
    return {
        str(finding.get("file", "")).strip()
        for finding in blocking_findings(review_result)
        if isinstance(finding, dict) and str(finding.get("file", "")).strip()
    }


def fetch_blob_text(
    *,
    repo: str,
    token: str,
    blob_sha: str,
) -> str:
    blob, _ = stage1.github_json(
        "GET",
        f"/repos/{repo}/git/blobs/{blob_sha}",
        token=token,
    )
    if not isinstance(blob, dict) or blob.get("encoding") != "base64":
        raise fatal(
            FailureCode.TRUST_BOUNDARY_VIOLATION,
            "trusted target blob could not be fetched as base64",
            "target_content",
        )
    try:
        decoded = base64.b64decode(str(blob.get("content", "")), validate=False)
        return decoded.decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        raise fatal(
            FailureCode.TRUST_BOUNDARY_VIOLATION,
            "trusted target blob is not UTF-8 text",
            "target_content",
        ) from exc


def trusted_target_contents(
    *,
    repo: str,
    token: str,
    files: list[dict[str, Any]],
    review_result: dict[str, Any],
    max_total_bytes: int,
) -> dict[str, Any]:
    file_by_path = {
        str(item.get("filename", "")): item
        for item in files
        if isinstance(item, dict)
    }
    records: list[dict[str, Any]] = []
    total_bytes = 0
    for path in sorted(blocking_finding_paths(review_result)):
        item = file_by_path.get(path)
        if not item:
            raise fatal(
                FailureCode.TRUST_BOUNDARY_VIOLATION,
                f"no trusted PR file metadata was found for {path}",
                "target_content",
            )
        if str(item.get("status", "")) == "removed":
            raise fatal(
                FailureCode.TRUST_BOUNDARY_VIOLATION,
                f"removed files cannot be fixed by Stage 2A proposals: {path}",
                "target_content",
            )
        blob_sha = str(item.get("sha", ""))
        if not SHA_RE.match(blob_sha):
            raise fatal(
                FailureCode.TRUST_BOUNDARY_VIOLATION,
                f"trusted blob SHA is missing for {path}",
                "target_content",
            )
        content = fetch_blob_text(repo=repo, token=token, blob_sha=blob_sha)
        content_bytes = len(content.encode("utf-8"))
        total_bytes += content_bytes
        if total_bytes > max_total_bytes:
            raise fatal(
                FailureCode.TRUST_BOUNDARY_VIOLATION,
                "trusted target content exceeds the prompt budget",
                "target_content",
            )
        records.append(
            {
                "path": path,
                "blob_sha": blob_sha,
                "content_sha256": sha256_hex_bytes(content.encode("utf-8")),
                "content": content,
            }
        )
    return {
        "schema_version": "fix-target-contents-v1",
        "files": records,
    }


def target_content_map(target_contents: dict[str, Any]) -> dict[str, dict[str, str]]:
    records: dict[str, dict[str, str]] = {}
    for item in target_contents.get("files", []):
        if not isinstance(item, dict):
            continue
        path = str(item.get("path", ""))
        content = str(item.get("content", ""))
        content_hash = str(item.get("content_sha256", ""))
        if sha256_hex_bytes(content.encode("utf-8")) != content_hash:
            raise fatal(
                FailureCode.TRUST_BOUNDARY_VIOLATION,
                f"trusted target content hash mismatch for {path}",
                "target_content",
            )
        records[path] = {
            "blob_sha": str(item.get("blob_sha", "")),
            "content": content,
        }
    return records


HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def validate_unified_patch_applies(
    *,
    path: str,
    patch: str,
    content: str,
) -> None:
    lines = patch.splitlines()
    if f"--- a/{path}" not in lines or f"+++ b/{path}" not in lines:
        raise fatal(
            FailureCode.PATCH_DOES_NOT_APPLY,
            f"patch headers do not match {path}",
            "proposal_validation",
        )
    original_lines = content.splitlines()
    hunk_count = 0
    index = 0
    while index < len(lines):
        header = HUNK_RE.match(lines[index])
        if not header:
            index += 1
            continue
        hunk_count += 1
        original_index = int(header.group(1)) - 1
        index += 1
        while index < len(lines):
            line = lines[index]
            if HUNK_RE.match(line):
                break
            if line.startswith("\\ No newline at end of file"):
                index += 1
                continue
            if not line:
                raise fatal(
                    FailureCode.PATCH_DOES_NOT_APPLY,
                    f"malformed empty patch line for {path}",
                    "proposal_validation",
                )
            marker = line[0]
            text = line[1:]
            if marker in {" ", "-"}:
                if original_index >= len(original_lines) or original_lines[original_index] != text:
                    raise fatal(
                        FailureCode.PATCH_DOES_NOT_APPLY,
                        f"patch hunk does not match trusted content for {path}",
                        "proposal_validation",
                    )
                original_index += 1
            elif marker == "+":
                pass
            else:
                raise fatal(
                    FailureCode.PATCH_DOES_NOT_APPLY,
                    f"unsupported patch line for {path}",
                    "proposal_validation",
                )
            index += 1
    if hunk_count == 0:
        raise fatal(
            FailureCode.PATCH_DOES_NOT_APPLY,
            f"patch has no hunks for {path}",
            "proposal_validation",
        )


def validate_patches_apply_to_targets(
    proposal: dict[str, Any],
    target_contents: dict[str, Any],
) -> None:
    targets = target_content_map(target_contents)
    for change in proposal.get("changes", []):
        path = str(change.get("path", ""))
        target = targets.get(path)
        if target is None:
            raise fatal(
                FailureCode.PATCH_DOES_NOT_APPLY,
                f"no trusted target content was supplied for {path}",
                "proposal_validation",
            )
        if target["blob_sha"] != str(change.get("original_blob_sha", "")):
            raise fatal(
                FailureCode.ORIGINAL_BLOB_MISMATCH,
                f"target content blob SHA mismatch for {path}",
                "proposal_validation",
            )
        validate_unified_patch_applies(
            path=path,
            patch=str(change.get("patch", "")),
            content=target["content"],
        )


def validate_finding_ids(proposal: dict[str, Any], review_result: dict[str, Any]) -> None:
    known_ids = finding_ids(review_result)
    for finding in proposal.get("findings_addressed", []):
        if str(finding.get("finding_id", "")) not in known_ids:
            raise fatal(
                FailureCode.FINDING_MISMATCH,
                "proposal references a finding ID not present in Stage 1 results",
                "proposal_validation",
            )


def validate_verified_proposal(
    proposal: dict[str, Any],
    *,
    request_manifest: dict[str, Any],
    review_result: dict[str, Any],
    policy: FixProposalPolicy,
    proposal_input_hash_value: str,
    original_blob_shas: dict[str, str],
    target_contents: dict[str, Any],
    generator_metadata: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    canonical, proposal_id, proposal_hash = canonicalize_proposal(
        proposal,
        request_manifest=request_manifest,
        review_result=review_result,
        policy=policy,
        proposal_input_hash_value=proposal_input_hash_value,
        generator_metadata=generator_metadata,
    )
    try:
        proposal_design.validate_schema_file()
        proposal_design.validate_fix_proposal(
            canonical,
            policy.proposal_policy,
            current_head_sha=request_manifest["head_sha"],
            expected_repository=request_manifest["repository"],
        )
    except proposal_design.ProposalValidationError as exc:
        code = FailureCode.PROTECTED_PATH if exc.code == "PROTECTED_PATH" else FailureCode.INVALID_PROPOSAL
        raise fatal(code, f"proposal validation failed: {exc.code}", "proposal_validation") from exc
    if canonical["base_sha"] != request_manifest["base_sha"]:
        raise fatal(FailureCode.SHA_MISMATCH, "proposal base SHA mismatch", "proposal_validation")
    if canonical["head_sha"] != request_manifest["head_sha"]:
        raise fatal(FailureCode.SHA_MISMATCH, "proposal head SHA mismatch", "proposal_validation")
    validate_finding_ids(canonical, review_result)
    validate_original_blobs(canonical, original_blob_shas)
    validate_patches_apply_to_targets(canonical, target_contents)
    metadata = {
        "schema_version": PROPOSAL_METADATA_SCHEMA_VERSION,
        "status": PROPOSAL_STATUS_READY,
        "proposal_id": proposal_id,
        "proposal_hash": proposal_hash,
        "proposal_input_hash": proposal_input_hash_value,
        "repository": request_manifest["repository"],
        "pull_request_number": request_manifest["pull_request_number"],
        "base_sha": request_manifest["base_sha"],
        "head_sha": request_manifest["head_sha"],
        "policy_hash": policy.policy_hash,
        "schema_id": "fix-proposal.schema.json",
        "generator_model": policy.model,
        "reasoning_effort": policy.reasoning_effort,
        "generated_at": dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z"),
        "source_review_run_id": review_result.get("workflow_run_id"),
        "source_review_artifact_id": review_result.get("review_artifact_id"),
        "source_review_hash": sha256_hex_json(review_result),
    }
    return canonical, metadata


def format_bytes(byte_count: int) -> str:
    return stage1.format_bytes(byte_count)


def proposal_comment_body(
    *,
    proposal: dict[str, Any],
    metadata: dict[str, Any],
    workflow_run_id: str,
    repo: str,
    max_patch_bytes: int = 4000,
) -> str:
    files = [change["path"] for change in proposal.get("changes", [])]
    findings = [
        finding["finding_id"]
        for finding in proposal.get("findings_addressed", [])
    ]
    patch_bytes = sum(
        len(str(change.get("patch", "")).encode("utf-8"))
        for change in proposal.get("changes", [])
    )
    patch_note = (
        "Patch details are stored in the workflow artifact."
        if patch_bytes > max_patch_bytes
        else "Patch details are intentionally omitted from the comment; see the artifact."
    )
    return "\n".join(
        [
            PROPOSAL_MARKER,
            "",
            "## AI Fix Proposal",
            "",
            "> Human approval is required. No file changes, patch application, tests, commit, push, or merge were performed.",
            "",
            f"- Status: `{metadata['status']}`",
            f"- Proposal ID: `{metadata['proposal_id']}`",
            f"- Target head SHA: `{metadata['head_sha']}`",
            f"- Proposal input hash: `{metadata['proposal_input_hash']}`",
            f"- Workflow run: [{workflow_run_id}](https://github.com/{repo}/actions/runs/{workflow_run_id})",
            f"- Proposal hash: `{metadata['proposal_hash'][:16]}`",
            f"- Findings addressed: `{', '.join(findings)}`",
            f"- Files: `{', '.join(files)}`",
            f"- Patch bytes: `{format_bytes(patch_bytes)}`",
            "",
            "### Change Summary",
            "",
            str(proposal.get("summary", "")),
            "",
            "### Risk",
            "",
            "\n".join(f"- {risk}" for risk in proposal.get("risks", [])) or "- None.",
            "",
            "### Recommended Tests",
            "",
            "\n".join(f"- {test}" for test in proposal.get("tests_recommended", [])) or "- None.",
            "",
            patch_note,
        ]
    )


def stale_comment_body(
    *,
    metadata: dict[str, Any],
    current_head_sha: str,
    workflow_run_id: str,
    repo: str,
) -> str:
    return "\n".join(
        [
            PROPOSAL_MARKER,
            "",
            "## AI Fix Proposal",
            "",
            f"- Status: `{PROPOSAL_STATUS_STALE}`",
            f"- Previous proposal ID: `{metadata.get('proposal_id', 'unknown')}`",
            f"- Previous target head SHA: `{metadata.get('head_sha', 'unknown')}`",
            f"- Current head SHA: `{current_head_sha}`",
            f"- Workflow run: [{workflow_run_id}](https://github.com/{repo}/actions/runs/{workflow_run_id})",
            "",
            "The pull request head changed. The previous proposal is not valid for application or approval.",
            "",
            "No file changes, patch application, tests, commit, push, or merge were performed.",
        ]
    )


def skipped_comment_body(
    *,
    status: str,
    code: str,
    message: str,
    pr_number: int,
    head_sha: str,
    workflow_run_id: str,
    repo: str,
) -> str:
    return "\n".join(
        [
            PROPOSAL_MARKER,
            "",
            "## AI Fix Proposal",
            "",
            f"- Status: `{status}`",
            f"- Reason: `{code}`",
            f"- Pull request: `#{pr_number}`",
            f"- Target head SHA: `{head_sha}`",
            f"- Workflow run: [{workflow_run_id}](https://github.com/{repo}/actions/runs/{workflow_run_id})",
            "",
            message,
            "",
            "No file changes, patch application, tests, commit, push, or merge were performed.",
        ]
    )


def write_verified_artifact(
    *,
    output_dir: Path,
    proposal: dict[str, Any],
    metadata: dict[str, Any],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "fix-proposal.json").write_text(
        json.dumps(proposal, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "proposal-metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def safe_extract_expected_zip(
    zip_bytes: bytes,
    target_dir: Path,
    *,
    expected_files: set[str],
    max_bytes: int,
) -> None:
    if len(zip_bytes) > max_bytes:
        raise retryable(
            FailureCode.ARTIFACT_TRANSIENT_ERROR,
            "downloaded artifact zip exceeds configured maximum",
            "artifact_download",
        )
    root = target_dir.resolve()
    if target_dir.exists():
        for child in target_dir.iterdir():
            if child.is_file():
                child.unlink()
    target_dir.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    with zipfile.ZipFile(io_bytes(zip_bytes)) as archive:
        for member in archive.infolist():
            if member.is_dir():
                raise fatal(
                    FailureCode.INVALID_MANIFEST,
                    "artifact directory entries are not allowed",
                    "artifact_download",
                )
            destination = (target_dir / member.filename).resolve()
            if root != destination and root not in destination.parents:
                raise fatal(
                    FailureCode.PATH_TRAVERSAL,
                    "artifact path traversal detected",
                    "artifact_download",
                )
            if member.filename not in expected_files:
                raise fatal(
                    FailureCode.INVALID_MANIFEST,
                    f"unexpected artifact member: {member.filename}",
                    "artifact_download",
                )
            if member.file_size > max_bytes:
                raise fatal(
                    FailureCode.INVALID_MANIFEST,
                    "artifact member exceeds configured maximum",
                    "artifact_download",
                )
            seen.add(member.filename)
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, destination.open("wb") as output:
                output.write(source.read())
    missing = expected_files.difference(seen)
    if missing:
        raise retryable(
            FailureCode.ARTIFACT_TRANSIENT_ERROR,
            f"artifact missing expected files: {sorted(missing)}",
            "artifact_download",
        )


def io_bytes(data: bytes):
    import io

    return io.BytesIO(data)


def download_artifact_by_name(
    *,
    repo: str,
    token: str,
    run_id: str,
    artifact_name: str,
    target_dir: Path,
    expected_files: set[str],
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
        raise retryable(
            FailureCode.ARTIFACT_TRANSIENT_ERROR,
            f"artifact {artifact_name} was not available yet",
            "artifact_download",
        )
    artifact_id = int(matching[0]["id"])
    data, _ = stage1.github_api_request(
        "GET",
        f"/repos/{repo}/actions/artifacts/{artifact_id}/zip",
        token=token,
        max_response_bytes=max_bytes,
        accept="application/zip",
    )
    safe_extract_expected_zip(
        data,
        target_dir,
        expected_files=expected_files,
        max_bytes=max_bytes,
    )
    return artifact_id


def command_download_request_artifact(_: argparse.Namespace) -> int:
    try:
        artifact_id = run_with_retry(
            "github_fix_request_artifact",
            lambda: download_artifact_by_name(
                repo=required_env("GITHUB_REPOSITORY"),
                token=required_env("GITHUB_TOKEN"),
                run_id=required_env("COLLECTOR_RUN_ID"),
                artifact_name=required_env("ARTIFACT_NAME"),
                target_dir=Path(required_env("FIX_REQUEST_DIR")),
                expected_files={"manifest.json", "review.diff"},
                max_bytes=int(required_env("MAX_ARTIFACT_BYTES")),
            ),
        ).value
        github_output({"request_artifact_id": str(artifact_id)})
        return 0
    except BaseException as error:
        return fail_command(error)


def list_pr_files(repo: str, pr_number: int, token: str) -> list[dict[str, Any]]:
    return list(stage1.iter_live_pr_files(repo, pr_number, token))


def blob_sha_map_from_files(files: Iterable[dict[str, Any]]) -> dict[str, str]:
    result: dict[str, str] = {}
    for file_info in files:
        filename = str(file_info.get("filename", ""))
        blob_sha = str(file_info.get("sha", ""))
        if filename and SHA_RE.fullmatch(blob_sha):
            result[filename] = blob_sha
    return result


def find_latest_review_result_artifact(
    *,
    repo: str,
    token: str,
    pr_number: int,
    head_sha: str,
    output_dir: Path,
    max_bytes: int,
) -> tuple[dict[str, Any], int]:
    runs_data, _ = stage1.github_json(
        "GET",
        f"/repos/{repo}/actions/workflows/architect-review.yml/runs?status=completed&per_page=50",
        token=token,
    )
    runs = runs_data.get("workflow_runs", []) if isinstance(runs_data, dict) else []
    for run in runs:
        if run.get("conclusion") != "success":
            continue
        run_id = str(run.get("id", ""))
        artifact_name = f"architect-review-result-{run_id}"
        try:
            artifact_id = download_artifact_by_name(
                repo=repo,
                token=token,
                run_id=run_id,
                artifact_name=artifact_name,
                target_dir=output_dir,
                expected_files={"architect-review-result.json"},
                max_bytes=max_bytes,
            )
        except FixProposalFailure as exc:
            if exc.failure_class is FailureClass.RETRYABLE:
                continue
            raise
        result = read_json_file(output_dir / "architect-review-result.json")
        if not isinstance(result, dict):
            continue
        if (
            result.get("pull_request_number") == pr_number
            and result.get("reviewed_head_sha") == head_sha
        ):
            return result, artifact_id
    raise fatal(
        FailureCode.REVIEW_NOT_READY,
        "no matching structured Stage 1 review result artifact was found",
        "stage1_review_lookup",
    )


def command_prepare_generation(_: argparse.Namespace) -> int:
    try:
        repo = required_env("GITHUB_REPOSITORY")
        token = required_env("GITHUB_TOKEN")
        request_dir = Path(required_env("FIX_REQUEST_DIR"))
        review_result_dir = Path(required_env("REVIEW_RESULT_DIR"))
        manifest = read_json_file(request_dir / "manifest.json")
        assert isinstance(manifest, dict)
        policy = load_fix_proposal_policy(Path(required_env("FIX_POLICY")))

        pull_data, _ = stage1.github_json(
            "GET",
            f"/repos/{repo}/pulls/{manifest['pull_request_number']}",
            token=token,
        )
        assert isinstance(pull_data, dict)
        review_result, review_artifact_id = run_with_retry(
            "github_stage1_review_artifact",
            lambda: find_latest_review_result_artifact(
                repo=repo,
                token=token,
                pr_number=int(manifest["pull_request_number"]),
                head_sha=str(manifest["head_sha"]),
                output_dir=review_result_dir,
                max_bytes=int(required_env("MAX_ARTIFACT_BYTES")),
            ),
        ).value
        files = run_with_retry(
            "github_pr_files",
            lambda: list_pr_files(repo, int(manifest["pull_request_number"]), token),
        ).value
        input_hash = proposal_input_hash(
            request_manifest=manifest,
            review_result=review_result,
            policy_hash=policy.policy_hash,
        )
        existing_comments = list(
            iter_fix_comments(repo, str(manifest["pull_request_number"]), token)
        )
        existing_proposals = existing_proposal_records_from_comments(existing_comments)
        gate = evaluate_generation_gate(
            request_manifest=manifest,
            pull=pull_data,
            review_result=review_result,
            policy=policy,
            existing_proposals=existing_proposals,
        )
        blob_map = blob_sha_map_from_files(files)
        (request_dir / "original-blob-shas.json").write_text(
            json.dumps(blob_map, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        target_contents = {"schema_version": "fix-target-contents-v1", "files": []}
        if gate.should_generate:
            target_contents = run_with_retry(
                "github_target_file_contents",
                lambda: trusted_target_contents(
                    repo=repo,
                    token=token,
                    files=files,
                    review_result=review_result,
                    max_total_bytes=policy.max_prompt_bytes,
                ),
            ).value
        (request_dir / "target-file-contents.json").write_text(
            json.dumps(target_contents, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        github_output(
            {
                "should_generate": "true" if gate.should_generate else "false",
                "status": gate.status,
                "reason_code": gate.code,
                "reason_message": gate.message,
                "pr_number": str(manifest["pull_request_number"]),
                "base_sha": str(manifest["base_sha"]),
                "head_sha": str(manifest["head_sha"]),
                "review_artifact_id": str(review_artifact_id),
                "proposal_input_hash": input_hash,
                "original_blob_shas": json.dumps(blob_map, sort_keys=True),
                "target_file_count": str(len(target_contents.get("files", []))),
                "blocking_findings": str(len(blocking_findings(review_result))),
            }
        )
        write_job_summary(
            "\n".join(
                [
                    "## Fix Proposal Gate",
                    "",
                    f"- Status: `{gate.status}`",
                    f"- Reason: `{gate.code}`",
                    f"- PR: `#{manifest['pull_request_number']}`",
                    f"- Head SHA: `{manifest['head_sha']}`",
                    f"- Blocking findings: `{len(blocking_findings(review_result))}`",
                ]
            )
        )
        return 0
    except BaseException as error:
        return fail_command(error)


def parse_blob_sha_map(raw: str) -> dict[str, str]:
    if not raw.strip():
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise fatal(
            FailureCode.INVALID_MANIFEST,
            "blob SHA map must be a JSON object",
            "blob_sha_map",
        )
    return {str(path): str(sha) for path, sha in data.items()}


def extract_issue_comment_id(comment: dict[str, Any]) -> str:
    return str(comment.get("id", ""))


def existing_proposal_records_from_comments(
    comments: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for comment in comments:
        body = comment.get("body")
        if not isinstance(body, str) or PROPOSAL_MARKER not in body:
            continue
        head_match = re.search(r"Target head SHA:\s*`([0-9a-f]{40})`", body)
        input_match = re.search(r"Proposal input hash:\s*`([0-9a-f]{64})`", body)
        status_match = re.search(r"Status:\s*`([^`]+)`", body)
        if head_match and input_match:
            records.append(
                {
                    "metadata": {
                        "head_sha": head_match.group(1),
                        "proposal_input_hash": input_match.group(1),
                        "status": status_match.group(1) if status_match else "",
                    }
                }
            )
    return records


def iter_fix_comments(repo: str, issue_number: str, token: str) -> Iterable[dict[str, Any]]:
    for comment in stage1.iter_issue_comments(repo, issue_number, token):
        if isinstance(comment.get("body"), str) and PROPOSAL_MARKER in comment["body"]:
            yield comment


def post_or_update_comment(
    *,
    repo: str,
    issue_number: str,
    token: str,
    body: str,
) -> None:
    comments = list(iter_fix_comments(repo, issue_number, token))
    existing = comments[0] if comments else None
    if existing:
        stage1.github_json(
            "PATCH",
            f"/repos/{repo}/issues/comments/{existing['id']}",
            token=token,
            body={"body": body},
        )
    else:
        stage1.github_json(
            "POST",
            f"/repos/{repo}/issues/{issue_number}/comments",
            token=token,
            body={"body": body},
        )


def command_load_policy(_: argparse.Namespace) -> int:
    try:
        policy = load_fix_proposal_policy(Path(required_env("FIX_POLICY")))
        github_output(
            {
                "model": policy.model,
                "effort": policy.reasoning_effort,
                "prompt_version": policy.prompt_version,
                "policy_hash": policy.policy_hash,
                "max_prompt_bytes": str(policy.max_prompt_bytes),
                "max_comment_patch_bytes": str(policy.max_comment_patch_bytes),
                "max_changed_files": str(policy.proposal_policy.max_changed_files),
                "max_patch_bytes": str(policy.proposal_policy.max_patch_bytes),
                "max_file_patch_bytes": str(policy.proposal_policy.max_file_patch_bytes),
            }
        )
        write_job_summary(
            "\n".join(
                [
                    "## Fix Proposal Policy",
                    "",
                    f"- Model: `{policy.model}`",
                    f"- Reasoning: `{policy.reasoning_effort}`",
                    f"- Max changed files: `{policy.proposal_policy.max_changed_files}`",
                    f"- Max patch bytes: `{policy.proposal_policy.max_patch_bytes}`",
                    f"- Prompt limit: `{format_bytes(policy.max_prompt_bytes)}`",
                ]
            )
        )
        return 0
    except BaseException as error:
        return fail_command(error)


def command_verify_prompt(_: argparse.Namespace) -> int:
    try:
        prompt = Path(required_env("TRUSTED_PROMPT"))
        if not prompt.is_file():
            raise fatal(
                FailureCode.TRUSTED_PROMPT_MISSING,
                "trusted fix proposal prompt is missing",
                "trusted_prompt",
            )
        prompt_bytes = prompt.stat().st_size
        max_prompt_bytes = int(required_env("MAX_PROMPT_BYTES"))
        if prompt_bytes > max_prompt_bytes:
            raise fatal(
                FailureCode.WORKFLOW_CONFIGURATION_ERROR,
                "trusted prompt exceeds max prompt bytes",
                "trusted_prompt",
            )
        github_output({"prompt_ok": "true", "prompt_bytes": str(prompt_bytes)})
        return 0
    except BaseException as error:
        return fail_command(error)


def fail_command(error: BaseException) -> int:
    if isinstance(error, RetryExhausted):
        failure = error.failure
        write_job_summary(
            "\n".join(
                [
                    "## Fix Proposal Failure",
                    "",
                    f"- failure class: `{failure.failure_class.value}`",
                    f"- failure code: `{failure.code.value}`",
                    f"- failed operation: `{failure.operation}`",
                    f"- attempts: `{error.attempts}`",
                    f"- last error: `{sanitize_error(failure.message)}`",
                    "",
                    "Automatic processing stopped. A human should inspect the workflow logs.",
                ]
            )
        )
        return 1
    if isinstance(error, stage1.RetryExhausted):
        failure = error.failure
        summary = stage1.failure_summary(failure, attempts=error.attempts)
        write_job_summary(summary)
        return 1
    if isinstance(error, FixProposalFailure):
        write_job_summary(
            "\n".join(
                [
                    "## Fix Proposal Failure",
                    "",
                    f"- failure class: `{error.failure_class.value}`",
                    f"- failure code: `{error.code.value}`",
                    f"- failed operation: `{error.operation}`",
                    f"- attempts: `0`",
                    f"- last error: `{sanitize_error(error.message)}`",
                    "",
                    "Automatic processing stopped. A human should inspect the workflow logs.",
                ]
            )
        )
        return 1
    return stage1.fail_command(error)


def command_validate_request(_: argparse.Namespace) -> int:
    try:
        root = Path(required_env("FIX_REQUEST_DIR"))
        manifest = read_json_file(root / "manifest.json")
        assert isinstance(manifest, dict)
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
        return fail_command(error)


def command_finalize_proposal(_: argparse.Namespace) -> int:
    try:
        request_manifest = read_json_file(Path(required_env("FIX_REQUEST_DIR")) / "manifest.json")
        review_result = read_json_file(Path(required_env("REVIEW_RESULT_PATH")))
        assert isinstance(request_manifest, dict)
        assert isinstance(review_result, dict)
        policy = load_fix_proposal_policy(Path(required_env("FIX_POLICY")))
        proposal_input_hash_value = required_env("PROPOSAL_INPUT_HASH")
        original_blob_shas = parse_blob_sha_map(os.environ.get("ORIGINAL_BLOB_SHAS", "{}"))
        target_contents = read_json_file(Path(required_env("TRUSTED_TARGET_CONTENTS_PATH")))
        assert isinstance(target_contents, dict)
        generator_metadata = {
            "model": policy.model,
            "reasoning_effort": policy.reasoning_effort,
            "policy_version": policy.policy_hash,
        }
        proposal = parse_codex_json(os.environ.get("CODEX_FINAL_MESSAGE", ""))
        verified, metadata = validate_verified_proposal(
            proposal,
            request_manifest=request_manifest,
            review_result=review_result,
            policy=policy,
            proposal_input_hash_value=proposal_input_hash_value,
            original_blob_shas=original_blob_shas,
            target_contents=target_contents,
            generator_metadata=generator_metadata,
        )
        output_dir = Path(required_env("PROPOSAL_OUTPUT_DIR"))
        write_verified_artifact(output_dir=output_dir, proposal=verified, metadata=metadata)
        github_output(
            {
                "proposal_ready": "true",
                "proposal_id": metadata["proposal_id"],
                "proposal_hash": metadata["proposal_hash"],
                "proposal_input_hash": metadata["proposal_input_hash"],
                "artifact_name": f"fix-proposal-{metadata['proposal_id']}",
            }
        )
        write_job_summary(
            "\n".join(
                [
                    "## Fix Proposal",
                    "",
                    f"- Status: `{metadata['status']}`",
                    f"- Proposal ID: `{metadata['proposal_id']}`",
                    f"- Proposal hash: `{metadata['proposal_hash'][:16]}`",
                    f"- Files: `{len(verified.get('changes', []))}`",
                ]
            )
        )
        return 0
    except BaseException as error:
        return fail_command(error)


def command_post_comment(_: argparse.Namespace) -> int:
    try:
        repo = required_env("GITHUB_REPOSITORY")
        token = required_env("GITHUB_TOKEN")
        issue_number = required_env("PR_NUMBER")
        workflow_run_id = required_env("WORKFLOW_RUN_ID")
        proposal_path = Path(os.environ.get("PROPOSAL_PATH", ""))
        metadata_path = Path(os.environ.get("PROPOSAL_METADATA_PATH", ""))
        if proposal_path.is_file() and metadata_path.is_file():
            proposal = read_json_file(proposal_path)
            metadata = read_json_file(metadata_path)
            body = proposal_comment_body(
                proposal=proposal,
                metadata=metadata,
                workflow_run_id=workflow_run_id,
                repo=repo,
                max_patch_bytes=int(os.environ.get("MAX_COMMENT_PATCH_BYTES", "4000")),
            )
        else:
            body = skipped_comment_body(
                status=os.environ.get("STATUS", PROPOSAL_STATUS_SKIPPED),
                code=os.environ.get("REASON_CODE", "UNKNOWN"),
                message=os.environ.get("REASON_MESSAGE", "Fix proposal was not generated."),
                pr_number=int(issue_number),
                head_sha=os.environ.get("HEAD_SHA", ""),
                workflow_run_id=workflow_run_id,
                repo=repo,
            )
        run_with_retry(
            "github_fix_proposal_comment",
            lambda: (
                stage1.validate_comment_target(repo, issue_number, required_env("HEAD_SHA"), token),
                post_or_update_comment(
                    repo=repo,
                    issue_number=issue_number,
                    token=token,
                    body=body,
                ),
            ),
        )
        return 0
    except BaseException as error:
        return fail_command(error)


def command_self_check(_: argparse.Namespace) -> int:
    text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((Path(__file__).resolve().parents[1] / ".github" / "workflows").glob("*.y*ml"))
    )
    lowered = text.lower()
    for token in FORBIDDEN_AUTOMATION_TOKENS:
        if token.lower() in lowered:
            raise SystemExit(f"forbidden automation token found: {token}")
    if "workflow_dispatch:" in text:
        raise SystemExit("Stage 2A workflows must not use workflow_dispatch")
    if "contents: write" in text:
        raise SystemExit("Stage 2A workflows must not request contents: write")
    print("Stage 2A workflow self-check passed.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("load-policy").set_defaults(func=command_load_policy)
    subparsers.add_parser("verify-prompt").set_defaults(func=command_verify_prompt)
    subparsers.add_parser("download-request-artifact").set_defaults(
        func=command_download_request_artifact
    )
    subparsers.add_parser("validate-request").set_defaults(func=command_validate_request)
    subparsers.add_parser("prepare-generation").set_defaults(
        func=command_prepare_generation
    )
    subparsers.add_parser("finalize-proposal").set_defaults(func=command_finalize_proposal)
    subparsers.add_parser("post-comment").set_defaults(func=command_post_comment)
    subparsers.add_parser("self-check").set_defaults(func=command_self_check)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
