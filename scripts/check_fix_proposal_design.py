#!/usr/bin/env python3
"""Validate Stage 2 fix proposal design artifacts.

This script is intentionally read-only. It validates the design contract,
policy file, schema shape, and sample proposal objects, but it never applies
patches, writes repository files, contacts GitHub, commits, pushes, or merges.
"""

from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DESIGN_DOC_PATH = REPO_ROOT / "docs" / "stage2-fix-proposal-design.md"
AI_LOOP_DOC_PATH = REPO_ROOT / "docs" / "ai-development-loop.md"
FIX_POLICY_PATH = REPO_ROOT / ".github" / "codex" / "fix-policy.yml"
FIX_SCHEMA_PATH = (
    REPO_ROOT / ".github" / "codex" / "schemas" / "fix-proposal.schema.json"
)
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
FIX_PROPOSAL_RUNTIME_PATH = REPO_ROOT / "scripts" / "fix_proposal_generator.py"
EXPECTED_REPOSITORY = "Vectology-cloud-team/namma-rogue-agent"
FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DATE_TIME_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    r"(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)
PROPOSAL_MARKER = "<!-- namma-ai-fix-proposal -->"
STAGE2_LABEL = "ai-fix-proposal"
STAGE2_APPROVAL_LABEL = "ai-fix-approved"
ALLOWED_APPROVERS = {"OWNER", "MEMBER"}
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
)
REQUIRED_PROTECTED_PATHS = {
    ".git/**",
    ".github/workflows/**",
    ".github/actions/**",
    ".github/codex/prompts/**",
    ".github/codex/review-policy.yml",
    ".github/codex/fix-policy.yml",
    ".github/codex/schemas/**",
    "*.pem",
    "**/*.pem",
    "*.key",
    "**/*.key",
    "*secret*",
    "**/*secret*",
    "*credential*",
    "**/*credential*",
    "*token*",
    "**/*token*",
}
PROPOSAL_KEYS = {
    "schema_version",
    "proposal_id",
    "repository",
    "pull_request_number",
    "base_sha",
    "head_sha",
    "source_review_run_id",
    "source_review_artifact_id",
    "reviewed_at",
    "generator",
    "summary",
    "findings_addressed",
    "changes",
    "tests_recommended",
    "risks",
    "human_approval_required",
}
GENERATOR_KEYS = {"model", "reasoning_effort", "policy_version"}
FINDING_KEYS = {"finding_id", "severity", "category"}
FINDING_SEVERITIES = {"critical", "high", "medium", "low"}
CHANGE_KEYS = {"path", "operation", "original_blob_sha", "patch", "rationale"}


@dataclass(frozen=True)
class FixPolicy:
    schema_version: int
    proposal_label: str
    approval_label: str
    max_changed_files: int
    max_patch_bytes: int
    max_file_patch_bytes: int
    allowed_operations: tuple[str, ...]
    protected_paths: tuple[str, ...]


@dataclass(frozen=True)
class CheckResult:
    label: str
    passed: bool
    detail: str = ""


class ProposalValidationError(ValueError):
    """Raised when a fix proposal violates the Stage 2 design contract."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def strip_yaml_scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def parse_simple_yaml_mapping(text: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
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
                data[key] = strip_yaml_scalar(value)
                current_section = None
            else:
                data[key] = [] if key in {"allowed_operations", "protected_paths"} else {}
                current_section = key
            continue
        if current_section is None:
            raise ProposalValidationError(
                "INVALID_POLICY",
                "unexpected indented policy line",
            )
        stripped = line.strip()
        if stripped.startswith("- "):
            if not isinstance(data[current_section], list):
                raise ProposalValidationError(
                    "INVALID_POLICY",
                    f"section {current_section} is not a list",
                )
            data[current_section].append(strip_yaml_scalar(stripped[2:]))
            continue
        key, _, value = stripped.partition(":")
        if not value:
            raise ProposalValidationError(
                "INVALID_POLICY",
                "nested policy objects deeper than one level are not supported",
            )
        if not isinstance(data[current_section], dict):
            raise ProposalValidationError(
                "INVALID_POLICY",
                f"section {current_section} is not a mapping",
            )
        data[current_section][key.strip()] = strip_yaml_scalar(value)
    return data


def parse_int(value: Any, field_name: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ProposalValidationError(
            "INVALID_POLICY",
            f"{field_name} must be an integer",
        ) from exc
    if parsed <= 0:
        raise ProposalValidationError(
            "INVALID_POLICY",
            f"{field_name} must be positive",
        )
    return parsed


def load_fix_policy(path: Path = FIX_POLICY_PATH) -> FixPolicy:
    raw = parse_simple_yaml_mapping(read_text(path))
    labels = raw.get("labels")
    limits = raw.get("limits")
    operations = raw.get("allowed_operations")
    protected = raw.get("protected_paths")
    if not isinstance(labels, dict) or not isinstance(limits, dict):
        raise ProposalValidationError("INVALID_POLICY", "labels and limits are required")
    if not isinstance(operations, list) or not isinstance(protected, list):
        raise ProposalValidationError(
            "INVALID_POLICY",
            "allowed_operations and protected_paths are required",
        )
    policy = FixPolicy(
        schema_version=parse_int(raw.get("schema_version"), "schema_version"),
        proposal_label=str(labels.get("proposal", "")),
        approval_label=str(labels.get("approval", "")),
        max_changed_files=parse_int(
            limits.get("max_changed_files"),
            "limits.max_changed_files",
        ),
        max_patch_bytes=parse_int(
            limits.get("max_patch_bytes"),
            "limits.max_patch_bytes",
        ),
        max_file_patch_bytes=parse_int(
            limits.get("max_file_patch_bytes"),
            "limits.max_file_patch_bytes",
        ),
        allowed_operations=tuple(str(item) for item in operations),
        protected_paths=tuple(str(item) for item in protected),
    )
    validate_fix_policy(policy)
    return policy


def validate_fix_policy(policy: FixPolicy) -> None:
    if policy.schema_version != 1:
        raise ProposalValidationError("INVALID_POLICY", "unsupported policy version")
    if policy.proposal_label != STAGE2_LABEL:
        raise ProposalValidationError("INVALID_POLICY", "unexpected proposal label")
    if policy.approval_label != STAGE2_APPROVAL_LABEL:
        raise ProposalValidationError("INVALID_POLICY", "unexpected approval label")
    if policy.proposal_label == policy.approval_label:
        raise ProposalValidationError(
            "INVALID_POLICY",
            "proposal and approval labels must differ",
        )
    if policy.allowed_operations != ("modify",):
        raise ProposalValidationError(
            "INVALID_POLICY",
            "Stage 2 initial design only allows modify",
        )
    missing = REQUIRED_PROTECTED_PATHS.difference(policy.protected_paths)
    if missing:
        raise ProposalValidationError(
            "INVALID_POLICY",
            f"missing protected paths: {sorted(missing)}",
        )


def normalize_repo_path(path: str) -> str:
    return path.replace("\\", "/").lstrip("/")


def reject_path(path: str, policy: FixPolicy) -> str:
    if "\\" in path:
        raise ProposalValidationError(
            "INVALID_PATH",
            "backslash paths are forbidden",
        )
    normalized = normalize_repo_path(path)
    if not normalized or normalized != path:
        raise ProposalValidationError("INVALID_PATH", "path must be relative")
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:/", normalized):
        raise ProposalValidationError("INVALID_PATH", "absolute paths are forbidden")
    if any(part == ".." for part in normalized.split("/")):
        raise ProposalValidationError("PATH_TRAVERSAL", "path traversal is forbidden")
    lowered = normalized.lower()
    if any(keyword in lowered for keyword in ("secret", "credential", "token")):
        raise ProposalValidationError(
            "PROTECTED_PATH",
            "secret, credential, and token paths are forbidden",
        )
    for pattern in policy.protected_paths:
        if fnmatch.fnmatchcase(lowered, pattern.lower()):
            raise ProposalValidationError(
                "PROTECTED_PATH",
                f"{normalized} is protected",
            )
    return normalized


def reject_unexpected_keys(
    obj: dict[str, Any],
    allowed: set[str],
    context: str,
) -> None:
    extra = set(obj).difference(allowed)
    if extra:
        raise ProposalValidationError(
            "INVALID_PROPOSAL",
            f"{context} has unexpected fields: {sorted(extra)}",
        )
    missing = allowed.difference(obj)
    if missing:
        raise ProposalValidationError(
            "INVALID_PROPOSAL",
            f"{context} is missing fields: {sorted(missing)}",
        )


def require_full_sha(value: Any, field_name: str) -> None:
    if not isinstance(value, str) or not FULL_SHA_RE.fullmatch(value):
        raise ProposalValidationError(
            "INVALID_SHA",
            f"{field_name} must be a full lowercase SHA",
        )


def require_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProposalValidationError("INVALID_PROPOSAL", f"{field_name} is required")
    return value


def require_positive_int(value: Any, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ProposalValidationError(
            "INVALID_PROPOSAL",
            f"{field_name} must be a positive integer",
        )
    return value


def proposal_content_hash(proposal: dict[str, Any]) -> str:
    encoded = json.dumps(
        proposal,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def parse_patch_paths(patch: str) -> set[str]:
    paths: set[str] = set()
    for line in patch.splitlines():
        if line.startswith("diff --git "):
            if '"' in line:
                raise ProposalValidationError(
                    "PATCH_PATH_MISMATCH",
                    "quoted diff paths are forbidden",
                )
            parts = line.split()
            if len(parts) != 4:
                raise ProposalValidationError(
                    "PATCH_PATH_MISMATCH",
                    "diff header must contain exactly two paths",
                )
            for raw in parts[2:4]:
                if raw.startswith(("a/", "b/")):
                    paths.add(normalize_repo_path(raw[2:]))
        elif line.startswith(("--- ", "+++ ")):
            raw = line[4:].strip().split("\t", 1)[0]
            if raw.startswith('"'):
                raise ProposalValidationError(
                    "PATCH_PATH_MISMATCH",
                    "quoted patch paths are forbidden",
                )
            if raw == "/dev/null":
                continue
            if raw.startswith(("a/", "b/")):
                paths.add(normalize_repo_path(raw[2:]))
    return paths


def validate_patch(change: dict[str, Any], policy: FixPolicy) -> None:
    path = require_string(change.get("path"), "changes.path")
    patch = require_string(change.get("patch"), "changes.patch")
    patch_bytes = len(patch.encode("utf-8"))
    if patch_bytes > policy.max_file_patch_bytes:
        raise ProposalValidationError(
            "PATCH_TOO_LARGE",
            "file patch exceeds max_file_patch_bytes",
        )
    if any(marker in patch for marker in FORBIDDEN_PATCH_MARKERS):
        raise ProposalValidationError(
            "FORBIDDEN_PATCH_KIND",
            "binary, mode, rename, create, or delete patches are forbidden",
        )
    for line in patch.splitlines():
        if line.startswith(("--- ", "+++ ")):
            raw = line[4:].strip().split("\t", 1)[0]
            if raw == "/dev/null":
                raise ProposalValidationError(
                    "FORBIDDEN_PATCH_KIND",
                    "/dev/null create and delete patches are forbidden",
                )
    patch_paths = parse_patch_paths(patch)
    if not patch_paths:
        raise ProposalValidationError(
            "PATCH_PATH_MISMATCH",
            "patch must identify its target path",
        )
    if patch_paths != {normalize_repo_path(path)}:
        raise ProposalValidationError(
            "PATCH_PATH_MISMATCH",
            "patch target path must match changes.path",
        )


def validate_fix_proposal(
    proposal: dict[str, Any],
    policy: FixPolicy | None = None,
    *,
    current_head_sha: str | None = None,
    expected_repository: str = EXPECTED_REPOSITORY,
) -> None:
    policy = policy or load_fix_policy()
    reject_unexpected_keys(proposal, PROPOSAL_KEYS, "proposal")
    if proposal.get("schema_version") != "1.0":
        raise ProposalValidationError("INVALID_PROPOSAL", "schema_version must be 1.0")
    if proposal.get("repository") != expected_repository:
        raise ProposalValidationError("REPOSITORY_MISMATCH", "repository mismatch")
    proposal_id = require_string(proposal.get("proposal_id"), "proposal_id")
    if not 8 <= len(proposal_id) <= 128:
        raise ProposalValidationError(
            "INVALID_PROPOSAL",
            "proposal_id must be 8 to 128 characters",
        )
    require_positive_int(proposal.get("pull_request_number"), "pull_request_number")
    require_full_sha(proposal.get("base_sha"), "base_sha")
    require_full_sha(proposal.get("head_sha"), "head_sha")
    if current_head_sha is not None and proposal["head_sha"] != current_head_sha:
        raise ProposalValidationError("STALE_HEAD_SHA", "proposal head SHA is stale")
    if proposal.get("human_approval_required") is not True:
        raise ProposalValidationError(
            "HUMAN_APPROVAL_REQUIRED",
            "human_approval_required must be true",
        )
    require_positive_int(proposal.get("source_review_run_id"), "source_review_run_id")
    require_string(proposal.get("source_review_artifact_id"), "source_review_artifact_id")
    try:
        reviewed_at = require_string(proposal.get("reviewed_at"), "reviewed_at")
        if not DATE_TIME_RE.fullmatch(reviewed_at):
            raise ValueError("reviewed_at is not RFC3339 date-time")
        dt.datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProposalValidationError(
            "INVALID_PROPOSAL",
            "reviewed_at must be ISO-8601",
        ) from exc
    generator = proposal.get("generator")
    if not isinstance(generator, dict):
        raise ProposalValidationError("INVALID_PROPOSAL", "generator is required")
    reject_unexpected_keys(generator, GENERATOR_KEYS, "generator")
    for field_name in ("model", "reasoning_effort", "policy_version"):
        require_string(generator.get(field_name), f"generator.{field_name}")
    require_string(proposal.get("summary"), "summary")
    findings = proposal.get("findings_addressed")
    if not isinstance(findings, list) or not findings:
        raise ProposalValidationError(
            "INVALID_PROPOSAL",
            "at least one finding must be addressed",
        )
    for finding in findings:
        if not isinstance(finding, dict):
            raise ProposalValidationError(
                "INVALID_PROPOSAL",
                "finding must be object",
            )
        reject_unexpected_keys(finding, FINDING_KEYS, "finding")
        for field_name in FINDING_KEYS:
            require_string(finding.get(field_name), f"finding.{field_name}")
        if finding["severity"] not in FINDING_SEVERITIES:
            raise ProposalValidationError(
                "INVALID_PROPOSAL",
                "finding severity is invalid",
            )
    changes = proposal.get("changes")
    if not isinstance(changes, list) or not changes:
        raise ProposalValidationError(
            "INVALID_PROPOSAL",
            "at least one change is required",
        )
    if len(changes) > policy.max_changed_files:
        raise ProposalValidationError(
            "TOO_MANY_FILES",
            "proposal exceeds max_changed_files",
        )
    paths: set[str] = set()
    total_patch_bytes = 0
    for change in changes:
        if not isinstance(change, dict):
            raise ProposalValidationError("INVALID_PROPOSAL", "change must be object")
        reject_unexpected_keys(change, CHANGE_KEYS, "change")
        path = require_string(change.get("path"), "changes.path")
        normalized_path = reject_path(path, policy)
        if normalized_path in paths:
            raise ProposalValidationError("DUPLICATE_PATH", "duplicate change path")
        paths.add(normalized_path)
        if change.get("operation") not in policy.allowed_operations:
            raise ProposalValidationError(
                "FORBIDDEN_OPERATION",
                "only modify is allowed",
            )
        require_full_sha(change.get("original_blob_sha"), "original_blob_sha")
        validate_patch(change, policy)
        total_patch_bytes += len(str(change["patch"]).encode("utf-8"))
    if total_patch_bytes > policy.max_patch_bytes:
        raise ProposalValidationError(
            "PATCH_TOO_LARGE",
            "proposal exceeds max_patch_bytes",
        )
    tests_recommended = proposal.get("tests_recommended")
    if not isinstance(tests_recommended, list):
        raise ProposalValidationError(
            "INVALID_PROPOSAL",
            "tests_recommended must be a list",
        )
    for test in tests_recommended:
        require_string(test, "tests_recommended[]")
    risks = proposal.get("risks")
    if not isinstance(risks, list):
        raise ProposalValidationError(
            "INVALID_PROPOSAL",
            "risks must be a list",
        )
    for risk in risks:
        require_string(risk, "risks[]")


def validate_approval_gate(
    proposal: dict[str, Any],
    policy: FixPolicy,
    *,
    labels: set[str],
    approver_association: str,
    current_head_sha: str,
    approved_head_sha: str,
    approved_proposal_id: str,
    approved_proposal_hash: str,
) -> None:
    if policy.proposal_label not in labels:
        raise ProposalValidationError(
            "LABEL_GATE_CLOSED",
            "proposal label is required",
        )
    if policy.approval_label not in labels:
        raise ProposalValidationError(
            "APPROVAL_MISSING",
            "approval label is required",
        )
    if approver_association not in ALLOWED_APPROVERS:
        raise ProposalValidationError(
            "APPROVER_NOT_ALLOWED",
            "approval must come from OWNER or MEMBER",
        )
    if not approved_proposal_id or not approved_proposal_hash or not approved_head_sha:
        raise ProposalValidationError(
            "APPROVAL_BINDING_MISSING",
            "trusted approval record must bind proposal ID, hash, and head SHA",
        )
    if proposal["head_sha"] != current_head_sha or approved_head_sha != current_head_sha:
        raise ProposalValidationError(
            "STALE_APPROVAL",
            "head SHA changed after proposal or approval",
        )
    if proposal["proposal_id"] != approved_proposal_id:
        raise ProposalValidationError(
            "PROPOSAL_ID_MISMATCH",
            "approval must name the current proposal ID",
        )
    if proposal_content_hash(proposal) != approved_proposal_hash:
        raise ProposalValidationError(
            "PROPOSAL_HASH_MISMATCH",
            "approval hash must match proposal content",
        )


def validate_schema_file(path: Path = FIX_SCHEMA_PATH) -> dict[str, Any]:
    schema = json.loads(read_text(path))
    required = set(schema.get("required", []))
    expected = {
        "schema_version",
        "proposal_id",
        "repository",
        "pull_request_number",
        "base_sha",
        "head_sha",
        "source_review_run_id",
        "source_review_artifact_id",
        "reviewed_at",
        "generator",
        "summary",
        "findings_addressed",
        "changes",
        "tests_recommended",
        "risks",
        "human_approval_required",
    }
    if not expected.issubset(required):
        raise ProposalValidationError("INVALID_SCHEMA", "schema missing required keys")
    changes = schema.get("properties", {}).get("changes", {})
    if changes.get("maxItems") != 5:
        raise ProposalValidationError("INVALID_SCHEMA", "schema must limit changes")
    change_schema = changes.get("items", {})
    path_pattern = (
        change_schema
        .get("properties", {})
        .get("path", {})
        .get("pattern", "")
    )
    if "(?!.*\\\\)" not in path_pattern:
        raise ProposalValidationError(
            "INVALID_SCHEMA",
            "schema must reject backslash paths",
        )
    patch_schema = change_schema.get("properties", {}).get("patch", {})
    if patch_schema.get("maxLength") != 20000:
        raise ProposalValidationError(
            "INVALID_SCHEMA",
            "schema must limit per-file patch length",
        )
    forbidden_patterns = [
        item.get("pattern", "")
        for item in patch_schema.get("not", {}).get("anyOf", [])
    ]
    for required_pattern in ("GIT binary patch", "/dev/null", "diff --git"):
        if not any(required_pattern in pattern for pattern in forbidden_patterns):
            raise ProposalValidationError(
                "INVALID_SCHEMA",
                f"schema must reject {required_pattern}",
            )
    return schema


def check_design_documents(policy: FixPolicy) -> list[CheckResult]:
    results: list[CheckResult] = []
    design = read_text(DESIGN_DOC_PATH)
    ai_loop = read_text(AI_LOOP_DOC_PATH)
    for label in (
        "Stage 2A: Fix Proposal",
        "Stage 2B: Human Approval",
        "Stage 2C: Sandboxed Apply",
        policy.proposal_label,
        policy.approval_label,
        PROPOSAL_MARKER,
        "trusted approval record",
        "normative validator",
        "PROPOSAL_READY -> repository commit is forbidden",
        "head SHA changes invalidate proposal and approval",
        "Threat Model",
    ):
        results.append(CheckResult(f"design mentions {label}", label in design))
    results.append(
        CheckResult(
            "ai loop links Stage 2 design",
            "docs/stage2-fix-proposal-design.md" in ai_loop,
        )
    )
    return results


def check_stage2a_runtime_boundary() -> list[CheckResult]:
    results: list[CheckResult] = []
    workflow_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted({*WORKFLOW_DIR.glob("*.yml"), *WORKFLOW_DIR.glob("*.yaml")})
    )
    runtime_text = workflow_text
    if FIX_PROPOSAL_RUNTIME_PATH.exists():
        runtime_text += "\n" + FIX_PROPOSAL_RUNTIME_PATH.read_text(encoding="utf-8")
    results.append(
        CheckResult(
            "workflows may request proposals but not approvals",
            STAGE2_LABEL in runtime_text
            and STAGE2_APPROVAL_LABEL not in workflow_text,
        )
    )
    results.append(
        CheckResult(
            "workflows may post proposal comments",
            PROPOSAL_MARKER in runtime_text,
        )
    )
    forbidden_tokens = (
        "git push",
        "git merge",
        "gh pr merge",
        "gh pr create",
        "contents: write",
        "createCommitOnBranch",
        "createPullRequest",
        "createReviewComment",
    )
    for token in forbidden_tokens:
        results.append(
            CheckResult(
                f"workflows do not contain {token}",
                token not in workflow_text,
            )
        )
    results.append(
        CheckResult(
            "workflows do not implement Stage 2B or Stage 2C",
            "Stage 2B" not in workflow_text and "Stage 2C" not in workflow_text,
        )
    )
    results.append(
        CheckResult(
            "fix design files do not reference repository secrets",
            "secrets." not in read_text(DESIGN_DOC_PATH)
            and "OPENAI_API_KEY" not in read_text(DESIGN_DOC_PATH)
            and "secrets." not in read_text(FIX_POLICY_PATH)
            and "OPENAI_API_KEY" not in read_text(FIX_POLICY_PATH),
        )
    )
    return results


def run_checks() -> list[CheckResult]:
    results = [
        CheckResult("design doc exists", DESIGN_DOC_PATH.exists()),
        CheckResult("fix policy exists", FIX_POLICY_PATH.exists()),
        CheckResult("fix proposal schema exists", FIX_SCHEMA_PATH.exists()),
    ]
    try:
        policy = load_fix_policy()
        results.append(CheckResult("fix policy validates", True))
    except ProposalValidationError as exc:
        results.append(CheckResult("fix policy validates", False, exc.code))
        return results
    try:
        validate_schema_file()
        results.append(CheckResult("fix proposal schema validates", True))
    except (json.JSONDecodeError, ProposalValidationError) as exc:
        results.append(CheckResult("fix proposal schema validates", False, str(exc)))
    results.extend(check_design_documents(policy))
    results.extend(check_stage2a_runtime_boundary())
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    results = run_checks()
    failed = [result for result in results if not result.passed]
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        detail = f" ({result.detail})" if result.detail else ""
        print(f"{status}: {result.label}{detail}")
    if failed:
        return 1
    print(f"{len(results)} Stage 2 fix proposal design checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
