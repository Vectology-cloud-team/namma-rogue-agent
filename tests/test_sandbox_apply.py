from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
SCRIPT_PATH = SCRIPTS_DIR / "sandbox_apply.py"
SPEC = importlib.util.spec_from_file_location("sandbox_apply", SCRIPT_PATH)
sandbox_apply = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = sandbox_apply
SPEC.loader.exec_module(sandbox_apply)


BASE_SHA = "a" * 40
HEAD_SHA = "b" * 40
PROPOSAL_HASH = "c" * 64
APPROVAL_HASH = "d" * 64
PREFLIGHT_HASH = "e" * 64
PATCH_HASH = "f" * 64


class SandboxApplyTests(unittest.TestCase):
    def policy(self):
        return sandbox_apply.fix.load_fix_proposal_policy(
            REPO_ROOT / ".github" / "codex" / "fix-policy.yml"
        )

    def manifest(
        self,
        *,
        labels=None,
        head_sha=HEAD_SHA,
        request_stage="SANDBOX_APPLY_REQUEST",
        event_action="labeled",
        event_label="ai-fix-apply-sandbox",
        head_repository=None,
    ):
        return {
            "schema_version": "sandbox-apply-request-v1",
            "request_stage": request_stage,
            "repository": sandbox_apply.EXPECTED_REPOSITORY,
            "pull_request_number": 31,
            "base_sha": BASE_SHA,
            "head_sha": head_sha,
            "actor": "applier",
            "author_association": "MEMBER",
            "draft": False,
            "base_repository": sandbox_apply.EXPECTED_REPOSITORY,
            "head_repository": head_repository or sandbox_apply.EXPECTED_REPOSITORY,
            "labels": labels
            if labels is not None
            else [
                "ai-fix-proposal",
                "ai-fix-approved",
                "ai-fix-validate",
                "ai-fix-apply-sandbox",
            ],
            "event_action": event_action,
            "event_name": "pull_request",
            "event_label": event_label,
            "collector_workflow_name": sandbox_apply.COLLECTOR_WORKFLOW_NAME,
            "collector_workflow_run_id": 123,
            "requested_at": "2026-07-18T00:00:00Z",
        }

    def live_pull(self, *, head_sha=HEAD_SHA, state="open", head_repo=None):
        return {
            "number": 31,
            "state": state,
            "draft": False,
            "head": {
                "sha": head_sha,
                "repo": {
                    "full_name": head_repo or sandbox_apply.EXPECTED_REPOSITORY,
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
        return {
            "labels": [
                {"name": label}
                for label in (
                    labels
                    if labels is not None
                    else [
                        "ai-fix-proposal",
                        "ai-fix-approved",
                        "ai-fix-validate",
                        "ai-fix-apply-sandbox",
                    ]
                )
            ],
        }

    def preflight_result(self, *, status="PRECHECK_PASSED", head_sha=HEAD_SHA):
        return {
            "validation_id": "1" * 32,
            "phase": "PREFLIGHT",
            "status": status,
            "repository": sandbox_apply.EXPECTED_REPOSITORY,
            "pull_request_number": 31,
            "head_sha": head_sha,
            "proposal_id": "2" * 32,
            "proposal_hash": PROPOSAL_HASH,
            "approval_id": "3" * 32,
            "approval_record_hash": APPROVAL_HASH,
            "policy_hash": self.policy().policy_hash,
            "persistent_repository_modified": False,
            "sandbox_checkout_performed": False,
            "patch_applied": False,
            "test_execution_performed": False,
            "commit_created": False,
            "push_performed": False,
            "merge_performed": False,
            "validation_request_actor": "validator",
            "tests_requested": [
                {
                    "test_id": "unit",
                    "requested": True,
                    "executed": False,
                    "status": "SKIPPED",
                }
            ],
        }

    def proposal_bundle(self):
        return sandbox_apply.preflight.ArtifactBundle(
            data={
                "head_sha": HEAD_SHA,
                "schema_version": "1.0",
                "proposal_id": "2" * 32,
                "changes": [
                    {
                        "path": "canary/example.py",
                        "operation": "modify",
                        "original_blob_sha": "9" * 40,
                        "patch": "diff --git a/canary/example.py b/canary/example.py\n"
                        "--- a/canary/example.py\n"
                        "+++ b/canary/example.py\n"
                        "@@ -1 +1 @@\n"
                        "-return False\n"
                        "+return True\n",
                    }
                ],
            },
            metadata={
                "proposal_id": "2" * 32,
                "proposal_hash": PROPOSAL_HASH,
                "policy_hash": self.policy().policy_hash,
                "head_sha": HEAD_SHA,
            },
            artifact_id=100,
            artifact_name="fix-proposal-test",
            workflow_run_id=200,
            workflow_name=sandbox_apply.fix.GENERATOR_WORKFLOW_NAME,
        )

    def approval_bundle(self):
        return sandbox_apply.preflight.ApprovalBundle(
            record={
                "schema_version": "approval-record-v3",
                "approval_id": "3" * 32,
                "proposal_id": "2" * 32,
                "proposal_hash": PROPOSAL_HASH,
                "approval_record_hash": APPROVAL_HASH,
                "repository": sandbox_apply.EXPECTED_REPOSITORY,
                "pull_request_number": 31,
                "head_sha": HEAD_SHA,
                "approved_by": "approver",
                "approved_by_repository_permission": "admin",
                "approved_by_repository_role": "admin",
                "policy_hash": self.policy().policy_hash,
            },
            artifact_id=101,
            artifact_name="approval-record-test",
            workflow_run_id=201,
            workflow_name=sandbox_apply.approval.RECORDER_WORKFLOW_NAME,
        )

    def assert_apply_status(self, status, code, func, *args, **kwargs):
        with self.assertRaises(sandbox_apply.ApplyStatus) as caught:
            func(*args, **kwargs)
        self.assertEqual(status, caught.exception.status)
        self.assertEqual(code, caught.exception.code)

    def test_valid_apply_manifest_and_live_gate(self):
        sandbox_apply.validate_request_manifest_shape(self.manifest())
        labels = sandbox_apply.validate_live_apply_gate(
            manifest=self.manifest(),
            live_pull=self.live_pull(),
            live_issue=self.live_issue(),
            policy=self.policy(),
            apply_actor="applier",
            apply_actor_permission="maintain",
        )
        self.assertEqual(
            {
                "ai-fix-proposal",
                "ai-fix-approved",
                "ai-fix-validate",
                "ai-fix-apply-sandbox",
            },
            labels,
        )

    def test_missing_apply_label_is_rejected(self):
        with self.assertRaises(sandbox_apply.fix.FixProposalFailure):
            sandbox_apply.validate_live_apply_gate(
                manifest=self.manifest(labels=["ai-fix-proposal"]),
                live_pull=self.live_pull(),
                live_issue=self.live_issue(),
                policy=self.policy(),
                apply_actor="applier",
                apply_actor_permission="maintain",
            )

    def test_missing_prior_live_label_is_rejected(self):
        with self.assertRaises(sandbox_apply.fix.FixProposalFailure):
            sandbox_apply.validate_live_apply_gate(
                manifest=self.manifest(),
                live_pull=self.live_pull(),
                live_issue=self.live_issue(
                    labels=[
                        "ai-fix-proposal",
                        "ai-fix-validate",
                        "ai-fix-apply-sandbox",
                    ]
                ),
                policy=self.policy(),
                apply_actor="applier",
                apply_actor_permission="maintain",
            )

    def test_stale_head_is_rejected(self):
        self.assert_apply_status(
            "STALE",
            "REQUEST_HEAD_STALE",
            sandbox_apply.validate_live_apply_gate,
            manifest=self.manifest(),
            live_pull=self.live_pull(head_sha="4" * 40),
            live_issue=self.live_issue(),
            policy=self.policy(),
            apply_actor="applier",
            apply_actor_permission="maintain",
        )

    def test_fork_pr_is_rejected(self):
        with self.assertRaises(sandbox_apply.fix.FixProposalFailure):
            sandbox_apply.validate_live_apply_gate(
                manifest=self.manifest(head_repository="someone/fork"),
                live_pull=self.live_pull(head_repo="someone/fork"),
                live_issue=self.live_issue(),
                policy=self.policy(),
                apply_actor="applier",
                apply_actor_permission="maintain",
            )

    def test_apply_actor_write_permission_is_rejected(self):
        with self.assertRaises(sandbox_apply.fix.FixProposalFailure):
            sandbox_apply.validate_live_apply_gate(
                manifest=self.manifest(),
                live_pull=self.live_pull(),
                live_issue=self.live_issue(),
                policy=self.policy(),
                apply_actor="applier",
                apply_actor_permission="write",
            )

    def test_preflight_result_must_be_precheck_passed(self):
        with self.assertRaises(sandbox_apply.fix.FixProposalFailure):
            sandbox_apply.validate_preflight_result(
                result=self.preflight_result(status="STALE"),
                manifest=self.manifest(),
                proposal_bundle=self.proposal_bundle(),
                approval_bundle=self.approval_bundle(),
                policy_hash=self.policy().policy_hash,
            )

    def test_preflight_hash_mismatch_fails_closed(self):
        with self.assertRaises(sandbox_apply.fix.FixProposalFailure):
            sandbox_apply.validate_preflight_result(
                result=self.preflight_result(head_sha="4" * 40),
                manifest=self.manifest(),
                proposal_bundle=self.proposal_bundle(),
                approval_bundle=self.approval_bundle(),
                policy_hash=self.policy().policy_hash,
            )

    def test_apply_id_is_deterministic(self):
        kwargs = {
            "repository": sandbox_apply.EXPECTED_REPOSITORY,
            "pull_request_number": 31,
            "head_sha": HEAD_SHA,
            "proposal_id": "2" * 32,
            "proposal_hash": PROPOSAL_HASH,
            "approval_id": "3" * 32,
            "approval_record_hash": APPROVAL_HASH,
            "preflight_validation_id": "1" * 32,
            "preflight_result_hash": PREFLIGHT_HASH,
            "apply_request_actor": "applier",
            "policy_hash": self.policy().policy_hash,
            "test_plan_hash": "8" * 64,
            "patch_file_hash": PATCH_HASH,
        }
        self.assertEqual(
            sandbox_apply.apply_id_for(**kwargs),
            sandbox_apply.apply_id_for(**kwargs),
        )

    def test_git_apply_argv_is_fixed_and_safe(self):
        self.assertEqual(
            (
                "git",
                "apply",
                "--check",
                "--verbose",
                "--recount",
                "--whitespace=error-all",
            ),
            sandbox_apply.GIT_APPLY_CHECK_ARGV,
        )
        self.assertNotIn("--3way", sandbox_apply.GIT_APPLY_ARGV)
        self.assertNotIn("--unsafe-paths", sandbox_apply.GIT_APPLY_CHECK_ARGV)

    def test_no_tests_are_marked_executed_in_base_result(self):
        context = {
            "manifest": self.manifest(),
            "proposal": self.proposal_bundle().data,
            "proposal_metadata": self.proposal_bundle().metadata,
            "approval_record": self.approval_bundle().record,
            "preflight_result": {
                **self.preflight_result(),
                "protected_path_check": {"status": "PASS", "message": "ok"},
                "blob_sha_check": {"status": "PASS", "message": "ok"},
                "target_blob_checks": [],
                "patch_metadata_check": {"status": "PASS", "message": "ok"},
            },
            "preflight_result_hash": PREFLIGHT_HASH,
            "proposal_artifact": {},
            "approval_artifact": {},
            "preflight_artifact": {},
            "apply_id": "5" * 32,
            "apply_request_actor": "applier",
            "apply_request_actor_repository_permission": "maintain",
            "apply_request_actor_repository_role": "maintain",
            "validation_request_actor": "validator",
            "validation_request_actor_repository_permission": "admin",
            "validation_request_actor_repository_role": "admin",
            "approved_by_repository_permission": "admin",
            "approved_by_repository_role": "admin",
            "live_labels": [],
            "expected_files": ["canary/example.py"],
            "patch_file_hash": PATCH_HASH,
            "planned_test_ids": ["unit"],
            "test_plan_hash": "8" * 64,
            "started_at": "2026-07-18T00:00:00Z",
        }
        result = sandbox_apply.base_apply_result(
            context=context,
            status="PATCH_REJECTED",
            failure_class="PATCH_REJECTED",
            failure_code="GIT_COMMAND_FAILED",
        )
        self.assertFalse(result["test_execution_performed"])
        self.assertEqual([], result["tests_executed"])
        self.assertEqual("SKIPPED", result["tests_requested"][0]["status"])

    def test_fixed_git_apply_changes_expected_file_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.PIPE)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
            target = repo / "canary" / "example.py"
            target.parent.mkdir()
            target.write_text("return False\n", encoding="utf-8")
            subprocess.run(["git", "add", "canary/example.py"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-m", "base"], cwd=repo, check=True, stdout=subprocess.PIPE)
            subprocess.run(["git", "checkout", "--detach", "HEAD"], cwd=repo, check=True, stdout=subprocess.PIPE)
            head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
            context = {
                "manifest": self.manifest(head_sha=head),
                "expected_files": ["canary/example.py"],
                "patch_text": "diff --git a/canary/example.py b/canary/example.py\n"
                "--- a/canary/example.py\n"
                "+++ b/canary/example.py\n"
                "@@ -1 +1 @@\n"
                "-return False\n"
                "+return True\n",
                "patch_file_hash": "",
            }
            context["patch_file_hash"] = sandbox_apply.sha256_hex_bytes(
                context["patch_text"].encode("utf-8")
            )
            checkout = sandbox_apply.verify_checkout(repo, head)
            self.assertTrue(checkout["detached_head"])
            patch_path = root / "namma-fix.patch"
            sandbox_apply.materialize_patch(context, patch_path)
            sandbox_apply.run_git(repo, (*sandbox_apply.GIT_APPLY_CHECK_ARGV, str(patch_path)))
            sandbox_apply.run_git(repo, (*sandbox_apply.GIT_APPLY_ARGV, str(patch_path)))
            changed, binding, hashes = sandbox_apply.verify_changed_files(
                worktree=repo,
                context=context,
            )
            self.assertEqual(["canary/example.py"], changed)
            self.assertEqual("PASS", binding["status"])
            self.assertEqual(1, len(hashes))

    def test_unexpected_changed_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.PIPE)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
            (repo / "a.txt").write_text("a\n", encoding="utf-8")
            (repo / "b.txt").write_text("b\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-m", "base"], cwd=repo, check=True, stdout=subprocess.PIPE)
            subprocess.run(["git", "checkout", "--detach", "HEAD"], cwd=repo, check=True, stdout=subprocess.PIPE)
            (repo / "b.txt").write_text("changed\n", encoding="utf-8")
            self.assert_apply_status(
                "PATCH_REJECTED",
                "UNEXPECTED_CHANGED_FILE",
                sandbox_apply.verify_changed_files,
                worktree=repo,
                context={
                    "expected_files": ["a.txt"],
                    "patch_text": "diff --git a/a.txt b/a.txt\n--- a/a.txt\n+++ b/a.txt\n@@ -1 +1 @@\n-a\n+a2\n",
                },
            )


if __name__ == "__main__":
    unittest.main()
