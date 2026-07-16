from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
import urllib.error
import warnings
import zipfile
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "architect_review_retry.py"
)
SPEC = importlib.util.spec_from_file_location("architect_review_retry", SCRIPT_PATH)
architect_review_retry = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = architect_review_retry
SPEC.loader.exec_module(architect_review_retry)


class ArchitectReviewRetryTests(unittest.TestCase):
    def retryable_error(self):
        return architect_review_retry.retryable(
            architect_review_retry.FailureCode.NETWORK_ERROR,
            "temporary network failure",
            "test_operation",
        )

    def fatal_error(self, code):
        return architect_review_retry.fatal(
            code,
            "fatal failure",
            "test_operation",
        )

    def test_retryable_first_failure_second_success(self):
        attempts = []
        sleeps = []

        def operation():
            attempts.append(len(attempts) + 1)
            if len(attempts) == 1:
                raise self.retryable_error()
            return "ok"

        result = architect_review_retry.run_with_retry(
            "test_operation",
            operation,
            sleep_func=sleeps.append,
        )

        self.assertEqual("ok", result.value)
        self.assertEqual(2, result.attempts)
        self.assertEqual([30], sleeps)

    def test_retryable_two_failures_third_success(self):
        attempts = []
        sleeps = []

        def operation():
            attempts.append(len(attempts) + 1)
            if len(attempts) < 3:
                raise self.retryable_error()
            return "ok"

        result = architect_review_retry.run_with_retry(
            "test_operation",
            operation,
            sleep_func=sleeps.append,
        )

        self.assertEqual("ok", result.value)
        self.assertEqual(3, result.attempts)
        self.assertEqual([30, 60], sleeps)

    def test_retryable_three_failures_stop(self):
        attempts = []
        sleeps = []

        def operation():
            attempts.append(len(attempts) + 1)
            raise self.retryable_error()

        with self.assertRaises(architect_review_retry.RetryExhausted) as raised:
            architect_review_retry.run_with_retry(
                "test_operation",
                operation,
                sleep_func=sleeps.append,
            )

        self.assertEqual(3, raised.exception.attempts)
        self.assertEqual([30, 60], sleeps)
        self.assertEqual(3, len(attempts))

    def test_retry_delay_schedule_is_documented(self):
        self.assertEqual((30, 60, 120), architect_review_retry.RETRY_DELAYS_SECONDS)

    def test_rate_limit_is_retryable(self):
        failure = architect_review_retry.classify_http_status(
            429,
            "rate limit",
            "openai_codex_action",
        )
        self.assertEqual(architect_review_retry.FailureClass.RETRYABLE, failure.failure_class)
        self.assertEqual(architect_review_retry.FailureCode.RATE_LIMIT, failure.code)

    def test_timeout_is_retryable(self):
        failure = architect_review_retry.classify_exception(
            TimeoutError("timed out"),
            "openai_codex_action",
        )
        self.assertEqual(architect_review_retry.FailureClass.RETRYABLE, failure.failure_class)
        self.assertEqual(architect_review_retry.FailureCode.API_TIMEOUT, failure.code)

    def test_github_5xx_is_retryable(self):
        failure = architect_review_retry.classify_http_status(
            503,
            "service unavailable",
            "github_comment",
        )
        self.assertEqual(architect_review_retry.FailureClass.RETRYABLE, failure.failure_class)
        self.assertEqual(architect_review_retry.FailureCode.GITHUB_5XX, failure.code)

    def test_openai_5xx_is_retryable(self):
        failure = architect_review_retry.classify_http_status(
            500,
            "server error",
            "openai_codex_action",
        )
        self.assertEqual(architect_review_retry.FailureClass.RETRYABLE, failure.failure_class)
        self.assertEqual(architect_review_retry.FailureCode.OPENAI_5XX, failure.code)

    def test_github_429_is_retryable(self):
        failure = architect_review_retry.classify_http_status(
            429,
            "too many requests",
            "github_comment",
        )
        self.assertEqual(architect_review_retry.FailureClass.RETRYABLE, failure.failure_class)
        self.assertEqual(architect_review_retry.FailureCode.GITHUB_429, failure.code)

    def test_network_error_is_retryable(self):
        failure = architect_review_retry.classify_exception(
            urllib.error.URLError("temporary name resolution failure"),
            "github_comment",
        )
        self.assertEqual(architect_review_retry.FailureClass.RETRYABLE, failure.failure_class)
        self.assertEqual(architect_review_retry.FailureCode.NETWORK_ERROR, failure.code)

    def test_cross_origin_redirect_strips_authorization(self):
        headers = {
            "Authorization": "Bearer secret",
            "Accept": "application/vnd.github+json",
            "User-Agent": "test",
        }
        redirected = architect_review_retry.headers_for_redirect(
            "https://api.github.com/repos/x/y/actions/artifacts/1/zip",
            "https://pipelines.actions.githubusercontent.com/artifact.zip",
            headers,
        )
        self.assertNotIn("Authorization", redirected)
        self.assertEqual("application/vnd.github+json", redirected["Accept"])

    def test_same_origin_redirect_keeps_authorization(self):
        headers = {
            "Authorization": "Bearer secret",
            "Accept": "application/vnd.github+json",
        }
        redirected = architect_review_retry.headers_for_redirect(
            "https://api.github.com/repos/x/y",
            "https://api.github.com/repos/x/y?next=1",
            headers,
        )
        self.assertEqual("Bearer secret", redirected["Authorization"])

    def test_codex_rate_limit_is_retryable(self):
        failure = architect_review_retry.classify_codex_failure_message(
            "OpenAI API HTTP 429 rate limit"
        )
        self.assertEqual(architect_review_retry.FailureClass.RETRYABLE, failure.failure_class)
        self.assertEqual(architect_review_retry.FailureCode.RATE_LIMIT, failure.code)

    def test_codex_permission_error_is_fatal(self):
        failure = architect_review_retry.classify_codex_failure_message(
            "OpenAI API key unauthorized HTTP 401"
        )
        self.assertEqual(architect_review_retry.FailureClass.FATAL, failure.failure_class)
        self.assertEqual(architect_review_retry.FailureCode.PERMISSION_ERROR, failure.code)

    def test_codex_unknown_failure_is_fatal(self):
        failure = architect_review_retry.classify_codex_failure_message(
            "action configuration failed"
        )
        self.assertEqual(architect_review_retry.FailureClass.FATAL, failure.failure_class)
        self.assertEqual(
            architect_review_retry.FailureCode.WORKFLOW_CONFIGURATION_ERROR,
            failure.code,
        )

    def test_codex_empty_failure_details_are_retryable_after_preflight(self):
        failure = architect_review_retry.classify_codex_failure_message("")
        self.assertEqual(architect_review_retry.FailureClass.RETRYABLE, failure.failure_class)
        self.assertEqual(architect_review_retry.FailureCode.NETWORK_ERROR, failure.code)

    def assert_fatal_without_retry(self, failure):
        sleeps = []
        attempts = []

        def operation():
            attempts.append(1)
            raise failure

        with self.assertRaises(architect_review_retry.ReviewFailure):
            architect_review_retry.run_with_retry(
                "test_operation",
                operation,
                sleep_func=sleeps.append,
            )
        self.assertEqual(1, len(attempts))
        self.assertEqual([], sleeps)

    def test_trusted_prompt_missing_is_fatal_without_retry(self):
        self.assert_fatal_without_retry(
            self.fatal_error(architect_review_retry.FailureCode.TRUSTED_PROMPT_MISSING)
        )

    def test_invalid_manifest_is_fatal_without_retry(self):
        self.assert_fatal_without_retry(
            self.fatal_error(architect_review_retry.FailureCode.INVALID_MANIFEST)
        )

    def test_sha_mismatch_is_fatal_without_retry(self):
        self.assert_fatal_without_retry(
            self.fatal_error(architect_review_retry.FailureCode.SHA_MISMATCH)
        )

    def test_stale_artifact_is_fatal_without_retry(self):
        self.assert_fatal_without_retry(
            self.fatal_error(architect_review_retry.FailureCode.STALE_ARTIFACT)
        )

    def test_permission_error_is_fatal_without_retry(self):
        failure = architect_review_retry.classify_http_status(
            403,
            "forbidden",
            "github_comment",
        )
        self.assertEqual(architect_review_retry.FailureClass.FATAL, failure.failure_class)
        self.assertEqual(architect_review_retry.FailureCode.PERMISSION_ERROR, failure.code)
        self.assert_fatal_without_retry(failure)

    def test_path_traversal_is_fatal_without_retry(self):
        self.assert_fatal_without_retry(
            self.fatal_error(architect_review_retry.FailureCode.PATH_TRAVERSAL)
        )

    def zip_bytes(self, entries):
        import io

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, content in entries:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
                    archive.writestr(name, content)
        return buffer.getvalue()

    def test_artifact_path_traversal_is_rejected_before_extraction(self):
        data = self.zip_bytes(
            [
                ("manifest.json", "{}"),
                ("../review.diff", "diff"),
            ]
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "review-input"
            with self.assertRaises(architect_review_retry.ReviewFailure) as raised:
                architect_review_retry.safe_extract_zip(data, target, max_bytes=1000)
            self.assertEqual(
                architect_review_retry.FailureCode.PATH_TRAVERSAL,
                raised.exception.code,
            )
            self.assertFalse(target.exists())

    def test_artifact_oversized_member_is_rejected(self):
        data = self.zip_bytes(
            [
                ("manifest.json", "{}"),
                ("review.diff", "x" * 200),
            ]
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "review-input"
            with self.assertRaises(architect_review_retry.ReviewFailure) as raised:
                architect_review_retry.safe_extract_zip(data, target, max_bytes=100)
            self.assertEqual(
                architect_review_retry.FailureCode.INVALID_MANIFEST,
                raised.exception.code,
            )
            self.assertFalse(target.exists())

    def test_artifact_extra_member_is_rejected(self):
        data = self.zip_bytes(
            [
                ("manifest.json", "{}"),
                ("review.diff", "diff"),
                ("extra.txt", "extra"),
            ]
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "review-input"
            with self.assertRaises(architect_review_retry.ReviewFailure) as raised:
                architect_review_retry.safe_extract_zip(data, target, max_bytes=1000)
            self.assertEqual(
                architect_review_retry.FailureCode.INVALID_MANIFEST,
                raised.exception.code,
            )
            self.assertFalse(target.exists())

    def test_artifact_duplicate_member_is_rejected(self):
        data = self.zip_bytes(
            [
                ("review.diff", "diff"),
                ("review.diff", "again"),
            ]
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "review-input"
            with self.assertRaises(architect_review_retry.ReviewFailure) as raised:
                architect_review_retry.safe_extract_zip(data, target, max_bytes=1000)
            self.assertEqual(
                architect_review_retry.FailureCode.INVALID_MANIFEST,
                raised.exception.code,
            )
            self.assertFalse(target.exists())

    def base_manifest(self, diff_bytes):
        return {
            "actor": "uchuu",
            "author_association": "OWNER",
            "base_repository": "Vectology-cloud-team/namma-rogue-agent",
            "base_sha": "a" * 40,
            "binary_file_count": 0,
            "binary_files_omitted": [],
            "changed_file_count": 1,
            "collector_workflow_name": "Architect Review Collect",
            "collector_workflow_run_id": 123,
            "diff_bytes": diff_bytes,
            "draft": False,
            "head_repository": "Vectology-cloud-team/namma-rogue-agent",
            "head_sha": "b" * 40,
            "limits": {
                "max_diff_bytes": 200000,
                "max_changed_files": 200,
                "max_artifact_bytes": 250000,
            },
            "merge_sha": "c" * 40,
            "pull_request_number": 13,
            "repository": "Vectology-cloud-team/namma-rogue-agent",
            "schema_version": "architect-review-input-v1",
        }

    def with_manifest_validation_env(self, func):
        saved = os.environ.copy()
        os.environ.update(
            {
                "EXPECTED_REPOSITORY": "Vectology-cloud-team/namma-rogue-agent",
                "EXPECTED_COLLECTOR_WORKFLOW": "Architect Review Collect",
                "WORKFLOW_RUN_ID": "123",
                "MAX_DIFF_BYTES": "200000",
                "MAX_CHANGED_FILES": "200",
                "MAX_ARTIFACT_BYTES": "250000",
            }
        )
        try:
            return func()
        finally:
            os.environ.clear()
            os.environ.update(saved)

    def assert_manifest_field_rejected(self, field, value, expected_code):
        def run_validation():
            with tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                diff_path = root / "review.diff"
                manifest_path = root / "manifest.json"
                diff_path.write_text("diff", encoding="utf-8")
                manifest_path.write_text("{}", encoding="utf-8")
                manifest = self.base_manifest(diff_path.stat().st_size)
                manifest[field] = value
                with self.assertRaises(architect_review_retry.ReviewFailure) as raised:
                    architect_review_retry.validate_manifest_shape(
                        manifest,
                        diff_path=diff_path,
                        manifest_path=manifest_path,
                    )
                self.assertEqual(expected_code, raised.exception.code)

        self.with_manifest_validation_env(run_validation)

    def live_pull(self):
        return {
            "number": 13,
            "base": {
                "sha": "a" * 40,
                "repo": {"full_name": "Vectology-cloud-team/namma-rogue-agent"},
            },
            "head": {
                "sha": "b" * 40,
                "repo": {"full_name": "Vectology-cloud-team/namma-rogue-agent"},
            },
        }

    def test_manifest_pull_request_number_rejects_boolean(self):
        self.assert_manifest_field_rejected(
            "pull_request_number",
            True,
            architect_review_retry.FailureCode.PR_MISMATCH,
        )

    def test_manifest_changed_file_count_rejects_boolean(self):
        self.assert_manifest_field_rejected(
            "changed_file_count",
            False,
            architect_review_retry.FailureCode.INVALID_MANIFEST,
        )

    def test_manifest_diff_bytes_rejects_boolean(self):
        self.assert_manifest_field_rejected(
            "diff_bytes",
            True,
            architect_review_retry.FailureCode.INVALID_MANIFEST,
        )

    def test_manifest_changed_file_count_rejects_negative(self):
        self.assert_manifest_field_rejected(
            "changed_file_count",
            -1,
            architect_review_retry.FailureCode.INVALID_MANIFEST,
        )

    def test_manifest_diff_bytes_rejects_negative(self):
        self.assert_manifest_field_rejected(
            "diff_bytes",
            -1,
            architect_review_retry.FailureCode.INVALID_MANIFEST,
        )

    def test_live_pull_request_base_sha_mismatch_is_stale(self):
        manifest = self.base_manifest(4)
        pull = self.live_pull()
        pull["base"]["sha"] = "d" * 40
        with self.assertRaises(architect_review_retry.ReviewFailure) as raised:
            architect_review_retry.validate_live_pull_request(manifest, pull)
        self.assertEqual(
            architect_review_retry.FailureCode.STALE_ARTIFACT,
            raised.exception.code,
        )

    def test_live_pull_request_base_repo_mismatch_is_rejected(self):
        manifest = self.base_manifest(4)
        pull = self.live_pull()
        pull["base"]["repo"]["full_name"] = "attacker/fork"
        with self.assertRaises(architect_review_retry.ReviewFailure) as raised:
            architect_review_retry.validate_live_pull_request(manifest, pull)
        self.assertEqual(
            architect_review_retry.FailureCode.REPOSITORY_MISMATCH,
            raised.exception.code,
        )

    def test_refresh_review_diff_overwrites_artifact_diff_with_live_diff(self):
        original = architect_review_retry.github_api_request

        def fake_github_api_request(method, api_path, **kwargs):
            self.assertEqual("GET", method)
            self.assertEqual("/repos/Vectology-cloud-team/namma-rogue-agent/pulls/13", api_path)
            self.assertEqual("application/vnd.github.v3.diff", kwargs["accept"])
            return b"trusted live diff", {}

        architect_review_retry.github_api_request = fake_github_api_request
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                diff_path = Path(temp_dir) / "review.diff"
                diff_path.write_bytes(b"forged same-size")
                architect_review_retry.refresh_review_diff_from_github(
                    repo="Vectology-cloud-team/namma-rogue-agent",
                    pull_request_number=13,
                    token="token",
                    diff_path=diff_path,
                    max_diff_bytes=1000,
                )
                self.assertEqual(b"trusted live diff", diff_path.read_bytes())
        finally:
            architect_review_retry.github_api_request = original

    def test_live_pull_request_revalidation_detects_head_change_after_diff(self):
        manifest = self.base_manifest(4)
        initial_pull = self.live_pull()
        changed_pull = self.live_pull()
        changed_pull["head"]["sha"] = "d" * 40
        architect_review_retry.validate_live_pull_request(manifest, initial_pull)
        with self.assertRaises(architect_review_retry.ReviewFailure) as raised:
            architect_review_retry.validate_live_pull_request(manifest, changed_pull)
        self.assertEqual(
            architect_review_retry.FailureCode.STALE_ARTIFACT,
            raised.exception.code,
        )

    def test_success_approved_does_not_fail_workflow(self):
        self.assertEqual(
            architect_review_retry.SuccessCode.APPROVED,
            architect_review_retry.normalize_success_code("VERDICT: APPROVE\n"),
        )

    def test_success_changes_requested_does_not_fail_workflow(self):
        self.assertEqual(
            architect_review_retry.SuccessCode.CHANGES_REQUESTED,
            architect_review_retry.normalize_success_code("VERDICT: CHANGES_REQUESTED\n"),
        )

    def test_success_needs_human_does_not_fail_workflow(self):
        self.assertEqual(
            architect_review_retry.SuccessCode.NEEDS_HUMAN,
            architect_review_retry.normalize_success_code(
                "VERDICT: HUMAN_DECISION_REQUIRED\n"
            ),
        )

    def test_secret_values_are_redacted_from_logs(self):
        message = "Bearer ghp_secret123 and sk-secret-value should not appear"
        sanitized = architect_review_retry.sanitize_error(message)
        self.assertNotIn("ghp_secret123", sanitized)
        self.assertNotIn("sk-secret-value", sanitized)

    def test_failure_summary_includes_class_code_and_attempts(self):
        failure = self.retryable_error()
        summary = architect_review_retry.failure_summary(
            failure,
            attempts=3,
            pr_number="12",
            head_sha="a" * 40,
        )
        self.assertIn("`RETRYABLE`", summary)
        self.assertIn("`NETWORK_ERROR`", summary)
        self.assertIn("`3`", summary)
        self.assertIn("human should inspect", summary)

    def test_failure_summary_does_not_use_sticky_review_marker(self):
        failure = self.retryable_error()
        summary = architect_review_retry.failure_summary(
            failure,
            attempts=3,
            pr_number="12",
            head_sha="a" * 40,
        )
        self.assertNotIn("<!-- namma-ai-architect-review -->", summary)

    def test_comment_body_preserves_sticky_marker(self):
        body = architect_review_retry.build_comment_body(
            final_message="VERDICT: CHANGES_REQUESTED\n\nSUMMARY\nNeeds work.",
            reviewed_sha="b" * 40,
            prompt_version="architect-review-v1",
            workflow_run_id="123",
            repo="Vectology-cloud-team/namma-rogue-agent",
        )
        self.assertIn("<!-- namma-ai-architect-review -->", body)
        self.assertIn("Reviewed commit", body)
        self.assertIn("VERDICT: CHANGES_REQUESTED", body)


if __name__ == "__main__":
    unittest.main()
