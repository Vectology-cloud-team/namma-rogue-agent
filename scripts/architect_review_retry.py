#!/usr/bin/env python3
"""Retry and failure classification helpers for Stage 1 architect review."""

from __future__ import annotations

import argparse
import fnmatch
import io
import json
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.request
import urllib.parse
import uuid
import zipfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable


MAX_ATTEMPTS = 3
RETRY_DELAYS_SECONDS = (30, 60, 120)
REQUEST_TIMEOUT_SECONDS = 30
EXPECTED_REPOSITORY = "Vectology-cloud-team/namma-rogue-agent"
EXPECTED_ARTIFACT_FILES = ("manifest.json", "review.diff")
EXPECTED_MANIFEST_KEYS = (
    "actor",
    "author_association",
    "base_repository",
    "base_sha",
    "binary_file_count",
    "binary_files_omitted",
    "changed_file_count",
    "collector_workflow_name",
    "collector_workflow_run_id",
    "diff_bytes",
    "draft",
    "head_repository",
    "head_sha",
    "limits",
    "merge_sha",
    "pull_request_number",
    "repository",
    "schema_version",
)
ALLOWED_AUTHOR_ASSOCIATIONS = {"OWNER", "MEMBER", "COLLABORATOR"}
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
COMMENT_MARKER = "<!-- namma-ai-architect-review -->"
POLICY_VERSION = "architect-review-policy-v1"


class FailureClass(str, Enum):
    RETRYABLE = "RETRYABLE"
    FATAL = "FATAL"


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


class SuccessCode(str, Enum):
    APPROVED = "APPROVED"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    NEEDS_HUMAN = "NEEDS_HUMAN"


@dataclass
class ReviewFailure(Exception):
    failure_class: FailureClass
    code: FailureCode
    message: str
    operation: str

    def __str__(self) -> str:
        return f"{self.failure_class.value}/{self.code.value}: {self.message}"


@dataclass
class RetryExhausted(Exception):
    failure: ReviewFailure
    attempts: int


@dataclass
class RetrySuccess:
    value: Any
    attempts: int


@dataclass(frozen=True)
class ReviewPolicy:
    model: str
    effort: str
    max_changed_files: int
    max_diff_bytes: int
    max_prompt_bytes: int
    max_artifact_bytes: int
    exclude: tuple[str, ...]


@dataclass(frozen=True)
class ReviewInputBudget:
    total_files: int
    reviewed_files: int
    excluded_files: int
    diff_bytes: int


def retryable(code: FailureCode, message: str, operation: str) -> ReviewFailure:
    return ReviewFailure(FailureClass.RETRYABLE, code, message, operation)


def fatal(code: FailureCode, message: str, operation: str) -> ReviewFailure:
    return ReviewFailure(FailureClass.FATAL, code, message, operation)


def sanitize_error(message: str) -> str:
    cleaned = re.sub(r"(Bearer|token|password|secret)\s+[A-Za-z0-9._~+/=-]+", r"\1 ***", message)
    cleaned = re.sub(r"gh[pousr]_[A-Za-z0-9_]+", "***", cleaned)
    cleaned = re.sub(r"sk-[A-Za-z0-9_-]+", "***", cleaned)
    return cleaned[:500]


def is_openai_operation(operation: str) -> bool:
    return operation.startswith("openai") or operation.startswith("codex")


def classify_http_status(status: int, reason: str, operation: str) -> ReviewFailure:
    safe_reason = sanitize_error(reason or "HTTP request failed")
    if status == 429:
        if is_openai_operation(operation):
            return retryable(FailureCode.RATE_LIMIT, safe_reason, operation)
        return retryable(FailureCode.GITHUB_429, safe_reason, operation)
    if 500 <= status <= 599:
        if is_openai_operation(operation):
            return retryable(FailureCode.OPENAI_5XX, safe_reason, operation)
        return retryable(FailureCode.GITHUB_5XX, safe_reason, operation)
    if status in (401, 403):
        return fatal(FailureCode.PERMISSION_ERROR, safe_reason, operation)
    if operation.startswith("artifact") and status in (404, 409, 425):
        return retryable(FailureCode.ARTIFACT_TRANSIENT_ERROR, safe_reason, operation)
    return fatal(FailureCode.WORKFLOW_CONFIGURATION_ERROR, safe_reason, operation)


def classify_exception(error: BaseException, operation: str) -> ReviewFailure:
    if isinstance(error, ReviewFailure):
        return error
    if isinstance(error, TimeoutError):
        return retryable(FailureCode.API_TIMEOUT, "operation timed out", operation)
    if isinstance(error, urllib.error.HTTPError):
        return classify_http_status(error.code, error.reason, operation)
    if isinstance(error, urllib.error.URLError):
        reason = sanitize_error(str(error.reason))
        if "timed out" in reason.lower() or "timeout" in reason.lower():
            return retryable(FailureCode.API_TIMEOUT, reason, operation)
        return retryable(FailureCode.NETWORK_ERROR, reason, operation)
    return fatal(FailureCode.WORKFLOW_CONFIGURATION_ERROR, sanitize_error(str(error)), operation)


def classify_codex_failure_message(message: str) -> ReviewFailure:
    if not message:
        return retryable(
            FailureCode.NETWORK_ERROR,
            "Codex Action failed without details after preflight validation",
            "openai_codex_action",
        )
    safe_message = sanitize_error(message)
    lowered = safe_message.lower()
    if any(term in lowered for term in ("rate limit", "too many requests", " 429", "http 429")):
        return retryable(FailureCode.RATE_LIMIT, safe_message, "openai_codex_action")
    if any(
        term in lowered
        for term in (
            "timed out",
            "timeout",
            "etimedout",
            "deadline exceeded",
        )
    ):
        return retryable(FailureCode.API_TIMEOUT, safe_message, "openai_codex_action")
    if any(
        term in lowered
        for term in (
            " 500",
            " 502",
            " 503",
            " 504",
            "http 500",
            "http 502",
            "http 503",
            "http 504",
            "5xx",
            "bad gateway",
            "service unavailable",
        )
    ):
        return retryable(FailureCode.OPENAI_5XX, safe_message, "openai_codex_action")
    if any(
        term in lowered
        for term in (
            "network",
            "connection reset",
            "econnreset",
            "econnrefused",
            "temporary failure",
            "temporary name resolution",
            "enotfound",
        )
    ):
        return retryable(FailureCode.NETWORK_ERROR, safe_message, "openai_codex_action")
    if any(
        term in lowered
        for term in (
            "api key",
            "unauthorized",
            "forbidden",
            "permission",
            " 401",
            " 403",
            "http 401",
            "http 403",
        )
    ):
        return fatal(FailureCode.PERMISSION_ERROR, safe_message, "openai_codex_action")
    return fatal(FailureCode.WORKFLOW_CONFIGURATION_ERROR, safe_message, "openai_codex_action")


def run_with_retry(
    operation: str,
    func: Callable[[], Any],
    *,
    max_attempts: int = MAX_ATTEMPTS,
    sleep_func: Callable[[int], None] = time.sleep,
) -> RetrySuccess:
    last_failure: ReviewFailure | None = None
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


def github_output(values: dict[str, str]) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        for key, value in values.items():
            print(f"{key}={value}")
        return
    with Path(output_path).open("a", encoding="utf-8") as output:
        for key, value in values.items():
            if "\n" in value:
                marker = f"EOF_{uuid.uuid4().hex}"
                output.write(f"{key}<<{marker}\n{value}\n{marker}\n")
            else:
                output.write(f"{key}={value}\n")


def failure_summary(
    failure: ReviewFailure,
    *,
    attempts: int,
    pr_number: str = "",
    head_sha: str = "",
) -> str:
    return "\n".join(
        [
            "## Architect Review Failure",
            "",
            f"- failure class: `{failure.failure_class.value}`",
            f"- failure code: `{failure.code.value}`",
            f"- failed operation: `{failure.operation}`",
            f"- attempts: `{attempts}`",
            f"- reviewed PR number: `{pr_number or 'unknown'}`",
            f"- reviewed head SHA: `{head_sha or 'unknown'}`",
            f"- last error: `{sanitize_error(failure.message)}`",
            "",
            "Automatic processing stopped. A human should inspect the workflow logs.",
        ]
    )


def write_job_summary(text: str) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with Path(summary_path).open("a", encoding="utf-8") as summary:
            summary.write(text.rstrip() + "\n")
    print(text)


def parse_size(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise fatal(
            FailureCode.WORKFLOW_CONFIGURATION_ERROR,
            f"review policy {field_name} must be a positive integer",
            "review_policy",
        )
    return value


def policy_int(limits: dict[str, Any], key: str, default: int | None = None) -> int:
    raw_value = limits.get(key, default)
    if isinstance(raw_value, bool) or raw_value is None:
        return parse_size(raw_value, f"limits.{key}")
    try:
        value = int(raw_value)
    except (TypeError, ValueError) as error:
        raise fatal(
            FailureCode.WORKFLOW_CONFIGURATION_ERROR,
            f"review policy limits.{key} must be a positive integer",
            "review_policy",
        ) from error
    return parse_size(value, f"limits.{key}")


def clean_yaml_value(value: str) -> str:
    value = value.strip()
    if value.startswith(("'", '"')) and value.endswith(("'", '"')) and len(value) >= 2:
        return value[1:-1]
    return value


def parse_review_policy_text(text: str) -> ReviewPolicy:
    top: dict[str, Any] = {}
    section = ""
    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        line = raw_line.strip()
        if indent == 0:
            if line.endswith(":"):
                section = line[:-1]
                top.setdefault(section, [] if section == "exclude" else {})
                continue
            key, separator, value = line.partition(":")
            if not separator:
                raise fatal(
                    FailureCode.WORKFLOW_CONFIGURATION_ERROR,
                    f"invalid review policy line: {raw_line}",
                    "review_policy",
                )
            section = ""
            top[key.strip()] = clean_yaml_value(value)
            continue
        if section == "exclude":
            if not line.startswith("- "):
                raise fatal(
                    FailureCode.WORKFLOW_CONFIGURATION_ERROR,
                    f"invalid review policy exclude entry: {raw_line}",
                    "review_policy",
                )
            top.setdefault("exclude", []).append(clean_yaml_value(line[2:]))
            continue
        key, separator, value = line.partition(":")
        if not section or not separator:
            raise fatal(
                FailureCode.WORKFLOW_CONFIGURATION_ERROR,
                f"invalid review policy nested line: {raw_line}",
                "review_policy",
            )
        nested = top.setdefault(section, {})
        if not isinstance(nested, dict):
            raise fatal(
                FailureCode.WORKFLOW_CONFIGURATION_ERROR,
                f"invalid review policy section: {section}",
                "review_policy",
            )
        nested[key.strip()] = clean_yaml_value(value)

    model = str(top.get("model", "")).strip()
    reasoning = top.get("reasoning", {})
    limits = top.get("limits", {})
    exclude = top.get("exclude", [])
    if not model:
        raise fatal(
            FailureCode.WORKFLOW_CONFIGURATION_ERROR,
            "review policy model is required",
            "review_policy",
        )
    if not isinstance(reasoning, dict) or not str(reasoning.get("effort", "")).strip():
        raise fatal(
            FailureCode.WORKFLOW_CONFIGURATION_ERROR,
            "review policy reasoning.effort is required",
            "review_policy",
        )
    if not isinstance(limits, dict):
        raise fatal(
            FailureCode.WORKFLOW_CONFIGURATION_ERROR,
            "review policy limits section is required",
            "review_policy",
        )
    if not isinstance(exclude, list) or not all(isinstance(item, str) for item in exclude):
        raise fatal(
            FailureCode.WORKFLOW_CONFIGURATION_ERROR,
            "review policy exclude must be a list of strings",
            "review_policy",
        )
    max_diff_bytes = policy_int(limits, "max_diff_bytes")
    default_artifact_bytes = max(max_diff_bytes + 50000, 250000)
    return ReviewPolicy(
        model=model,
        effort=str(reasoning["effort"]).strip(),
        max_changed_files=policy_int(limits, "max_changed_files"),
        max_diff_bytes=max_diff_bytes,
        max_prompt_bytes=policy_int(limits, "max_prompt_bytes"),
        max_artifact_bytes=policy_int(limits, "max_artifact_bytes", default_artifact_bytes),
        exclude=tuple(item.strip() for item in exclude if item.strip()),
    )


def load_review_policy(path: Path) -> ReviewPolicy:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise fatal(
            FailureCode.WORKFLOW_CONFIGURATION_ERROR,
            "trusted review policy is missing",
            "review_policy",
        ) from error
    return parse_review_policy_text(text)


def review_policy_from_env() -> ReviewPolicy:
    return ReviewPolicy(
        model=required_env("REVIEW_MODEL"),
        effort=required_env("REVIEW_EFFORT"),
        max_changed_files=int(required_env("MAX_CHANGED_FILES")),
        max_diff_bytes=int(required_env("MAX_DIFF_BYTES")),
        max_prompt_bytes=int(required_env("MAX_PROMPT_BYTES")),
        max_artifact_bytes=int(required_env("MAX_ARTIFACT_BYTES")),
        exclude=tuple(json.loads(required_env("POLICY_EXCLUDE_JSON"))),
    )


def format_bytes(byte_count: int) -> str:
    if byte_count < 1024:
        return f"{byte_count} B"
    return f"{byte_count / 1024:.1f} KB"


def policy_summary(policy: ReviewPolicy) -> str:
    exclude_text = ", ".join(policy.exclude) if policy.exclude else "None"
    return "\n".join(
        [
            "## Review Policy",
            "",
            f"- Policy: `{POLICY_VERSION}`",
            f"- Model: `{policy.model}`",
            f"- Reasoning: `{policy.effort}`",
            f"- Max changed files: `{policy.max_changed_files}`",
            f"- Max diff: `{format_bytes(policy.max_diff_bytes)}`",
            f"- Max prompt: `{format_bytes(policy.max_prompt_bytes)}`",
            f"- Exclude: `{exclude_text}`",
            "",
        ]
    )


def review_input_summary(policy: ReviewPolicy, budget: ReviewInputBudget) -> str:
    return "\n".join(
        [
            "## Review Input",
            "",
            f"- Files: `{budget.reviewed_files}` reviewed / `{budget.total_files}` changed",
            f"- Excluded files: `{budget.excluded_files}`",
            f"- Diff: `{format_bytes(budget.diff_bytes)}`",
            f"- Model: `{policy.model}`",
            f"- Reasoning: `{policy.effort}`",
            "",
        ]
    )


def skipped_review_message(reason: str, detail: str) -> str:
    return "\n".join(
        [
            "VERDICT: HUMAN_DECISION_REQUIRED",
            "",
            "SUMMARY",
            "Review skipped by trusted Reviewer policy.",
            "",
            "BLOCKING FINDINGS",
            "None.",
            "",
            "NON-BLOCKING FINDINGS",
            "None.",
            "",
            "REQUIRED TESTS",
            "None.",
            "",
            "SCOPE VIOLATIONS",
            "None.",
            "",
            "HUMAN DECISIONS",
            f"{reason}: {detail}",
        ]
    )


def fail_command(error: BaseException, *, pr_number: str = "", head_sha: str = "") -> int:
    if isinstance(error, RetryExhausted):
        failure = error.failure
        attempts = error.attempts
    else:
        failure = classify_exception(error, "unknown")
        attempts = 1
    write_job_summary(
        failure_summary(
            failure,
            attempts=attempts,
            pr_number=pr_number,
            head_sha=head_sha,
        )
    )
    print(f"::error ::{failure.failure_class.value}/{failure.code.value}: {failure.message}")
    return 1


def github_api_request(
    method: str,
    api_path: str,
    *,
    token: str,
    body: dict[str, Any] | None = None,
    accept: str = "application/vnd.github+json",
    max_response_bytes: int | None = None,
    operation: str = "github_api",
) -> tuple[bytes, dict[str, str]]:
    data = None
    headers = {
        "Accept": accept,
        "Authorization": f"Bearer {token}",
        "User-Agent": "namma-architect-review",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    url = f"https://api.github.com{api_path}"
    return http_request_with_safe_redirects(
        url,
        headers=headers,
        method=method,
        data=data,
        max_response_bytes=max_response_bytes,
        operation=operation,
    )


def read_limited_response(
    response: Any,
    *,
    max_response_bytes: int | None,
    operation: str,
) -> bytes:
    if max_response_bytes is None:
        return response.read()
    chunks: list[bytes] = []
    total = 0
    chunk_size = min(65536, max_response_bytes + 1)
    while True:
        chunk = response.read(chunk_size)
        if not chunk:
            return b"".join(chunks)
        total += len(chunk)
        if total > max_response_bytes:
            raise fatal(
                FailureCode.INVALID_MANIFEST,
                "HTTP response exceeds configured maximum size",
                operation,
            )
        chunks.append(chunk)


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def headers_for_redirect(
    original_url: str,
    redirect_url: str,
    headers: dict[str, str],
) -> dict[str, str]:
    original_host = urllib.parse.urlparse(original_url).netloc.lower()
    redirect_host = urllib.parse.urlparse(redirect_url).netloc.lower()
    next_headers = dict(headers)
    if original_host != redirect_host:
        next_headers.pop("Authorization", None)
    return next_headers


def http_request_with_safe_redirects(
    url: str,
    *,
    headers: dict[str, str],
    method: str,
    data: bytes | None,
    max_response_bytes: int | None,
    operation: str,
    redirects_remaining: int = 3,
) -> tuple[bytes, dict[str, str]]:
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    opener = urllib.request.build_opener(NoRedirectHandler)
    try:
        with opener.open(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            data = read_limited_response(
                response,
                max_response_bytes=max_response_bytes,
                operation=operation,
            )
            return data, dict(response.headers.items())
    except urllib.error.HTTPError as error:
        location = error.headers.get("Location")
        if (
            error.code in (301, 302, 303, 307, 308)
            and location
            and redirects_remaining > 0
        ):
            redirect_url = urllib.parse.urljoin(url, location)
            redirect_headers = headers_for_redirect(url, redirect_url, headers)
            redirect_method = method
            redirect_data = data
            if error.code in (301, 302, 303) and method != "GET":
                redirect_method = "GET"
                redirect_data = None
            return http_request_with_safe_redirects(
                redirect_url,
                headers=redirect_headers,
                method=redirect_method,
                data=redirect_data,
                max_response_bytes=max_response_bytes,
                operation=operation,
                redirects_remaining=redirects_remaining - 1,
            )
        raise


def command_load_policy(_: argparse.Namespace) -> int:
    try:
        policy = load_review_policy(Path(required_env("REVIEW_POLICY")))
        write_job_summary(policy_summary(policy))
        github_output(
            {
                "policy_version": POLICY_VERSION,
                "model": policy.model,
                "effort": policy.effort,
                "max_changed_files": str(policy.max_changed_files),
                "max_diff_bytes": str(policy.max_diff_bytes),
                "max_prompt_bytes": str(policy.max_prompt_bytes),
                "max_artifact_bytes": str(policy.max_artifact_bytes),
                "exclude_json": json.dumps(list(policy.exclude), separators=(",", ":")),
            }
        )
        return 0
    except BaseException as error:
        return fail_command(error)


def github_json(
    method: str,
    api_path: str,
    *,
    token: str,
    body: dict[str, Any] | None = None,
) -> tuple[Any, dict[str, str]]:
    data, headers = github_api_request(method, api_path, token=token, body=body)
    if not data:
        return None, headers
    return json.loads(data.decode("utf-8")), headers


def validate_artifact_member(
    member: zipfile.ZipInfo,
    *,
    root: Path,
    target_dir: Path,
    max_bytes: int,
    seen_destinations: set[Path],
) -> tuple[Path, int]:
    if member.is_dir():
        raise fatal(
            FailureCode.INVALID_MANIFEST,
            f"artifact directory entries are not allowed: {member.filename}",
            "artifact_download",
        )
    file_type = (member.external_attr >> 16) & 0o170000
    if file_type == 0o120000:
        raise fatal(
            FailureCode.PATH_TRAVERSAL,
            f"artifact symlink entries are not allowed: {member.filename}",
            "artifact_download",
        )
    destination = (target_dir / member.filename).resolve()
    if root != destination and root not in destination.parents:
        raise fatal(
            FailureCode.PATH_TRAVERSAL,
            f"artifact path traversal detected: {member.filename}",
            "artifact_download",
        )
    if member.filename not in EXPECTED_ARTIFACT_FILES:
        raise fatal(
            FailureCode.INVALID_MANIFEST,
            f"unexpected artifact member: {member.filename}",
            "artifact_download",
        )
    if member.file_size > max_bytes:
        raise fatal(
            FailureCode.INVALID_MANIFEST,
            f"artifact member exceeds maximum size: {member.filename}",
            "artifact_download",
        )
    if destination in seen_destinations:
        raise fatal(
            FailureCode.INVALID_MANIFEST,
            f"duplicate artifact member destination: {member.filename}",
            "artifact_download",
        )
    seen_destinations.add(destination)
    return destination, member.file_size


def safe_extract_zip(zip_bytes: bytes, target_dir: Path, *, max_bytes: int) -> None:
    if len(zip_bytes) > max_bytes:
        raise fatal(
            FailureCode.INVALID_MANIFEST,
            "downloaded artifact zip exceeds configured maximum size",
            "artifact_download",
        )
    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    root = target_dir.resolve()
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
            members = [member for member in archive.infolist() if not member.is_dir()]
            if len(members) != len(EXPECTED_ARTIFACT_FILES):
                raise fatal(
                    FailureCode.INVALID_MANIFEST,
                    "artifact must contain exactly manifest.json and review.diff",
                    "artifact_download",
                )
            seen_destinations: set[Path] = set()
            total_declared_size = 0
            planned: list[tuple[zipfile.ZipInfo, Path]] = []
            for member in members:
                destination, declared_size = validate_artifact_member(
                    member,
                    root=root,
                    target_dir=target_dir,
                    max_bytes=max_bytes,
                    seen_destinations=seen_destinations,
                )
                total_declared_size += declared_size
                if total_declared_size > max_bytes:
                    raise fatal(
                        FailureCode.INVALID_MANIFEST,
                        "artifact extracted size exceeds configured maximum",
                        "artifact_download",
                    )
                planned.append((member, destination))
            for member, destination in planned:
                destination.parent.mkdir(parents=True, exist_ok=True)
                extracted_size = 0
                with archive.open(member) as source, destination.open("wb") as output:
                    while True:
                        chunk = source.read(65536)
                        if not chunk:
                            break
                        extracted_size += len(chunk)
                        if extracted_size > member.file_size or extracted_size > max_bytes:
                            raise fatal(
                                FailureCode.INVALID_MANIFEST,
                                f"artifact member expanded beyond declared size: {member.filename}",
                                "artifact_download",
                            )
                        output.write(chunk)
    except BaseException:
        shutil.rmtree(target_dir, ignore_errors=True)
        raise


def command_download_artifact(_: argparse.Namespace) -> int:
    token = required_env("GITHUB_TOKEN")
    repo = required_env("GITHUB_REPOSITORY")
    run_id = required_env("COLLECTOR_RUN_ID")
    artifact_name = required_env("ARTIFACT_NAME")
    target_dir = Path(required_env("REVIEW_INPUT_DIR"))
    max_artifact_bytes = int(required_env("MAX_ARTIFACT_BYTES"))

    def operation() -> None:
        listing, _ = github_json(
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
        artifact_id = matching[0]["id"]
        data, _ = github_api_request(
            "GET",
            f"/repos/{repo}/actions/artifacts/{artifact_id}/zip",
            token=token,
            max_response_bytes=max_artifact_bytes,
            operation="artifact_download",
        )
        safe_extract_zip(data, target_dir, max_bytes=max_artifact_bytes)

    try:
        run_with_retry("artifact_download", operation)
        return 0
    except BaseException as error:
        return fail_command(error)


def required_env(name: str) -> str:
    value = os.environ.get(name)
    if value is None or value == "":
        raise fatal(
            FailureCode.WORKFLOW_CONFIGURATION_ERROR,
            f"required environment variable {name} is missing",
            "configuration",
        )
    return value


def is_plain_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def is_non_negative_int(value: Any) -> bool:
    return is_plain_int(value) and value >= 0


def read_manifest(root: Path) -> tuple[dict[str, Any], Path, Path]:
    entries = sorted(path.name for path in root.iterdir())
    if entries != ["manifest.json", "review.diff"]:
        raise fatal(
            FailureCode.INVALID_MANIFEST,
            f"unexpected artifact contents: {', '.join(entries)}",
            "review_input_validation",
        )
    for entry in root.iterdir():
        if not entry.is_file() or entry.is_symlink():
            raise fatal(
                FailureCode.PATH_TRAVERSAL,
                f"unsafe artifact entry: {entry.name}",
                "review_input_validation",
            )
        resolved = entry.resolve()
        if root.resolve() != resolved and root.resolve() not in resolved.parents:
            raise fatal(
                FailureCode.PATH_TRAVERSAL,
                f"artifact path traversal detected: {entry.name}",
                "review_input_validation",
            )
    manifest_path = root / "manifest.json"
    diff_path = root / "review.diff"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise fatal(
            FailureCode.INVALID_JSON,
            f"manifest.json is not valid JSON: {error.msg}",
            "review_input_validation",
        ) from error
    return manifest, manifest_path, diff_path


def validate_manifest_shape(
    manifest: dict[str, Any],
    *,
    diff_path: Path,
    manifest_path: Path,
) -> None:
    keys = tuple(sorted(manifest.keys()))
    if keys != EXPECTED_MANIFEST_KEYS:
        raise fatal(
            FailureCode.INVALID_MANIFEST,
            "manifest.json schema keys do not match",
            "review_input_validation",
        )
    if manifest["schema_version"] != "architect-review-input-v1":
        raise fatal(
            FailureCode.INVALID_MANIFEST,
            "unsupported manifest schema_version",
            "review_input_validation",
        )
    if manifest["repository"] != required_env("EXPECTED_REPOSITORY"):
        raise fatal(
            FailureCode.REPOSITORY_MISMATCH,
            "manifest repository does not match expected repository",
            "review_input_validation",
        )
    if manifest["collector_workflow_name"] != required_env("EXPECTED_COLLECTOR_WORKFLOW"):
        raise fatal(
            FailureCode.WORKFLOW_CONFIGURATION_ERROR,
            "manifest collector workflow name does not match",
            "review_input_validation",
        )
    if not is_non_negative_int(manifest["collector_workflow_run_id"]):
        raise fatal(
            FailureCode.INVALID_MANIFEST,
            "manifest collector_workflow_run_id must be a non-negative integer",
            "review_input_validation",
        )
    if manifest["collector_workflow_run_id"] != int(required_env("WORKFLOW_RUN_ID")):
        raise fatal(
            FailureCode.WORKFLOW_CONFIGURATION_ERROR,
            "manifest collector workflow run ID does not match",
            "review_input_validation",
        )
    if not is_non_negative_int(manifest["pull_request_number"]):
        raise fatal(
            FailureCode.PR_MISMATCH,
            "manifest pull_request_number must be a non-negative integer",
            "review_input_validation",
        )
    for key in ("base_sha", "head_sha", "merge_sha"):
        if not SHA_RE.match(str(manifest[key])):
            raise fatal(
                FailureCode.SHA_MISMATCH,
                f"manifest {key} must be a full commit SHA",
                "review_input_validation",
            )
    if not isinstance(manifest["draft"], bool):
        raise fatal(
            FailureCode.INVALID_MANIFEST,
            "manifest draft must be a boolean",
            "review_input_validation",
        )
    if not is_non_negative_int(manifest["changed_file_count"]):
        raise fatal(
            FailureCode.INVALID_MANIFEST,
            "manifest changed_file_count must be a non-negative integer",
            "review_input_validation",
        )
    diff_bytes = diff_path.stat().st_size
    manifest_bytes = manifest_path.stat().st_size
    if not is_non_negative_int(manifest["diff_bytes"]):
        raise fatal(
            FailureCode.INVALID_MANIFEST,
            "manifest diff_bytes must be a non-negative integer",
            "review_input_validation",
        )
    if manifest["diff_bytes"] != diff_bytes:
        raise fatal(
            FailureCode.INVALID_MANIFEST,
            "manifest diff_bytes does not match review.diff",
            "review_input_validation",
        )
    if diff_bytes + manifest_bytes > int(required_env("MAX_ARTIFACT_BYTES")):
        raise fatal(
            FailureCode.INVALID_MANIFEST,
            "review input artifact exceeds configured maximum size",
            "review_input_validation",
        )
    if not isinstance(manifest["binary_files_omitted"], list):
        raise fatal(
            FailureCode.INVALID_MANIFEST,
            "manifest binary_files_omitted must be an array",
            "review_input_validation",
        )
    if not is_non_negative_int(manifest["binary_file_count"]):
        raise fatal(
            FailureCode.INVALID_MANIFEST,
            "manifest binary_file_count must be a non-negative integer",
            "review_input_validation",
        )
    if manifest["binary_file_count"] != len(manifest["binary_files_omitted"]):
        raise fatal(
            FailureCode.INVALID_MANIFEST,
            "manifest binary_file_count does not match binary_files_omitted",
            "review_input_validation",
        )
    limits = manifest["limits"]
    if not isinstance(limits, dict):
        raise fatal(
            FailureCode.INVALID_MANIFEST,
            "manifest limits must be an object",
            "review_input_validation",
        )
    for key in ("max_diff_bytes", "max_changed_files", "max_artifact_bytes"):
        if not is_non_negative_int(limits.get(key)):
            raise fatal(
                FailureCode.INVALID_MANIFEST,
                f"manifest limits.{key} must be a non-negative integer",
                "review_input_validation",
            )


def validate_live_pull_request(manifest: dict[str, Any], pull: dict[str, Any]) -> None:
    if pull.get("number") != manifest["pull_request_number"]:
        raise fatal(
            FailureCode.PR_MISMATCH,
            "live pull request number does not match manifest",
            "review_input_validation",
        )
    live_base_repo = pull["base"]["repo"]["full_name"]
    live_head_repo = pull["head"]["repo"]["full_name"]
    if manifest["base_repository"] != live_base_repo:
        raise fatal(
            FailureCode.REPOSITORY_MISMATCH,
            "manifest base repository does not match live pull request",
            "review_input_validation",
        )
    if manifest["head_repository"] != live_head_repo:
        raise fatal(
            FailureCode.REPOSITORY_MISMATCH,
            "manifest head repository does not match live pull request",
            "review_input_validation",
        )
    if manifest["base_sha"] != pull["base"]["sha"]:
        raise fatal(
            FailureCode.STALE_ARTIFACT,
            "pull request base SHA changed after artifact collection",
            "review_input_validation",
        )
    if manifest["head_sha"] != pull["head"]["sha"]:
        raise fatal(
            FailureCode.STALE_ARTIFACT,
            "pull request head SHA changed after artifact collection",
            "review_input_validation",
        )


def refresh_review_diff_from_github(
    *,
    repo: str,
    pull_request_number: int,
    token: str,
    diff_path: Path,
    max_response_bytes: int,
) -> None:
    data, _ = github_api_request(
        "GET",
        f"/repos/{repo}/pulls/{pull_request_number}",
        token=token,
        accept="application/vnd.github.v3.diff",
        max_response_bytes=max_response_bytes,
        operation="github_pr_diff",
    )
    diff_path.write_bytes(data)


def iter_live_pr_files(repo: str, pull_request_number: int, token: str) -> Iterable[dict[str, Any]]:
    next_path = f"/repos/{repo}/pulls/{pull_request_number}/files?per_page=100"
    while next_path:
        data, headers = github_json("GET", next_path, token=token)
        if not isinstance(data, list):
            raise fatal(
                FailureCode.INVALID_MANIFEST,
                "live pull request files response was not an array",
                "github_pr_files",
            )
        yield from data
        next_path = parse_next_link(headers.get("Link", ""))


def normalized_repo_path(path: str) -> str:
    return path.replace("\\", "/").lstrip("/")


def path_matches_exclude(path: str, patterns: tuple[str, ...]) -> bool:
    normalized = normalized_repo_path(path)
    return any(fnmatch.fnmatchcase(normalized, pattern) for pattern in patterns)


def file_is_excluded(file_info: dict[str, Any], policy: ReviewPolicy) -> bool:
    return path_matches_exclude(str(file_info.get("filename", "")), policy.exclude)


def validate_live_pr_files(
    manifest: dict[str, Any],
    files: list[dict[str, Any]],
    policy: ReviewPolicy,
) -> None:
    if len(files) != manifest["changed_file_count"]:
        raise fatal(
            FailureCode.STALE_ARTIFACT,
            "live changed-file count does not match manifest",
            "github_pr_files",
        )
    unreviewable_files = sorted(
        str(file_info.get("filename", ""))
        for file_info in files
        if not isinstance(file_info.get("patch"), str)
    )
    manifest_omitted = sorted(str(path) for path in manifest["binary_files_omitted"])
    if manifest["binary_file_count"] != len(unreviewable_files):
        raise fatal(
            FailureCode.INVALID_MANIFEST,
            "manifest binary_file_count does not match live unreviewable files",
            "github_pr_files",
        )
    if manifest_omitted != unreviewable_files:
        raise fatal(
            FailureCode.INVALID_MANIFEST,
            "manifest binary_files_omitted does not match live unreviewable files",
            "github_pr_files",
        )
    unreviewable_not_excluded = [
        path
        for path in unreviewable_files
        if not path_matches_exclude(path, policy.exclude)
    ]
    if unreviewable_not_excluded:
        raise fatal(
            FailureCode.TRUST_BOUNDARY_VIOLATION,
            "pull request contains non-excluded files without reviewable text patches",
            "github_pr_files",
        )


def diff_section_paths(section: list[str]) -> set[str]:
    paths: set[str] = set()
    for line in section:
        if line.startswith("diff --git "):
            parts = line.strip().split()
            for raw_path in parts[2:4]:
                if raw_path.startswith(("a/", "b/")):
                    paths.add(normalized_repo_path(raw_path[2:]))
        elif line.startswith(("--- ", "+++ ")):
            raw_path = line[4:].strip().split("\t", 1)[0]
            if raw_path == "/dev/null":
                continue
            if raw_path.startswith(("a/", "b/")):
                paths.add(normalized_repo_path(raw_path[2:]))
    return paths


def split_diff_sections(diff_text: str) -> list[list[str]]:
    sections: list[list[str]] = []
    current: list[str] = []
    for line in diff_text.splitlines(keepends=True):
        if line.startswith("diff --git ") and current:
            sections.append(current)
            current = []
        current.append(line)
    if current:
        sections.append(current)
    return sections


def filter_unified_diff(diff_bytes: bytes, policy: ReviewPolicy) -> bytes:
    diff_text = diff_bytes.decode("utf-8", errors="replace")
    kept_sections: list[str] = []
    for section in split_diff_sections(diff_text):
        paths = diff_section_paths(section)
        if paths and all(path_matches_exclude(path, policy.exclude) for path in paths):
            continue
        kept_sections.append("".join(section))
    return "".join(kept_sections).encode("utf-8")


def review_input_budget(
    files: list[dict[str, Any]],
    filtered_diff_bytes: bytes,
    policy: ReviewPolicy,
) -> ReviewInputBudget:
    excluded_files = [file_info for file_info in files if file_is_excluded(file_info, policy)]
    return ReviewInputBudget(
        total_files=len(files),
        reviewed_files=len(files) - len(excluded_files),
        excluded_files=len(excluded_files),
        diff_bytes=len(filtered_diff_bytes),
    )


def validate_workflow_run_identity() -> None:
    if required_env("WORKFLOW_RUN_NAME") != required_env("EXPECTED_COLLECTOR_WORKFLOW"):
        raise fatal(
            FailureCode.WORKFLOW_CONFIGURATION_ERROR,
            "unexpected collector workflow name",
            "review_input_validation",
        )
    if required_env("WORKFLOW_RUN_EVENT") != "pull_request":
        raise fatal(
            FailureCode.WORKFLOW_CONFIGURATION_ERROR,
            "collector workflow_run was not triggered by pull_request",
            "review_input_validation",
        )
    if required_env("WORKFLOW_RUN_REPOSITORY") != required_env("EXPECTED_REPOSITORY"):
        raise fatal(
            FailureCode.REPOSITORY_MISMATCH,
            "collector workflow_run repository does not match expected repository",
            "review_input_validation",
        )
    if required_env("GITHUB_REPOSITORY") != required_env("EXPECTED_REPOSITORY"):
        raise fatal(
            FailureCode.REPOSITORY_MISMATCH,
            "reviewer repository identity does not match expected repository",
            "review_input_validation",
        )


def command_validate_review_input(_: argparse.Namespace) -> int:
    root = Path(required_env("REVIEW_INPUT_DIR")).resolve()
    token = required_env("GITHUB_TOKEN")
    repo = required_env("GITHUB_REPOSITORY")
    policy = review_policy_from_env()
    manifest: dict[str, Any] | None = None
    try:
        validate_workflow_run_identity()
        manifest, manifest_path, diff_path = read_manifest(root)
        validate_manifest_shape(manifest, diff_path=diff_path, manifest_path=manifest_path)

        def fetch_pr() -> dict[str, Any]:
            data, _ = github_json(
                "GET",
                f"/repos/{repo}/pulls/{manifest['pull_request_number']}",
                token=token,
            )
            assert isinstance(data, dict)
            return data

        pull = run_with_retry("github_pr_lookup", fetch_pr).value
        validate_live_pull_request(manifest, pull)
        if pull["draft"]:
            print("Skipping draft pull request.")
            github_output(outputs_for_skip(manifest))
            return 0
        if pull["head"]["repo"]["full_name"] != required_env("EXPECTED_REPOSITORY"):
            print("Skipping fork or external pull request.")
            github_output(outputs_for_skip(manifest))
            return 0
        if pull["user"]["type"] == "Bot":
            print("Skipping bot-authored pull request.")
            github_output(outputs_for_skip(manifest))
            return 0
        if pull["author_association"] not in ALLOWED_AUTHOR_ASSOCIATIONS:
            print("Skipping pull request from author without write-level association.")
            github_output(outputs_for_skip(manifest))
            return 0
        live_files = run_with_retry(
            "github_pr_files",
            lambda: list(
                iter_live_pr_files(
                    repo,
                    manifest["pull_request_number"],
                    token,
                )
            ),
        ).value
        validate_live_pr_files(manifest, live_files, policy)
        run_with_retry(
            "github_pr_diff",
            lambda: refresh_review_diff_from_github(
                repo=repo,
                pull_request_number=manifest["pull_request_number"],
                token=token,
                diff_path=diff_path,
                max_response_bytes=policy.max_artifact_bytes,
            ),
        )
        filtered_diff = filter_unified_diff(diff_path.read_bytes(), policy)
        diff_path.write_bytes(filtered_diff)
        budget = review_input_budget(live_files, filtered_diff, policy)
        write_job_summary(review_input_summary(policy, budget))
        pull_after_diff = run_with_retry("github_pr_revalidate", fetch_pr).value
        validate_live_pull_request(manifest, pull_after_diff)
        if budget.reviewed_files == 0:
            detail = "all changed files were excluded by trusted review policy"
            github_output(
                outputs_for_budget_skip(
                    manifest,
                    pull_after_diff,
                    budget,
                    "Review input excluded",
                    detail,
                )
            )
            return 0
        if budget.reviewed_files > policy.max_changed_files:
            detail = (
                f"{budget.reviewed_files} reviewable files exceeds "
                f"{policy.max_changed_files}"
            )
            github_output(
                outputs_for_budget_skip(
                    manifest,
                    pull_after_diff,
                    budget,
                    "Diff budget exceeded",
                    detail,
                )
            )
            return 0
        if budget.diff_bytes > policy.max_diff_bytes:
            detail = (
                f"{budget.diff_bytes} review diff bytes exceeds "
                f"{policy.max_diff_bytes}"
            )
            github_output(
                outputs_for_budget_skip(
                    manifest,
                    pull_after_diff,
                    budget,
                    "Diff budget exceeded",
                    detail,
                )
            )
            return 0
        github_output(
            {
                "should_review": "true",
                "should_comment": "true",
                "pr_number": str(manifest["pull_request_number"]),
                "head_sha": pull_after_diff["head"]["sha"],
                "base_sha": pull_after_diff["base"]["sha"],
                "review_status": "pending_codex",
                "final_message": "",
                "total_files": str(budget.total_files),
                "reviewed_files": str(budget.reviewed_files),
                "excluded_files": str(budget.excluded_files),
                "diff_bytes": str(budget.diff_bytes),
            }
        )
        return 0
    except BaseException as error:
        pr_number = str(manifest.get("pull_request_number", "")) if manifest else ""
        head_sha = str(manifest.get("head_sha", "")) if manifest else ""
        return fail_command(error, pr_number=pr_number, head_sha=head_sha)


def outputs_for_skip(manifest: dict[str, Any]) -> dict[str, str]:
    return {
        "should_review": "false",
        "should_comment": "false",
        "pr_number": str(manifest["pull_request_number"]),
        "head_sha": str(manifest["head_sha"]),
        "base_sha": str(manifest["base_sha"]),
        "review_status": "skipped",
        "final_message": "",
        "total_files": str(manifest["changed_file_count"]),
        "reviewed_files": "0",
        "excluded_files": "0",
        "diff_bytes": "0",
    }


def outputs_for_budget_skip(
    manifest: dict[str, Any],
    pull: dict[str, Any],
    budget: ReviewInputBudget,
    reason: str,
    detail: str,
) -> dict[str, str]:
    return {
        "should_review": "false",
        "should_comment": "true",
        "pr_number": str(manifest["pull_request_number"]),
        "head_sha": str(pull["head"]["sha"]),
        "base_sha": str(pull["base"]["sha"]),
        "review_status": "skipped",
        "final_message": skipped_review_message(reason, detail),
        "total_files": str(budget.total_files),
        "reviewed_files": str(budget.reviewed_files),
        "excluded_files": str(budget.excluded_files),
        "diff_bytes": str(budget.diff_bytes),
    }


def command_verify_prompt(_: argparse.Namespace) -> int:
    prompt_path = Path(required_env("TRUSTED_PROMPT"))
    try:
        if not prompt_path.is_file():
            raise fatal(
                FailureCode.TRUSTED_PROMPT_MISSING,
                "trusted architect-review prompt is missing from the base SHA",
                "trusted_prompt",
            )
        prompt_bytes = prompt_path.stat().st_size
        max_prompt_bytes = int(required_env("MAX_PROMPT_BYTES"))
        write_job_summary(
            "\n".join(
                [
                    "## Review Prompt",
                    "",
                    f"- Prompt: `{format_bytes(prompt_bytes)}`",
                    f"- Max prompt: `{format_bytes(max_prompt_bytes)}`",
                    "",
                ]
            )
        )
        if prompt_bytes > max_prompt_bytes:
            github_output(
                {
                    "prompt_ok": "false",
                    "prompt_bytes": str(prompt_bytes),
                    "should_comment": "true",
                    "review_status": "skipped",
                    "final_message": skipped_review_message(
                        "Prompt budget exceeded",
                        (
                            f"trusted prompt size {prompt_bytes} bytes exceeds "
                            f"{max_prompt_bytes} bytes; Prompt truncated/skipped"
                        ),
                    ),
                }
            )
            return 0
        github_output(
            {
                "prompt_ok": "true",
                "prompt_bytes": str(prompt_bytes),
                "should_comment": "false",
                "review_status": "prompt_ok",
                "final_message": "",
            }
        )
        return 0
    except BaseException as error:
        return fail_command(
            error,
            pr_number=os.environ.get("PR_NUMBER", ""),
            head_sha=os.environ.get("HEAD_SHA", ""),
        )


def command_check_api_key(_: argparse.Namespace) -> int:
    try:
        if os.environ.get("HAS_OPENAI_API_KEY") != "true":
            raise fatal(
                FailureCode.PERMISSION_ERROR,
                "OPENAI_API_KEY is not available for this trusted reviewer event",
                "openai_api_key",
            )
        return 0
    except BaseException as error:
        return fail_command(
            error,
            pr_number=os.environ.get("PR_NUMBER", ""),
            head_sha=os.environ.get("HEAD_SHA", ""),
        )


def command_sleep_before_retry(args: argparse.Namespace) -> int:
    retry_attempt = int(args.attempt) - 1
    delay_index = max(0, retry_attempt - 1)
    delay = RETRY_DELAYS_SECONDS[delay_index]
    print(f"Waiting {delay} seconds before retry attempt {args.attempt}.")
    time.sleep(delay)
    return 0


def command_classify_codex_attempt(_: argparse.Namespace) -> int:
    attempt = int(required_env("CODEX_ATTEMPT"))
    outcome = required_env("CODEX_OUTCOME")
    message = os.environ.get("CODEX_MESSAGE", "")
    if outcome == "success":
        github_output({"should_retry": "false", "success_code": "UNKNOWN"})
        return 0
    if outcome != "failure":
        github_output({"should_retry": "false", "failure_code": "NOT_FAILED"})
        return 0
    failure = classify_codex_failure_message(message)
    github_output(
        {
            "should_retry": str(
                failure.failure_class is FailureClass.RETRYABLE
                and attempt < MAX_ATTEMPTS
            ).lower(),
            "failure_class": failure.failure_class.value,
            "failure_code": failure.code.value,
        }
    )
    if failure.failure_class is FailureClass.FATAL:
        return fail_command(
            failure,
            pr_number=os.environ.get("PR_NUMBER", ""),
            head_sha=os.environ.get("HEAD_SHA", ""),
        )
    if attempt >= MAX_ATTEMPTS:
        return fail_command(
            RetryExhausted(failure, attempt),
            pr_number=os.environ.get("PR_NUMBER", ""),
            head_sha=os.environ.get("HEAD_SHA", ""),
        )
    print(
        f"Codex attempt {attempt} classified as "
        f"{failure.failure_class.value}/{failure.code.value}; retrying."
    )
    return 0


def normalize_success_code(final_message: str) -> SuccessCode:
    match = re.search(r"^VERDICT:\s*(.+)$", final_message, flags=re.MULTILINE)
    verdict = match.group(1).strip() if match else "HUMAN_DECISION_REQUIRED"
    if verdict in {"APPROVE", "APPROVED"}:
        return SuccessCode.APPROVED
    if verdict == "CHANGES_REQUESTED":
        return SuccessCode.CHANGES_REQUESTED
    return SuccessCode.NEEDS_HUMAN


def command_finalize_codex(_: argparse.Namespace) -> int:
    outcomes = [
        os.environ.get("CODEX_OUTCOME_1", ""),
        os.environ.get("CODEX_OUTCOME_2", ""),
        os.environ.get("CODEX_OUTCOME_3", ""),
    ]
    messages = [
        os.environ.get("CODEX_MESSAGE_1", ""),
        os.environ.get("CODEX_MESSAGE_2", ""),
        os.environ.get("CODEX_MESSAGE_3", ""),
    ]
    for index, outcome in enumerate(outcomes):
        if outcome == "success":
            final_message = messages[index] or "VERDICT: HUMAN_DECISION_REQUIRED"
            success_code = normalize_success_code(final_message)
            print(
                f"Codex review completed with SUCCESS/{success_code.value} "
                f"on attempt {index + 1}."
            )
            github_output(
                {
                    "final_message": final_message,
                    "success_code": success_code.value,
                    "attempts": str(index + 1),
                    "review_status": "completed",
                }
            )
            return 0
    failure = retryable(
        FailureCode.NETWORK_ERROR,
        "Codex Action failed in all attempts; inspect action logs for provider details",
        "openai_codex_action",
    )
    return fail_command(
        RetryExhausted(failure, MAX_ATTEMPTS),
        pr_number=os.environ.get("PR_NUMBER", ""),
        head_sha=os.environ.get("HEAD_SHA", ""),
    )


def build_comment_body(
    *,
    final_message: str,
    reviewed_sha: str,
    prompt_version: str,
    policy_version: str,
    model: str,
    effort: str,
    review_status: str,
    total_files: str,
    reviewed_files: str,
    excluded_files: str,
    diff_bytes: str,
    prompt_bytes: str,
    workflow_run_id: str,
    repo: str,
) -> str:
    success_code = normalize_success_code(final_message)
    diff_display = format_bytes(int(diff_bytes or "0"))
    prompt_display = format_bytes(int(prompt_bytes or "0"))
    return "\n".join(
        [
            COMMENT_MARKER,
            "",
            "## Automated Architect Review",
            "",
            "> This is an AI-generated review. It does not replace human merge judgment.",
            "",
            f"- Reviewed commit: `{reviewed_sha}`",
            f"- Workflow run: [{workflow_run_id}](https://github.com/{repo}/actions/runs/{workflow_run_id})",
            f"- Prompt version: `{prompt_version}`",
            f"- Verdict: `VERDICT: {success_code.value}`",
            "",
            "### Review Policy",
            "",
            f"- Policy: `{policy_version}`",
            f"- Model: `{model}`",
            f"- Reasoning: `{effort}`",
            f"- Files: `{reviewed_files}` reviewed / `{total_files}` changed",
            f"- Excluded files: `{excluded_files}`",
            f"- Diff: `{diff_display}`",
            f"- Prompt: `{prompt_display}`",
            f"- Review: `{review_status}`",
            "",
            final_message,
        ]
    )


def iter_issue_comments(repo: str, issue_number: str, token: str) -> Iterable[dict[str, Any]]:
    next_path = f"/repos/{repo}/issues/{issue_number}/comments?per_page=100"
    while next_path:
        data, headers = github_json("GET", next_path, token=token)
        if isinstance(data, list):
            yield from data
        next_path = parse_next_link(headers.get("Link", ""))


def parse_next_link(link_header: str) -> str:
    for section in link_header.split(","):
        if 'rel="next"' not in section:
            continue
        match = re.search(r"<https://api.github.com([^>]+)>", section)
        if match:
            return match.group(1)
    return ""


def command_post_comment(_: argparse.Namespace) -> int:
    token = required_env("GITHUB_TOKEN")
    repo = required_env("GITHUB_REPOSITORY")
    issue_number = required_env("PR_NUMBER")
    reviewed_sha = required_env("REVIEWED_SHA")
    prompt_version = required_env("PROMPT_VERSION")
    policy_version = required_env("POLICY_VERSION")
    model = required_env("REVIEW_MODEL")
    effort = required_env("REVIEW_EFFORT")
    review_status = required_env("REVIEW_STATUS")
    total_files = required_env("TOTAL_FILES")
    reviewed_files = required_env("REVIEWED_FILES")
    excluded_files = required_env("EXCLUDED_FILES")
    diff_bytes = required_env("DIFF_BYTES")
    prompt_bytes = required_env("PROMPT_BYTES")
    workflow_run_id = required_env("WORKFLOW_RUN_ID")
    final_message = os.environ.get("FINAL_MESSAGE") or "VERDICT: HUMAN_DECISION_REQUIRED"
    body = build_comment_body(
        final_message=final_message,
        reviewed_sha=reviewed_sha,
        prompt_version=prompt_version,
        policy_version=policy_version,
        model=model,
        effort=effort,
        review_status=review_status,
        total_files=total_files,
        reviewed_files=reviewed_files,
        excluded_files=excluded_files,
        diff_bytes=diff_bytes,
        prompt_bytes=prompt_bytes,
        workflow_run_id=workflow_run_id,
        repo=repo,
    )

    def operation() -> None:
        comments = list(iter_issue_comments(repo, issue_number, token))
        existing = next(
            (
                comment
                for comment in comments
                if isinstance(comment.get("body"), str) and COMMENT_MARKER in comment["body"]
            ),
            None,
        )
        if existing:
            github_json(
                "PATCH",
                f"/repos/{repo}/issues/comments/{existing['id']}",
                token=token,
                body={"body": body},
            )
        else:
            github_json(
                "POST",
                f"/repos/{repo}/issues/{issue_number}/comments",
                token=token,
                body={"body": body},
            )

    try:
        run_with_retry("github_comment", operation)
        return 0
    except BaseException as error:
        return fail_command(error, pr_number=issue_number, head_sha=reviewed_sha)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("load-policy").set_defaults(func=command_load_policy)
    subparsers.add_parser("download-artifact").set_defaults(func=command_download_artifact)
    subparsers.add_parser("validate-review-input").set_defaults(
        func=command_validate_review_input
    )
    subparsers.add_parser("verify-prompt").set_defaults(func=command_verify_prompt)
    subparsers.add_parser("check-api-key").set_defaults(func=command_check_api_key)
    sleep_parser = subparsers.add_parser("sleep-before-retry")
    sleep_parser.add_argument("--attempt", required=True, type=int)
    sleep_parser.set_defaults(func=command_sleep_before_retry)
    subparsers.add_parser("classify-codex-attempt").set_defaults(
        func=command_classify_codex_attempt
    )
    subparsers.add_parser("finalize-codex").set_defaults(func=command_finalize_codex)
    subparsers.add_parser("post-comment").set_defaults(func=command_post_comment)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
