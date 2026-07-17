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

    def manifest(self, *, labels=None, head_sha=HEAD_SHA):
        return {
            "schema_version": "sandbox-validation-request-v1",
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
            "event_action": "labeled",
            "event_name": "pull_request",
            "event_label": "ai-fix-validate",
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
                "unit",
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

    def test_allowed_test_ids_are_normalized_without_execution(self):
        self.assertEqual(
            ("unit", "compileall"),
            sandbox_validation.normalize_test_ids(
                ["unit", "compileall", "unit"],
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
