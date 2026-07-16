from __future__ import annotations

import copy
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
import zipfile
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "fix_proposal_generator.py"
)
SCRIPTS_DIR = SCRIPT_PATH.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
SPEC = importlib.util.spec_from_file_location("fix_proposal_generator", SCRIPT_PATH)
fix_proposal_generator = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = fix_proposal_generator
SPEC.loader.exec_module(fix_proposal_generator)


FULL_SHA_A = "a" * 40
FULL_SHA_B = "b" * 40
FULL_SHA_C = "c" * 40


class FixProposalGeneratorTests(unittest.TestCase):
    def setUp(self):
        self.policy = fix_proposal_generator.load_fix_proposal_policy(
            fix_proposal_generator.REPO_ROOT
            / ".github"
            / "codex"
            / "fix-policy.yml"
        )

    def request_manifest(self):
        return {
            "schema_version": "fix-proposal-request-v1",
            "repository": "Vectology-cloud-team/namma-rogue-agent",
            "pull_request_number": 16,
            "base_sha": FULL_SHA_A,
            "head_sha": FULL_SHA_B,
            "actor": "uchuu",
            "author_association": "MEMBER",
            "draft": False,
            "base_repository": "Vectology-cloud-team/namma-rogue-agent",
            "head_repository": "Vectology-cloud-team/namma-rogue-agent",
            "labels": ["ai-fix-proposal"],
            "collector_workflow_name": "Fix Proposal Request Collect",
            "collector_workflow_run_id": 123,
        }

    def pull(self):
        return {
            "number": 16,
            "draft": False,
            "author_association": "MEMBER",
            "user": {"type": "User"},
            "labels": [{"name": "ai-fix-proposal"}],
            "base": {"sha": FULL_SHA_A},
            "head": {
                "sha": FULL_SHA_B,
                "repo": {"full_name": "Vectology-cloud-team/namma-rogue-agent"},
            },
        }

    def review_result(self):
        return {
            "schema_version": "architect-review-result-v1",
            "repository": "Vectology-cloud-team/namma-rogue-agent",
            "pull_request_number": 16,
            "base_sha": FULL_SHA_A,
            "reviewed_head_sha": FULL_SHA_B,
            "workflow_run_id": 456,
            "review_artifact_id": "architect-review-result-456",
            "review_status": "completed",
            "verdict": "CHANGES_REQUESTED",
            "prompt_version": "architect-review-v1",
            "policy_version": "policy",
            "model": "gpt-5.5",
            "reasoning_effort": "medium",
            "generated_at": "2026-07-16T00:00:00Z",
            "findings": [
                {
                    "finding_id": "finding-1",
                    "severity": "high",
                    "category": "correctness",
                    "file": "src/example.py",
                    "line": 1,
                    "message": "Fix the inconsistency.",
                    "suggestion": "Change the sentence.",
                    "blocking": True,
                }
            ],
        }

    def valid_patch(self, path="src/example.py"):
        return (
            f"diff --git a/{path} b/{path}\n"
            f"--- a/{path}\n"
            f"+++ b/{path}\n"
            "@@ -1 +1 @@\n"
            "-old\n"
            "+new\n"
        )

    def proposal(self, path="src/example.py"):
        return {
            "schema_version": "1.0",
            "proposal_id": "temporary-proposal-id",
            "repository": "Vectology-cloud-team/namma-rogue-agent",
            "pull_request_number": 16,
            "base_sha": FULL_SHA_A,
            "head_sha": FULL_SHA_B,
            "source_review_run_id": 456,
            "source_review_artifact_id": "architect-review-result-456",
            "reviewed_at": "2026-07-16T00:00:00Z",
            "generator": {
                "model": "gpt-5.5",
                "reasoning_effort": "medium",
                "policy_version": self.policy.policy_hash,
            },
            "summary": "Fix the reviewed inconsistency.",
            "findings_addressed": [
                {
                    "finding_id": "finding-1",
                    "severity": "high",
                    "category": "correctness",
                }
            ],
            "changes": [
                {
                    "path": path,
                    "operation": "modify",
                    "original_blob_sha": FULL_SHA_C,
                    "patch": self.valid_patch(path),
                    "rationale": "Address the blocking Stage 1 finding.",
                }
            ],
            "tests_recommended": ["python -m unittest discover"],
            "risks": ["Low risk documentation change."],
            "human_approval_required": True,
        }

    def input_hash(self):
        return fix_proposal_generator.proposal_input_hash(
            request_manifest=self.request_manifest(),
            review_result=self.review_result(),
            policy_hash=self.policy.policy_hash,
        )

    def target_contents(self, path="src/example.py", content="old\n"):
        return {
            "schema_version": "fix-target-contents-v1",
            "files": [
                {
                    "path": path,
                    "blob_sha": FULL_SHA_C,
                    "content_sha256": fix_proposal_generator.sha256_hex_bytes(
                        content.encode("utf-8")
                    ),
                    "content": content,
                }
            ],
        }

    def assert_gate_code(self, request, pull, review, code):
        decision = fix_proposal_generator.evaluate_generation_gate(
            request_manifest=request,
            pull=pull,
            review_result=review,
            policy=self.policy,
        )
        self.assertFalse(decision.should_generate)
        self.assertEqual(code, decision.code)

    def validate(self, proposal=None, original_blob_shas=None):
        return fix_proposal_generator.validate_verified_proposal(
            proposal or self.proposal(),
            request_manifest=self.request_manifest(),
            review_result=self.review_result(),
            policy=self.policy,
            proposal_input_hash_value=self.input_hash(),
            original_blob_shas=original_blob_shas or {"src/example.py": FULL_SHA_C},
            target_contents=self.target_contents(),
            generator_metadata={
                "model": self.policy.model,
                "reasoning_effort": self.policy.reasoning_effort,
                "policy_version": self.policy.policy_hash,
            },
        )

    def test_label_missing_skips_generation(self):
        pull = self.pull()
        pull["labels"] = []
        self.assert_gate_code(
            self.request_manifest(),
            pull,
            self.review_result(),
            "LABEL_MISSING",
        )

    def test_draft_is_rejected(self):
        pull = self.pull()
        pull["draft"] = True
        self.assert_gate_code(
            self.request_manifest(),
            pull,
            self.review_result(),
            "DRAFT_PULL_REQUEST",
        )

    def test_fork_is_rejected(self):
        pull = self.pull()
        pull["head"]["repo"]["full_name"] = "someone/fork"
        self.assert_gate_code(
            self.request_manifest(),
            pull,
            self.review_result(),
            "FORK_PULL_REQUEST",
        )

    def test_bot_is_rejected(self):
        pull = self.pull()
        pull["user"]["type"] = "Bot"
        self.assert_gate_code(
            self.request_manifest(),
            pull,
            self.review_result(),
            "BOT_PULL_REQUEST",
        )

    def test_unauthorized_association_is_rejected(self):
        pull = self.pull()
        pull["author_association"] = "CONTRIBUTOR"
        self.assert_gate_code(
            self.request_manifest(),
            pull,
            self.review_result(),
            "UNAUTHORIZED_ASSOCIATION",
        )

    def test_stale_request_is_rejected(self):
        pull = self.pull()
        pull["head"]["sha"] = "d" * 40
        self.assert_gate_code(
            self.request_manifest(),
            pull,
            self.review_result(),
            "STALE_ARTIFACT",
        )

    def test_stage1_reviewed_sha_mismatch_is_rejected(self):
        review = self.review_result()
        review["reviewed_head_sha"] = "d" * 40
        self.assert_gate_code(
            self.request_manifest(),
            self.pull(),
            review,
            "SHA_MISMATCH",
        )

    def test_stage1_base_sha_mismatch_is_rejected(self):
        review = self.review_result()
        review["base_sha"] = "d" * 40
        self.assert_gate_code(
            self.request_manifest(),
            self.pull(),
            review,
            "SHA_MISMATCH",
        )

    def test_blocking_finding_is_required(self):
        review = self.review_result()
        review["findings"] = []
        self.assert_gate_code(
            self.request_manifest(),
            self.pull(),
            review,
            "NO_BLOCKING_FINDINGS",
        )

    def test_approved_review_does_not_generate_even_with_blocking_finding(self):
        review = self.review_result()
        review["verdict"] = "APPROVED"
        self.assert_gate_code(
            self.request_manifest(),
            self.pull(),
            review,
            "REVIEW_NOT_READY",
        )

    def test_human_decision_review_does_not_generate_even_with_blocking_finding(self):
        review = self.review_result()
        review["verdict"] = "NEEDS_HUMAN"
        self.assert_gate_code(
            self.request_manifest(),
            self.pull(),
            review,
            "REVIEW_NOT_READY",
        )

    def test_fileless_blocking_finding_does_not_generate(self):
        review = self.review_result()
        review["findings"][0]["file"] = ""
        self.assert_gate_code(
            self.request_manifest(),
            self.pull(),
            review,
            "NO_BLOCKING_FINDINGS",
        )

    def test_blocking_finding_without_line_does_not_generate(self):
        review = self.review_result()
        review["findings"][0]["line"] = None
        self.assert_gate_code(
            self.request_manifest(),
            self.pull(),
            review,
            "NO_BLOCKING_FINDINGS",
        )

    def test_existing_same_input_proposal_skips_generation(self):
        input_hash = self.input_hash()
        decision = fix_proposal_generator.evaluate_generation_gate(
            request_manifest=self.request_manifest(),
            pull=self.pull(),
            review_result=self.review_result(),
            policy=self.policy,
            existing_proposals=[
                {
                    "metadata": {
                        "head_sha": FULL_SHA_B,
                        "proposal_input_hash": input_hash,
                        "status": "PROPOSAL_READY",
                    }
                }
            ],
        )
        self.assertFalse(decision.should_generate)
        self.assertEqual("DUPLICATE_PROPOSAL", decision.code)

    def test_valid_gate_generates(self):
        decision = fix_proposal_generator.evaluate_generation_gate(
            request_manifest=self.request_manifest(),
            pull=self.pull(),
            review_result=self.review_result(),
            policy=self.policy,
        )
        self.assertTrue(decision.should_generate)
        self.assertEqual(64, len(decision.input_hash))

    def test_malformed_json_is_rejected(self):
        with self.assertRaises(fix_proposal_generator.FixProposalFailure) as raised:
            fix_proposal_generator.parse_codex_json("{not json")
        self.assertEqual("INVALID_JSON", raised.exception.code.value)

    def test_schema_violation_is_rejected(self):
        proposal = self.proposal()
        del proposal["changes"]
        with self.assertRaises(fix_proposal_generator.FixProposalFailure) as raised:
            self.validate(proposal)
        self.assertEqual("INVALID_PROPOSAL", raised.exception.code.value)

    def test_protected_path_is_rejected(self):
        proposal = self.proposal(".github/workflows/fix-proposal.yml")
        with self.assertRaises(fix_proposal_generator.FixProposalFailure) as raised:
            self.validate(
                proposal,
                {".github/workflows/fix-proposal.yml": FULL_SHA_C},
            )
        self.assertEqual("PROTECTED_PATH", raised.exception.code.value)

    def test_original_blob_sha_mismatch_is_rejected(self):
        with self.assertRaises(fix_proposal_generator.FixProposalFailure) as raised:
            self.validate(original_blob_shas={"src/example.py": "d" * 40})
        self.assertEqual("ORIGINAL_BLOB_MISMATCH", raised.exception.code.value)

    def test_patch_that_does_not_apply_to_trusted_content_is_rejected(self):
        proposal = self.proposal()
        proposal["changes"][0]["patch"] = (
            "diff --git a/src/example.py b/src/example.py\n"
            "--- a/src/example.py\n"
            "+++ b/src/example.py\n"
            "@@ -1 +1 @@\n"
            "-different\n"
            "+new\n"
        )
        with self.assertRaises(fix_proposal_generator.FixProposalFailure) as raised:
            self.validate(proposal)
        self.assertEqual("PATCH_DOES_NOT_APPLY", raised.exception.code.value)

    def test_missing_trusted_target_content_is_rejected(self):
        proposal = self.proposal()
        with self.assertRaises(fix_proposal_generator.FixProposalFailure) as raised:
            fix_proposal_generator.validate_verified_proposal(
                proposal,
                request_manifest=self.request_manifest(),
                review_result=self.review_result(),
                policy=self.policy,
                proposal_input_hash_value=self.input_hash(),
                original_blob_shas={"src/example.py": FULL_SHA_C},
                target_contents={"schema_version": "fix-target-contents-v1", "files": []},
                generator_metadata={
                    "model": self.policy.model,
                    "reasoning_effort": self.policy.reasoning_effort,
                    "policy_version": self.policy.policy_hash,
                },
            )
        self.assertEqual("PATCH_DOES_NOT_APPLY", raised.exception.code.value)

    def test_duplicate_patch_hunks_are_rejected(self):
        proposal = self.proposal()
        proposal["changes"][0]["patch"] = (
            "diff --git a/src/example.py b/src/example.py\n"
            "--- a/src/example.py\n"
            "+++ b/src/example.py\n"
            "@@ -1 +1 @@\n"
            "-old\n"
            "+new\n"
            "@@ -1 +1 @@\n"
            "-old\n"
            "+newer\n"
        )
        with self.assertRaises(fix_proposal_generator.FixProposalFailure) as raised:
            self.validate(proposal)
        self.assertEqual("PATCH_DOES_NOT_APPLY", raised.exception.code.value)

    def test_out_of_order_patch_hunks_are_rejected(self):
        proposal = self.proposal()
        proposal["changes"][0]["patch"] = (
            "diff --git a/src/example.py b/src/example.py\n"
            "--- a/src/example.py\n"
            "+++ b/src/example.py\n"
            "@@ -2 +2 @@\n"
            "-second\n"
            "+second-new\n"
            "@@ -1 +1 @@\n"
            "-old\n"
            "+new\n"
        )
        with self.assertRaises(fix_proposal_generator.FixProposalFailure) as raised:
            fix_proposal_generator.validate_verified_proposal(
                proposal,
                request_manifest=self.request_manifest(),
                review_result=self.review_result(),
                policy=self.policy,
                proposal_input_hash_value=self.input_hash(),
                original_blob_shas={"src/example.py": FULL_SHA_C},
                target_contents=self.target_contents(content="old\nsecond\n"),
                generator_metadata={
                    "model": self.policy.model,
                    "reasoning_effort": self.policy.reasoning_effort,
                    "policy_version": self.policy.policy_hash,
                },
            )
        self.assertEqual("PATCH_DOES_NOT_APPLY", raised.exception.code.value)

    def test_fabricated_finding_id_is_rejected(self):
        proposal = self.proposal()
        proposal["findings_addressed"][0]["finding_id"] = "made-up"
        with self.assertRaises(fix_proposal_generator.FixProposalFailure) as raised:
            self.validate(proposal)
        self.assertEqual("FINDING_MISMATCH", raised.exception.code.value)

    def test_proposal_hash_is_deterministic(self):
        first_proposal, first_metadata = self.validate()
        second_proposal, second_metadata = self.validate()
        self.assertEqual(first_metadata["proposal_hash"], second_metadata["proposal_hash"])
        self.assertEqual(first_metadata["proposal_id"], second_metadata["proposal_id"])
        self.assertEqual(first_proposal["proposal_id"], second_proposal["proposal_id"])

    def test_different_change_changes_proposal_id(self):
        first, first_metadata = self.validate()
        proposal = self.proposal()
        proposal["summary"] = "A different summary."
        second, second_metadata = self.validate(proposal)
        self.assertNotEqual(first_metadata["proposal_hash"], second_metadata["proposal_hash"])
        self.assertNotEqual(first["proposal_id"], second["proposal_id"])

    def test_head_sha_change_is_stale(self):
        proposal = self.proposal()
        proposal["head_sha"] = "d" * 40
        verified, metadata = self.validate(proposal)
        self.assertEqual(FULL_SHA_B, verified["head_sha"])
        self.assertEqual(FULL_SHA_B, metadata["head_sha"])

    def test_untrusted_provenance_fields_are_overwritten(self):
        proposal = self.proposal()
        proposal["source_review_run_id"] = 999999
        proposal["source_review_artifact_id"] = "made-up"
        proposal["reviewed_at"] = "2099-01-01T00:00:00Z"
        proposal["generator"] = {
            "model": "untrusted-model",
            "reasoning_effort": "maximal",
            "policy_version": "untrusted-policy",
        }
        verified, _metadata = self.validate(proposal)
        self.assertEqual(456, verified["source_review_run_id"])
        self.assertEqual(
            "architect-review-result-456",
            verified["source_review_artifact_id"],
        )
        self.assertEqual("2026-07-16T00:00:00Z", verified["reviewed_at"])
        self.assertEqual("gpt-5.5", verified["generator"]["model"])
        self.assertEqual("medium", verified["generator"]["reasoning_effort"])
        self.assertEqual(self.policy.policy_hash, verified["generator"]["policy_version"])

    def test_trusted_review_provenance_changes_proposal_hash(self):
        _first, first_metadata = self.validate()
        review = self.review_result()
        review["workflow_run_id"] = 789
        review["review_artifact_id"] = "architect-review-result-789"
        proposal_input_hash = fix_proposal_generator.proposal_input_hash(
            request_manifest=self.request_manifest(),
            review_result=review,
            policy_hash=self.policy.policy_hash,
        )
        _second, second_metadata = fix_proposal_generator.validate_verified_proposal(
            self.proposal(),
            request_manifest=self.request_manifest(),
            review_result=review,
            policy=self.policy,
            proposal_input_hash_value=proposal_input_hash,
            original_blob_shas={"src/example.py": FULL_SHA_C},
            target_contents=self.target_contents(),
            generator_metadata={
                "model": self.policy.model,
                "reasoning_effort": self.policy.reasoning_effort,
                "policy_version": self.policy.policy_hash,
            },
        )
        self.assertNotEqual(first_metadata["proposal_hash"], second_metadata["proposal_hash"])

    def test_comment_is_sticky_and_does_not_include_full_patch(self):
        proposal, metadata = self.validate()
        body = fix_proposal_generator.proposal_comment_body(
            proposal=proposal,
            metadata=metadata,
            workflow_run_id="999",
            repo="Vectology-cloud-team/namma-rogue-agent",
            max_patch_bytes=1,
        )
        self.assertIn("<!-- namma-ai-fix-proposal -->", body)
        self.assertIn("Proposal input hash:", body)
        self.assertIn("No file changes, patch application, tests, commit, push, or merge", body)
        self.assertNotIn("@@ -1 +1 @@", body)

    def test_existing_proposal_comment_metadata_is_detected(self):
        proposal, metadata = self.validate()
        body = fix_proposal_generator.proposal_comment_body(
            proposal=proposal,
            metadata=metadata,
            workflow_run_id="999",
            repo="Vectology-cloud-team/namma-rogue-agent",
        )
        records = fix_proposal_generator.existing_proposal_records_from_comments(
            [{"body": body}]
        )
        self.assertEqual(1, len(records))
        self.assertEqual(metadata["head_sha"], records[0]["metadata"]["head_sha"])
        self.assertEqual(
            metadata["proposal_input_hash"],
            records[0]["metadata"]["proposal_input_hash"],
        )

    def test_fix_proposal_comment_creates_issue_comment_when_marker_missing(self):
        original_iter = fix_proposal_generator.stage1.iter_issue_comments
        original_github_json = fix_proposal_generator.stage1.github_json
        calls = []

        def fake_iter(_repo, _issue_number, _token):
            return iter([])

        def fake_github_json(method, api_path, **kwargs):
            calls.append((method, api_path, kwargs.get("body")))
            return {}, {}

        fix_proposal_generator.stage1.iter_issue_comments = fake_iter
        fix_proposal_generator.stage1.github_json = fake_github_json
        try:
            fix_proposal_generator.post_or_update_comment(
                repo="Vectology-cloud-team/namma-rogue-agent",
                issue_number="17",
                token="token",
                body="<!-- namma-ai-fix-proposal -->\nproposal",
            )
        finally:
            fix_proposal_generator.stage1.iter_issue_comments = original_iter
            fix_proposal_generator.stage1.github_json = original_github_json

        self.assertEqual(
            [
                (
                    "POST",
                    "/repos/Vectology-cloud-team/namma-rogue-agent/issues/17/comments",
                    {"body": "<!-- namma-ai-fix-proposal -->\nproposal"},
                )
            ],
            calls,
        )

    def test_fix_proposal_comment_updates_existing_marker_comment(self):
        original_iter = fix_proposal_generator.stage1.iter_issue_comments
        original_github_json = fix_proposal_generator.stage1.github_json
        calls = []

        def fake_iter(_repo, _issue_number, _token):
            return iter(
                [
                    {
                        "id": 12345,
                        "body": "<!-- namma-ai-fix-proposal -->\nold",
                    }
                ]
            )

        def fake_github_json(method, api_path, **kwargs):
            calls.append((method, api_path, kwargs.get("body")))
            return {}, {}

        fix_proposal_generator.stage1.iter_issue_comments = fake_iter
        fix_proposal_generator.stage1.github_json = fake_github_json
        try:
            fix_proposal_generator.post_or_update_comment(
                repo="Vectology-cloud-team/namma-rogue-agent",
                issue_number="17",
                token="token",
                body="<!-- namma-ai-fix-proposal -->\nnew",
            )
        finally:
            fix_proposal_generator.stage1.iter_issue_comments = original_iter
            fix_proposal_generator.stage1.github_json = original_github_json

        self.assertEqual(
            [
                (
                    "PATCH",
                    "/repos/Vectology-cloud-team/namma-rogue-agent/issues/comments/12345",
                    {"body": "<!-- namma-ai-fix-proposal -->\nnew"},
                )
            ],
            calls,
        )

    def test_fix_proposal_comment_retry_revalidates_and_relists(self):
        original_validate = fix_proposal_generator.stage1.validate_comment_target
        original_iter = fix_proposal_generator.stage1.iter_issue_comments
        original_github_json = fix_proposal_generator.stage1.github_json
        validate_calls = []
        list_calls = []
        write_calls = []
        list_responses = [
            [],
            [
                {
                    "id": 12345,
                    "body": "<!-- namma-ai-fix-proposal -->\nold",
                }
            ],
        ]

        def fake_validate(repo, issue_number, head_sha, token):
            validate_calls.append((repo, issue_number, head_sha, token))

        def fake_iter(repo, issue_number, token):
            list_calls.append((repo, issue_number, token))
            return iter(list_responses.pop(0))

        def fake_github_json(method, api_path, **kwargs):
            write_calls.append((method, api_path, kwargs.get("body")))
            if method == "POST":
                raise fix_proposal_generator.retryable(
                    fix_proposal_generator.FailureCode.NETWORK_ERROR,
                    "temporary network error",
                    "github_issue_comment_create",
                )
            return {}, {}

        fix_proposal_generator.stage1.validate_comment_target = fake_validate
        fix_proposal_generator.stage1.iter_issue_comments = fake_iter
        fix_proposal_generator.stage1.github_json = fake_github_json
        delays = []
        try:
            result = fix_proposal_generator.run_with_retry(
                "github_fix_proposal_comment",
                lambda: fix_proposal_generator.publish_fix_comment(
                    repo="Vectology-cloud-team/namma-rogue-agent",
                    issue_number="17",
                    head_sha=FULL_SHA_B,
                    token="token",
                    body="<!-- namma-ai-fix-proposal -->\nnew",
                ),
                sleep_func=delays.append,
            )
        finally:
            fix_proposal_generator.stage1.validate_comment_target = original_validate
            fix_proposal_generator.stage1.iter_issue_comments = original_iter
            fix_proposal_generator.stage1.github_json = original_github_json

        self.assertEqual(2, result.attempts)
        self.assertEqual([30], delays)
        self.assertEqual(2, len(validate_calls))
        self.assertEqual(2, len(list_calls))
        self.assertEqual(
            [
                (
                    "POST",
                    "/repos/Vectology-cloud-team/namma-rogue-agent/issues/17/comments",
                    {"body": "<!-- namma-ai-fix-proposal -->\nnew"},
                ),
                (
                    "PATCH",
                    "/repos/Vectology-cloud-team/namma-rogue-agent/issues/comments/12345",
                    {"body": "<!-- namma-ai-fix-proposal -->\nnew"},
                ),
            ],
            write_calls,
        )

    def test_fix_proposal_comment_retry_rechecks_stale_head_before_writing(self):
        original_validate = fix_proposal_generator.stage1.validate_comment_target
        original_iter = fix_proposal_generator.stage1.iter_issue_comments
        original_github_json = fix_proposal_generator.stage1.github_json
        validate_calls = []
        list_calls = []
        write_calls = []

        def fake_validate(repo, issue_number, head_sha, token):
            validate_calls.append((repo, issue_number, head_sha, token))
            if len(validate_calls) == 2:
                raise fix_proposal_generator.fatal(
                    fix_proposal_generator.FailureCode.STALE_ARTIFACT,
                    "pull request head changed before comment publication",
                    "github_fix_comment_target",
                )

        def fake_iter(repo, issue_number, token):
            list_calls.append((repo, issue_number, token))
            return iter([])

        def fake_github_json(method, api_path, **kwargs):
            write_calls.append((method, api_path, kwargs.get("body")))
            raise fix_proposal_generator.retryable(
                fix_proposal_generator.FailureCode.NETWORK_ERROR,
                "temporary network error",
                "github_issue_comment_create",
            )

        fix_proposal_generator.stage1.validate_comment_target = fake_validate
        fix_proposal_generator.stage1.iter_issue_comments = fake_iter
        fix_proposal_generator.stage1.github_json = fake_github_json
        delays = []
        try:
            with self.assertRaises(fix_proposal_generator.FixProposalFailure) as cm:
                fix_proposal_generator.run_with_retry(
                    "github_fix_proposal_comment",
                    lambda: fix_proposal_generator.publish_fix_comment(
                        repo="Vectology-cloud-team/namma-rogue-agent",
                        issue_number="17",
                        head_sha=FULL_SHA_B,
                        token="token",
                        body="<!-- namma-ai-fix-proposal -->\nnew",
                    ),
                    sleep_func=delays.append,
                )
        finally:
            fix_proposal_generator.stage1.validate_comment_target = original_validate
            fix_proposal_generator.stage1.iter_issue_comments = original_iter
            fix_proposal_generator.stage1.github_json = original_github_json

        self.assertEqual(
            fix_proposal_generator.FailureClass.FATAL,
            cm.exception.failure_class,
        )
        self.assertEqual(
            fix_proposal_generator.FailureCode.STALE_ARTIFACT,
            cm.exception.code,
        )
        self.assertEqual([30], delays)
        self.assertEqual(2, len(validate_calls))
        self.assertEqual(1, len(list_calls))
        self.assertEqual(1, len(write_calls))

    def test_fix_proposal_comment_uses_no_pull_request_review_api(self):
        script = SCRIPT_PATH.read_text(encoding="utf-8")
        self.assertNotIn("/pulls/{issue_number}/comments", script)
        self.assertNotIn("pulls.createReview", script)
        self.assertNotIn("pulls.createReviewComment", script)
        self.assertIn("/issues/{issue_number}/comments", script)
        self.assertIn("/issues/comments/{comment_id}", script)

    def test_forbidden_comment_permission_is_fatal_without_retry(self):
        error = urllib.error.HTTPError(
            "https://api.github.com/repos/example/repo/issues/17/comments",
            403,
            "Forbidden",
            {},
            None,
        )
        failure = fix_proposal_generator.classify_exception(
            error,
            "github_issue_comment_create",
        )
        self.assertEqual(
            fix_proposal_generator.FailureClass.FATAL,
            failure.failure_class,
        )
        self.assertEqual(
            fix_proposal_generator.FailureCode.PERMISSION_ERROR,
            failure.code,
        )

    def test_prepare_generation_defers_when_stage1_result_is_not_ready(self):
        original_find = fix_proposal_generator.find_latest_review_result_artifact
        original_github_json = fix_proposal_generator.stage1.github_json

        def missing_review_result(**_kwargs):
            raise fix_proposal_generator.fatal(
                fix_proposal_generator.FailureCode.REVIEW_NOT_READY,
                "no matching structured Stage 1 review result artifact was found",
                "stage1_review_lookup",
            )

        def fake_github_json(method, api_path, **_kwargs):
            self.assertEqual("GET", method)
            self.assertEqual(
                "/repos/Vectology-cloud-team/namma-rogue-agent/pulls/16",
                api_path,
            )
            return self.pull(), {}

        fix_proposal_generator.find_latest_review_result_artifact = missing_review_result
        fix_proposal_generator.stage1.github_json = fake_github_json
        old_env = os.environ.copy()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                request_dir = root / "request"
                review_dir = root / "review"
                request_dir.mkdir()
                review_dir.mkdir()
                (request_dir / "manifest.json").write_text(
                    json.dumps(self.request_manifest()),
                    encoding="utf-8",
                )
                output_path = root / "output.txt"
                summary_path = root / "summary.md"
                os.environ.update(
                    {
                        "GITHUB_REPOSITORY": "Vectology-cloud-team/namma-rogue-agent",
                        "GITHUB_TOKEN": "token",
                        "FIX_REQUEST_DIR": str(request_dir),
                        "REVIEW_RESULT_DIR": str(review_dir),
                        "FIX_POLICY": str(
                            Path(__file__).resolve().parents[1]
                            / ".github"
                            / "codex"
                            / "fix-policy.yml"
                        ),
                        "MAX_ARTIFACT_BYTES": "100000",
                        "GITHUB_OUTPUT": str(output_path),
                        "GITHUB_STEP_SUMMARY": str(summary_path),
                    }
                )
                self.assertEqual(0, fix_proposal_generator.command_prepare_generation(None))
                output = output_path.read_text(encoding="utf-8")
                self.assertIn("should_generate=false", output)
                self.assertIn("reason_code=REVIEW_NOT_READY", output)
                self.assertIn("blocking_findings=0", output)
        finally:
            fix_proposal_generator.find_latest_review_result_artifact = original_find
            fix_proposal_generator.stage1.github_json = original_github_json
            os.environ.clear()
            os.environ.update(old_env)

    def test_stale_comment_marks_old_proposal_invalid(self):
        _, metadata = self.validate()
        body = fix_proposal_generator.stale_comment_body(
            metadata=metadata,
            current_head_sha="d" * 40,
            workflow_run_id="999",
            repo="Vectology-cloud-team/namma-rogue-agent",
        )
        self.assertIn("STALE", body)
        self.assertIn("not valid for application", body)

    def test_artifact_writes_verified_json_only(self):
        proposal, metadata = self.validate()
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir)
            fix_proposal_generator.write_verified_artifact(
                output_dir=output,
                proposal=proposal,
                metadata=metadata,
            )
            self.assertEqual(
                {"fix-proposal.json", "proposal-metadata.json"},
                {path.name for path in output.iterdir()},
            )
            self.assertEqual(
                proposal["proposal_id"],
                json.loads((output / "fix-proposal.json").read_text())["proposal_id"],
            )

    def test_artifact_download_uses_github_rest_accept_header(self):
        original_github_json = fix_proposal_generator.stage1.github_json
        original_github_api_request = fix_proposal_generator.stage1.github_api_request
        calls = []

        def fake_github_json(method, api_path, **_kwargs):
            self.assertEqual("GET", method)
            self.assertEqual(
                "/repos/Vectology-cloud-team/namma-rogue-agent/actions/runs/123/artifacts?per_page=100",
                api_path,
            )
            return {"artifacts": [{"id": 456, "name": "fix-proposal-request-123"}]}, {}

        def fake_github_api_request(method, api_path, **kwargs):
            calls.append(kwargs)
            self.assertEqual("GET", method)
            self.assertEqual(
                "/repos/Vectology-cloud-team/namma-rogue-agent/actions/artifacts/456/zip",
                api_path,
            )
            archive_bytes = io.BytesIO()
            with zipfile.ZipFile(archive_bytes, "w") as archive:
                archive.writestr("manifest.json", "{}\n")
                archive.writestr("review.diff", "")
            return archive_bytes.getvalue(), {}

        fix_proposal_generator.stage1.github_json = fake_github_json
        fix_proposal_generator.stage1.github_api_request = fake_github_api_request
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                artifact_id = fix_proposal_generator.download_artifact_by_name(
                    repo="Vectology-cloud-team/namma-rogue-agent",
                    token="token",
                    run_id="123",
                    artifact_name="fix-proposal-request-123",
                    target_dir=Path(tmpdir),
                    expected_files={"manifest.json", "review.diff"},
                    max_bytes=50000,
                )
                self.assertEqual(456, artifact_id)
                self.assertEqual(1, len(calls))
                self.assertNotEqual("application/zip", calls[0].get("accept"))
        finally:
            fix_proposal_generator.stage1.github_json = original_github_json
            fix_proposal_generator.stage1.github_api_request = original_github_api_request

    def test_parse_codex_json_accepts_json_only(self):
        parsed = fix_proposal_generator.parse_codex_json(json.dumps(self.proposal()))
        self.assertEqual("1.0", parsed["schema_version"])

    def test_stage2b_and_stage2c_are_not_in_script(self):
        text = SCRIPT_PATH.read_text(encoding="utf-8")
        self.assertNotIn("Stage 2B", text)
        self.assertNotIn("Stage 2C", text)
        self.assertNotIn("subprocess", text)
        self.assertNotIn("os.system", text)

    def test_request_manifest_requires_exact_shape(self):
        manifest = self.request_manifest()
        manifest["extra"] = "nope"
        with self.assertRaises(fix_proposal_generator.FixProposalFailure) as raised:
            fix_proposal_generator.validate_request_manifest_shape(manifest)
        self.assertEqual("INVALID_MANIFEST", raised.exception.code.value)

    def test_policy_has_generator_model_and_effort(self):
        self.assertEqual("gpt-5.5", self.policy.model)
        self.assertEqual("medium", self.policy.reasoning_effort)
        self.assertEqual(64, len(self.policy.policy_hash))

    def test_retryable_operation_stops_after_success(self):
        calls = {"count": 0}
        delays: list[int] = []

        def operation():
            calls["count"] += 1
            if calls["count"] == 1:
                raise fix_proposal_generator.retryable(
                    fix_proposal_generator.FailureCode.NETWORK_ERROR,
                    "temporary",
                    "test",
                )
            return "ok"

        result = fix_proposal_generator.run_with_retry(
            "test",
            operation,
            sleep_func=delays.append,
        )
        self.assertEqual("ok", result.value)
        self.assertEqual(2, result.attempts)
        self.assertEqual([30], delays)

    def test_retryable_operation_never_exceeds_three_attempts(self):
        delays: list[int] = []

        def operation():
            raise fix_proposal_generator.retryable(
                fix_proposal_generator.FailureCode.NETWORK_ERROR,
                "temporary",
                "test",
            )

        with self.assertRaises(fix_proposal_generator.RetryExhausted) as raised:
            fix_proposal_generator.run_with_retry(
                "test",
                operation,
                sleep_func=delays.append,
            )
        self.assertEqual(3, raised.exception.attempts)
        self.assertEqual([30, 60], delays)

    def test_fatal_operation_is_not_retried(self):
        calls = {"count": 0}

        def operation():
            calls["count"] += 1
            raise fix_proposal_generator.fatal(
                fix_proposal_generator.FailureCode.INVALID_MANIFEST,
                "bad input",
                "test",
            )

        with self.assertRaises(fix_proposal_generator.FixProposalFailure):
            fix_proposal_generator.run_with_retry("test", operation)
        self.assertEqual(1, calls["count"])


if __name__ == "__main__":
    unittest.main()
