from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
SCRIPT_PATH = SCRIPTS_DIR / "sandbox_validation.py"
SPEC = importlib.util.spec_from_file_location("sandbox_validation", SCRIPT_PATH)
sandbox_validation = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = sandbox_validation
SPEC.loader.exec_module(sandbox_validation)


BASE_SHA = "a" * 40
HEAD_SHA = "b" * 40
ORIGINAL_BLOB_SHA = "d" * 40


class SandboxValidationTests(unittest.TestCase):
    def policy(self):
        return sandbox_validation.fix.load_fix_proposal_policy(
            REPO_ROOT / ".github" / "codex" / "fix-policy.yml"
        )

    def manifest(
        self,
        *,
        labels=None,
        head_sha=HEAD_SHA,
        request_stage="SANDBOX_VALIDATION_REQUEST",
        event_action="labeled",
        event_name="pull_request",
        event_label="ai-fix-validate",
    ):
        return {
            "schema_version": "sandbox-validation-request-v1",
            "request_stage": request_stage,
            "repository": sandbox_validation.EXPECTED_REPOSITORY,
            "pull_request_number": 26,
            "base_sha": BASE_SHA,
            "head_sha": head_sha,
            "actor": "validator",
            "author_association": "MEMBER",
            "draft": False,
            "base_repository": sandbox_validation.EXPECTED_REPOSITORY,
            "head_repository": sandbox_validation.EXPECTED_REPOSITORY,
            "labels": labels if labels is not None else [
                "ai-fix-proposal",
                "ai-fix-approved",
                "ai-fix-validate",
            ],
            "event_action": event_action,
            "event_name": event_name,
            "event_label": event_label,
            "collector_workflow_name": sandbox_validation.COLLECTOR_WORKFLOW_NAME,
            "collector_workflow_run_id": 123,
            "requested_at": "2026-07-17T00:00:00Z",
        }

    def live_pull(self, *, head_sha=HEAD_SHA, state="open", head_repo=None):
        return {
            "number": 26,
            "state": state,
            "draft": False,
            "head": {
                "sha": head_sha,
                "repo": {
                    "full_name": head_repo or sandbox_validation.EXPECTED_REPOSITORY,
                },
            },
            "base": {
                "sha": BASE_SHA,
            },
            "user": {
                "type": "User",
            },
        }

    def live_issue(self, *, labels=None):
        labels = labels if labels is not None else [
            "ai-fix-proposal",
            "ai-fix-approved",
            "ai-fix-validate",
        ]
        return {
            "labels": [
                {
                    "name": label,
                }
                for label in labels
            ],
        }

    def proposal(self, *, tests_recommended=None, path="canary/example.py"):
        policy_hash = self.policy().policy_hash
        proposal = {
            "schema_version": "1.0",
            "proposal_id": "0" * 32,
            "repository": sandbox_validation.EXPECTED_REPOSITORY,
            "pull_request_number": 26,
            "base_sha": BASE_SHA,
            "head_sha": HEAD_SHA,
            "source_review_run_id": 456,
            "source_review_artifact_id": "architect-review-result-456",
            "reviewed_at": "2026-07-17T00:00:00Z",
            "generator": {
                "model": "gpt-5.5",
                "reasoning_effort": "medium",
                "policy_version": policy_hash,
            },
            "summary": "Fix the canary bug.",
            "findings_addressed": [
                {
                    "finding_id": "finding-canary",
                    "severity": "high",
                    "category": "correctness",
                }
            ],
            "changes": [
                {
                    "path": path,
                    "operation": "modify",
                    "original_blob_sha": ORIGINAL_BLOB_SHA,
                    "patch": "\n".join(
                        [
                            f"diff --git a/{path} b/{path}",
                            f"--- a/{path}",
                            f"+++ b/{path}",
                            "@@ -1 +1 @@",
                            "-return False",
                            "+return True",
                        ]
                    ),
                    "rationale": "Correct the boolean result.",
                }
            ],
            "tests_recommended": tests_recommended if tests_recommended is not None else [
                "stage2c-b1-clamp",
            ],
            "tests_rationale": [
                "Verify values below the minimum, within the range, and above the maximum.",
            ],
            "risks": [
                "Canary-only change.",
            ],
            "human_approval_required": True,
        }
        metadata = {
            "policy_hash": policy_hash,
            "proposal_input_hash": "e" * 64,
            "source_review_hash": "f" * 64,
        }
        proposal_hash = sandbox_validation.approval.proposal_hash_for_approval(
            proposal=proposal,
            metadata=metadata,
        )
        proposal["proposal_id"] = proposal_hash[:32]
        return proposal

    def metadata(self, proposal):
        proposal_hash = sandbox_validation.approval.proposal_hash_for_approval(
            proposal=proposal,
            metadata={
                "policy_hash": self.policy().policy_hash,
                "proposal_input_hash": "e" * 64,
                "source_review_hash": "f" * 64,
            },
        )
        return {
            "schema_version": "fix-proposal-metadata-v1",
            "status": "PROPOSAL_READY",
            "proposal_id": proposal_hash[:32],
            "proposal_hash": proposal_hash,
            "proposal_input_hash": "e" * 64,
            "repository": sandbox_validation.EXPECTED_REPOSITORY,
            "pull_request_number": 26,
            "base_sha": BASE_SHA,
            "head_sha": HEAD_SHA,
            "policy_hash": self.policy().policy_hash,
            "schema_id": "fix-proposal.schema.json",
            "generator_model": "gpt-5.5",
            "reasoning_effort": "medium",
            "generated_at": "2026-07-17T00:01:00Z",
            "source_review_run_id": 456,
            "source_review_artifact_id": "architect-review-result-456",
            "source_review_hash": "f" * 64,
        }

    def approval_record(self, proposal, metadata, *, approved_at="2026-07-17T00:02:00Z"):
        return sandbox_validation.approval.build_approval_record(
            manifest={
                "actor": "approver",
            },
            proposal=proposal,
            metadata=metadata,
            approved_by="approver",
            approved_by_repository_permission="admin",
            approved_by_repository_role="admin",
            approved_at=approved_at,
        )

    def proposal_bundle(self):
        proposal = self.proposal()
        metadata = self.metadata(proposal)
        return sandbox_validation.ArtifactBundle(
            data=proposal,
            metadata=metadata,
            artifact_id=100,
            artifact_name=f"fix-proposal-{metadata['proposal_id']}",
            workflow_run_id=200,
            workflow_name=sandbox_validation.fix.GENERATOR_WORKFLOW_NAME,
        )

    def approval_bundle(self, proposal_bundle):
        record = self.approval_record(proposal_bundle.data, proposal_bundle.metadata)
        return sandbox_validation.ApprovalBundle(
            record=record,
            artifact_id=101,
            artifact_name=f"approval-record-{record['approval_id']}",
            workflow_run_id=201,
            workflow_name=sandbox_validation.approval.RECORDER_WORKFLOW_NAME,
        )

    def assert_preflight_status(self, status, code, func, *args, **kwargs):
        with self.assertRaises(sandbox_validation.PreflightStatus) as caught:
            func(*args, **kwargs)
        self.assertEqual(status, caught.exception.status)
        self.assertEqual(code, caught.exception.code)

    def test_valid_live_gate_requires_three_live_labels_and_same_head(self):
        labels = sandbox_validation.validate_live_gate(
            manifest=self.manifest(),
            live_pull=self.live_pull(),
            live_issue=self.live_issue(),
            policy=self.policy(),
            validation_actor="validator",
            validation_actor_permission="maintain",
        )
        self.assertEqual(
            {"ai-fix-proposal", "ai-fix-approved", "ai-fix-validate"},
            labels,
        )

    def test_missing_live_validate_label_fails_closed(self):
        with self.assertRaises(sandbox_validation.fix.FixProposalFailure):
            sandbox_validation.validate_live_gate(
                manifest=self.manifest(),
                live_pull=self.live_pull(),
                live_issue=self.live_issue(labels=["ai-fix-proposal", "ai-fix-approved"]),
                policy=self.policy(),
                validation_actor="validator",
                validation_actor_permission="maintain",
            )

    def test_fork_pr_is_rejected_before_artifacts(self):
        manifest = self.manifest()
        manifest["head_repository"] = "attacker/fork"
        with self.assertRaises(sandbox_validation.fix.FixProposalFailure):
            sandbox_validation.validate_live_gate(
                manifest=manifest,
                live_pull=self.live_pull(head_repo="attacker/fork"),
                live_issue=self.live_issue(),
                policy=self.policy(),
                validation_actor="validator",
                validation_actor_permission="maintain",
            )

    def test_stale_collector_head_is_stale_not_success(self):
        self.assert_preflight_status(
            "STALE",
            "REQUEST_HEAD_STALE",
            sandbox_validation.validate_live_gate,
            manifest=self.manifest(),
            live_pull=self.live_pull(head_sha="c" * 40),
            live_issue=self.live_issue(),
            policy=self.policy(),
            validation_actor="validator",
            validation_actor_permission="maintain",
        )

    def test_validation_actor_write_permission_is_rejected(self):
        with self.assertRaises(sandbox_validation.fix.FixProposalFailure):
            sandbox_validation.validate_live_gate(
                manifest=self.manifest(),
                live_pull=self.live_pull(),
                live_issue=self.live_issue(),
                policy=self.policy(),
                validation_actor="validator",
                validation_actor_permission="write",
            )

    def test_patch_metadata_accepts_modify_only_expected_file(self):
        proposal = self.proposal()
        result = sandbox_validation.validate_patch_metadata(
            proposal=proposal,
            policy=self.policy().proposal_policy,
        )
        self.assertEqual("PASS", result["status"])
        self.assertEqual(["canary/example.py"], result["expected_files"])

    def test_patch_metadata_accepts_stage2a_unified_patch_without_git_header(self):
        proposal = self.proposal()
        patch_lines = proposal["changes"][0]["patch"].splitlines()
        proposal["changes"][0]["patch"] = "\n".join(patch_lines[1:])
        result = sandbox_validation.validate_patch_metadata(
            proposal=proposal,
            policy=self.policy().proposal_policy,
        )
        self.assertEqual("PASS", result["status"])
        self.assertEqual(["canary/example.py"], result["expected_files"])

    def test_patch_metadata_rejects_path_traversal(self):
        proposal = self.proposal(path="../escape.py")
        self.assert_preflight_status(
            "PATCH_REJECTED",
            "PATH_TRAVERSAL",
            sandbox_validation.validate_patch_metadata,
            proposal=proposal,
            policy=self.policy().proposal_policy,
        )

    def test_patch_metadata_rejects_protected_workflow_path(self):
        proposal = self.proposal(path=".github/workflows/evil.yml")
        self.assert_preflight_status(
            "PATCH_REJECTED",
            "PROTECTED_PATH",
            sandbox_validation.validate_patch_metadata,
            proposal=proposal,
            policy=self.policy().proposal_policy,
        )

    def test_patch_metadata_rejects_binary_rename_delete_create_and_mode_change(self):
        forbidden_markers = {
            "binary": "GIT binary patch",
            "rename": "rename from old.py",
            "delete": "deleted file mode 100644",
            "create": "new file mode 100644",
            "mode": "old mode 100644",
        }
        for name, marker in forbidden_markers.items():
            with self.subTest(name=name):
                proposal = self.proposal()
                proposal["changes"][0]["patch"] += f"\n{marker}\n"
                self.assert_preflight_status(
                    "PATCH_REJECTED",
                    "UNSUPPORTED_PATCH_OPERATION",
                    sandbox_validation.validate_patch_metadata,
                    proposal=proposal,
                    policy=self.policy().proposal_policy,
                )

    def test_patch_metadata_rejects_unexpected_patch_path(self):
        proposal = self.proposal()
        proposal["changes"][0]["patch"] = proposal["changes"][0]["patch"].replace(
            "b/canary/example.py",
            "b/canary/other.py",
            1,
        )
        self.assert_preflight_status(
            "PATCH_REJECTED",
            "PATCH_PATH_MISMATCH",
            sandbox_validation.validate_patch_metadata,
            proposal=proposal,
            policy=self.policy().proposal_policy,
        )

    def test_patch_metadata_rejects_extra_protected_diff_section(self):
        proposal = self.proposal()
        proposal["changes"][0]["patch"] += "\n".join(
            [
                "",
                "diff --git a/.github/workflows/evil.yml b/.github/workflows/evil.yml",
                "--- a/.github/workflows/evil.yml",
                "+++ b/.github/workflows/evil.yml",
                "@@ -1 +1 @@",
                "-name: safe",
                "+name: unsafe",
            ]
        )
        self.assert_preflight_status(
            "PATCH_REJECTED",
            "PROTECTED_PATH",
            sandbox_validation.validate_patch_metadata,
            proposal=proposal,
            policy=self.policy().proposal_policy,
        )

    def test_patch_metadata_rejects_extra_undeclared_diff_section(self):
        proposal = self.proposal()
        proposal["changes"][0]["patch"] += "\n".join(
            [
                "",
                "diff --git a/canary/other.py b/canary/other.py",
                "--- a/canary/other.py",
                "+++ b/canary/other.py",
                "@@ -1 +1 @@",
                "-return False",
                "+return True",
            ]
        )
        self.assert_preflight_status(
            "PATCH_REJECTED",
            "PATCH_PATH_MISMATCH",
            sandbox_validation.validate_patch_metadata,
            proposal=proposal,
            policy=self.policy().proposal_policy,
        )

    def test_target_blob_sha_matches_current_tree(self):
        checks = sandbox_validation.validate_target_blob_shas(
            proposal=self.proposal(),
            tree_entries={
                "canary/example.py": {
                    "type": "blob",
                    "mode": "100644",
                    "sha": ORIGINAL_BLOB_SHA,
                    "size": 42,
                }
            },
            policy=self.policy().proposal_policy,
        )
        self.assertEqual("PASS", checks[0]["status"])

    def test_blob_sha_mismatch_is_stale(self):
        self.assert_preflight_status(
            "STALE",
            "BLOB_SHA_MISMATCH",
            sandbox_validation.validate_target_blob_shas,
            proposal=self.proposal(),
            tree_entries={
                "canary/example.py": {
                    "type": "blob",
                    "mode": "100644",
                    "sha": "9" * 40,
                    "size": 42,
                }
            },
            policy=self.policy().proposal_policy,
        )

    def test_symlink_and_submodule_are_rejected(self):
        for file_type, mode in (("blob", "120000"), ("commit", "160000")):
            with self.subTest(file_type=file_type, mode=mode):
                self.assert_preflight_status(
                    "PATCH_REJECTED",
                    "UNSUPPORTED_FILE_TYPE" if file_type != "blob" else "UNSUPPORTED_FILE_MODE",
                    sandbox_validation.validate_target_blob_shas,
                    proposal=self.proposal(),
                    tree_entries={
                        "canary/example.py": {
                            "type": file_type,
                            "mode": mode,
                            "sha": ORIGINAL_BLOB_SHA,
                            "size": 42,
                        }
                    },
                    policy=self.policy().proposal_policy,
                )

    def test_unrelated_old_approval_record_is_not_a_preflight_candidate(self):
        proposal = self.proposal()
        metadata = self.metadata(proposal)
        old_record = {
            "schema_version": "approval-record-v2",
            "repository": sandbox_validation.EXPECTED_REPOSITORY,
            "pull_request_number": 23,
            "proposal_id": "old-proposal",
            "proposal_hash": "a" * 64,
            "head_sha": "c" * 40,
        }
        self.assertFalse(
            sandbox_validation.approval_record_targets_preflight_request(
                record=old_record,
                manifest=self.manifest(),
                proposal=proposal,
                metadata=metadata,
            )
        )

    def test_matching_malformed_approval_record_is_a_preflight_candidate(self):
        proposal = self.proposal()
        metadata = self.metadata(proposal)
        malformed_record = {
            "schema_version": "approval-record-v2",
            "repository": sandbox_validation.EXPECTED_REPOSITORY,
            "pull_request_number": 26,
            "proposal_id": proposal["proposal_id"],
            "proposal_hash": metadata["proposal_hash"],
            "head_sha": HEAD_SHA,
        }
        self.assertTrue(
            sandbox_validation.approval_record_targets_preflight_request(
                record=malformed_record,
                manifest=self.manifest(),
                proposal=proposal,
                metadata=metadata,
            )
        )

    def test_allowed_test_ids_are_normalized_without_execution(self):
        self.assertEqual(
            ("unit", "compileall"),
            sandbox_validation.normalize_test_ids(
                ["unit", "compileall", "unit"],
                allowed_test_ids=("unit", "compileall"),
            ),
        )

    def test_stage2a_natural_language_test_recommendations_are_not_promoted(self):
        self.assertEqual(
            ("unit",),
            sandbox_validation.normalize_test_ids(
                [
                    "Run the targeted Stage 2C clamp tests.",
                    "unit",
                    "Run the repository unit test suite relevant to canary utilities.",
                ],
                allowed_test_ids=("unit", "compileall"),
            ),
        )

    def test_all_stage2a_natural_language_test_recommendations_plan_no_tests(self):
        self.assertEqual(
            (),
            sandbox_validation.normalize_test_ids(
                [
                    "Run the targeted Stage 2C clamp tests.",
                    "Run the repository unit test suite relevant to canary utilities.",
                ],
                allowed_test_ids=("unit", "compileall"),
            ),
        )

    def test_raw_shell_tests_are_rejected(self):
        for test_id in (
            "python -m unittest",
            "unit | curl example.com",
            "sudo unit",
            "curl",
            "unknown",
        ):
            with self.subTest(test_id=test_id):
                self.assert_preflight_status(
                    "PATCH_REJECTED",
                    "UNKNOWN_TEST_ID" if test_id == "unknown" else "UNTRUSTED_TEST_COMMAND",
                    sandbox_validation.normalize_test_ids,
                    [test_id],
                    allowed_test_ids=("unit", "compileall"),
                )

    def test_sandbox_comment_uses_issue_comment_api_create_body(self):
        original_iter = sandbox_validation.stage1.iter_issue_comments
        original_github_json = sandbox_validation.stage1.github_json
        calls = []

        def fake_iter_issue_comments(repo, issue_number, token):
            return iter(())

        def fake_github_json(method, path, *, token, body=None):
            calls.append((method, path, token, body))
            return {"id": 12345}, {}

        try:
            sandbox_validation.stage1.iter_issue_comments = fake_iter_issue_comments
            sandbox_validation.stage1.github_json = fake_github_json
            comment_id, action = sandbox_validation.post_or_update_sandbox_comment(
                repo=sandbox_validation.EXPECTED_REPOSITORY,
                issue_number="27",
                token="token",
                body="body",
            )
        finally:
            sandbox_validation.stage1.iter_issue_comments = original_iter
            sandbox_validation.stage1.github_json = original_github_json

        self.assertEqual("12345", comment_id)
        self.assertEqual("create", action)
        self.assertEqual(
            [
                (
                    "POST",
                    f"/repos/{sandbox_validation.EXPECTED_REPOSITORY}/issues/27/comments",
                    "token",
                    {"body": "body"},
                )
            ],
            calls,
        )

    def test_sandbox_comment_uses_issue_comment_api_update_body(self):
        original_iter = sandbox_validation.stage1.iter_issue_comments
        original_github_json = sandbox_validation.stage1.github_json
        calls = []

        def fake_iter_issue_comments(repo, issue_number, token):
            return iter(
                [
                    {
                        "id": 67890,
                        "body": sandbox_validation.SANDBOX_MARKER,
                    }
                ]
            )

        def fake_github_json(method, path, *, token, body=None):
            calls.append((method, path, token, body))
            return None, {}

        try:
            sandbox_validation.stage1.iter_issue_comments = fake_iter_issue_comments
            sandbox_validation.stage1.github_json = fake_github_json
            comment_id, action = sandbox_validation.post_or_update_sandbox_comment(
                repo=sandbox_validation.EXPECTED_REPOSITORY,
                issue_number="27",
                token="token",
                body="body",
            )
        finally:
            sandbox_validation.stage1.iter_issue_comments = original_iter
            sandbox_validation.stage1.github_json = original_github_json

        self.assertEqual("67890", comment_id)
        self.assertEqual("update", action)
        self.assertEqual(
            [
                (
                    "PATCH",
                    f"/repos/{sandbox_validation.EXPECTED_REPOSITORY}/issues/comments/67890",
                    "token",
                    {"body": "body"},
                )
            ],
            calls,
        )

    def test_precheck_result_is_deterministic_and_records_no_execution(self):
        proposal_bundle = self.proposal_bundle()
        approval_bundle = self.approval_bundle(proposal_bundle)
        patch_metadata = sandbox_validation.validate_patch_metadata(
            proposal=proposal_bundle.data,
            policy=self.policy().proposal_policy,
        )
        target_blob_checks = sandbox_validation.validate_target_blob_shas(
            proposal=proposal_bundle.data,
            tree_entries={
                "canary/example.py": {
                    "type": "blob",
                    "mode": "100644",
                    "sha": ORIGINAL_BLOB_SHA,
                    "size": 42,
                }
            },
            policy=self.policy().proposal_policy,
        )
        kwargs = {
            "manifest": self.manifest(),
            "proposal_bundle": proposal_bundle,
            "approval_bundle": approval_bundle,
            "validation_actor": "validator",
            "validation_actor_permission": "maintain",
            "validation_actor_role": "maintain",
            "live_labels": {"ai-fix-proposal", "ai-fix-approved", "ai-fix-validate"},
            "target_blob_checks": target_blob_checks,
            "patch_metadata_check": patch_metadata,
            "test_ids": ("unit",),
            "completed_at": "2026-07-17T00:03:00Z",
        }
        first = sandbox_validation.build_precheck_result(**kwargs)
        second = sandbox_validation.build_precheck_result(**kwargs)
        self.assertEqual(first["validation_id"], second["validation_id"])
        self.assertEqual("PRECHECK_PASSED", first["status"])
        self.assertFalse(first["sandbox_checkout_performed"])
        self.assertFalse(first["patch_applied"])
        self.assertFalse(first["test_execution_performed"])
        self.assertFalse(first["persistent_repository_modified"])
        self.assertFalse(first["commit_created"])
        self.assertFalse(first["push_performed"])
        self.assertFalse(first["merge_performed"])
        sandbox_validation.validate_result_against_schema(
            first,
            REPO_ROOT
            / ".github"
            / "codex"
            / "schemas"
            / "sandbox-validation-result.schema.json",
        )

    def test_result_schema_validation_rejects_malformed_result_before_upload(self):
        proposal_bundle = self.proposal_bundle()
        approval_bundle = self.approval_bundle(proposal_bundle)
        patch_metadata = sandbox_validation.validate_patch_metadata(
            proposal=proposal_bundle.data,
            policy=self.policy().proposal_policy,
        )
        target_blob_checks = sandbox_validation.validate_target_blob_shas(
            proposal=proposal_bundle.data,
            tree_entries={
                "canary/example.py": {
                    "type": "blob",
                    "mode": "100644",
                    "sha": ORIGINAL_BLOB_SHA,
                    "size": 42,
                }
            },
            policy=self.policy().proposal_policy,
        )
        result = sandbox_validation.build_precheck_result(
            manifest=self.manifest(),
            proposal_bundle=proposal_bundle,
            approval_bundle=approval_bundle,
            validation_actor="validator",
            validation_actor_permission="maintain",
            validation_actor_role="maintain",
            live_labels={"ai-fix-proposal", "ai-fix-approved", "ai-fix-validate"},
            target_blob_checks=target_blob_checks,
            patch_metadata_check=patch_metadata,
            test_ids=("unit",),
            completed_at="2026-07-17T00:03:00Z",
        )
        del result["validation_id"]
        with self.assertRaises(sandbox_validation.fix.FixProposalFailure) as caught:
            sandbox_validation.validate_result_against_schema(
                result,
                REPO_ROOT
                / ".github"
                / "codex"
                / "schemas"
                / "sandbox-validation-result.schema.json",
            )
        self.assertEqual(
            sandbox_validation.fix.FailureCode.INVALID_PROPOSAL,
            caught.exception.code,
        )

    def test_result_schema_validation_rejects_precheck_patch_application(self):
        proposal_bundle = self.proposal_bundle()
        approval_bundle = self.approval_bundle(proposal_bundle)
        patch_metadata = sandbox_validation.validate_patch_metadata(
            proposal=proposal_bundle.data,
            policy=self.policy().proposal_policy,
        )
        target_blob_checks = sandbox_validation.validate_target_blob_shas(
            proposal=proposal_bundle.data,
            tree_entries={
                "canary/example.py": {
                    "type": "blob",
                    "mode": "100644",
                    "sha": ORIGINAL_BLOB_SHA,
                    "size": 42,
                }
            },
            policy=self.policy().proposal_policy,
        )
        result = sandbox_validation.build_precheck_result(
            manifest=self.manifest(),
            proposal_bundle=proposal_bundle,
            approval_bundle=approval_bundle,
            validation_actor="validator",
            validation_actor_permission="maintain",
            validation_actor_role="maintain",
            live_labels={"ai-fix-proposal", "ai-fix-approved", "ai-fix-validate"},
            target_blob_checks=target_blob_checks,
            patch_metadata_check=patch_metadata,
            test_ids=("unit",),
            completed_at="2026-07-17T00:03:00Z",
        )
        result["patch_applied"] = True
        with self.assertRaises(sandbox_validation.fix.FixProposalFailure):
            sandbox_validation.validate_result_against_schema(
                result,
                REPO_ROOT
                / ".github"
                / "codex"
                / "schemas"
                / "sandbox-validation-result.schema.json",
            )

    def test_sandbox_script_has_no_repository_mutation_runtime(self):
        script = SCRIPT_PATH.read_text(encoding="utf-8").lower()
        for token in (
            "subprocess",
            "os.system",
            "git apply",
            "git push",
            "git merge",
            "createcommitonbranch",
            "createpullrequest",
        ):
            self.assertNotIn(token, script)


if __name__ == "__main__":
    unittest.main()
