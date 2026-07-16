from __future__ import annotations

import importlib.util
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
