from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
SCRIPT_PATH = SCRIPTS_DIR / "sandbox_test.py"
SPEC = importlib.util.spec_from_file_location("sandbox_test", SCRIPT_PATH)
sandbox_test = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = sandbox_test
SPEC.loader.exec_module(sandbox_test)


BASE_SHA = "a" * 40
HEAD_SHA = "b" * 40
PROPOSAL_HASH = "c" * 64
APPROVAL_HASH = "d" * 64
PREFLIGHT_HASH = "e" * 64
APPLY_HASH = "f" * 64
POLICY_HASH = "1" * 64
TEST_POLICY_HASH = "2" * 64
PATCH_HASH = "3" * 64
RESULTING_DIFF_HASH = "4" * 64


def python3_works() -> bool:
    if not shutil.which("python3"):
        return False
    completed = subprocess.run(
        ["python3", "-c", "import sys"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return completed.returncode == 0


class SandboxTestTests(unittest.TestCase):
    def policy(self):
        return sandbox_test.fix.load_fix_proposal_policy(
            REPO_ROOT / ".github" / "codex" / "fix-policy.yml"
        )

    def sandbox_test_policy(self):
        return sandbox_test.load_sandbox_test_policy(
            REPO_ROOT / ".github" / "codex" / "sandbox-test-policy.yml"
        )

    def sandbox_test_schema_path(self):
        return (
            REPO_ROOT
            / ".github"
            / "codex"
            / "schemas"
            / "sandbox-test-result.schema.json"
        )

    def sandbox_apply_schema_path(self):
        return (
            REPO_ROOT
            / ".github"
            / "codex"
            / "schemas"
            / "sandbox-validation-result.schema.json"
        )

    def manifest(
        self,
        *,
        labels=None,
        head_sha=HEAD_SHA,
        request_stage="SANDBOX_TEST_REQUEST",
        event_action="labeled",
        event_label="ai-fix-test-sandbox",
        head_repository=None,
    ):
        return {
            "schema_version": "sandbox-test-request-v1",
            "request_stage": request_stage,
            "repository": sandbox_test.EXPECTED_REPOSITORY,
            "pull_request_number": 32,
            "base_sha": BASE_SHA,
            "head_sha": head_sha,
            "actor": "tester",
            "author_association": "MEMBER",
            "draft": False,
            "base_repository": sandbox_test.EXPECTED_REPOSITORY,
            "head_repository": head_repository or sandbox_test.EXPECTED_REPOSITORY,
            "labels": labels
            if labels is not None
            else [
                "ai-fix-proposal",
                "ai-fix-approved",
                "ai-fix-validate",
                "ai-fix-apply-sandbox",
                "ai-fix-test-sandbox",
            ],
            "event_action": event_action,
            "event_name": "pull_request",
            "event_label": event_label,
            "collector_workflow_name": sandbox_test.COLLECTOR_WORKFLOW_NAME,
            "collector_workflow_run_id": 123,
            "requested_at": "2026-07-18T00:00:00Z",
        }

    def live_pull(self, *, head_sha=HEAD_SHA, state="open", head_repo=None):
        return {
            "number": 32,
            "state": state,
            "draft": False,
            "head": {
                "sha": head_sha,
                "repo": {"full_name": head_repo or sandbox_test.EXPECTED_REPOSITORY},
            },
            "base": {
                "sha": BASE_SHA,
                "repo": {"full_name": sandbox_test.EXPECTED_REPOSITORY},
            },
            "user": {"type": "User"},
        }

    def live_issue(self, labels=None):
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
                        "ai-fix-test-sandbox",
                    ]
                )
            ]
        }

    def proposal_bundle(self):
        data = {
            "head_sha": HEAD_SHA,
            "schema_version": "1.0",
            "tests_recommended": ["unit", "compileall"],
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
        }
        return sandbox_test.preflight.ArtifactBundle(
            data=data,
            metadata={
                "proposal_id": "a" * 32,
                "proposal_hash": PROPOSAL_HASH,
                "policy_hash": POLICY_HASH,
                "head_sha": HEAD_SHA,
            },
            artifact_id=100,
            artifact_name="fix-proposal-test",
            workflow_run_id=200,
            workflow_name=sandbox_test.fix.GENERATOR_WORKFLOW_NAME,
        )

    def approval_bundle(self):
        return sandbox_test.preflight.ApprovalBundle(
            record={
                "schema_version": "approval-record-v3",
                "approval_id": "b" * 32,
                "proposal_id": "a" * 32,
                "proposal_hash": PROPOSAL_HASH,
                "approval_record_hash": APPROVAL_HASH,
                "repository": sandbox_test.EXPECTED_REPOSITORY,
                "pull_request_number": 32,
                "base_sha": BASE_SHA,
                "head_sha": HEAD_SHA,
                "approved_by": "approver",
                "approved_by_repository_permission": "admin",
                "approved_by_repository_role": "admin",
                "policy_hash": POLICY_HASH,
            },
            artifact_id=101,
            artifact_name="approval-record-test",
            workflow_run_id=201,
            workflow_name=sandbox_test.approval.RECORDER_WORKFLOW_NAME,
        )

    def preflight_bundle(self):
        return sandbox_test.apply.PreflightBundle(
            result={
                "validation_id": "c" * 32,
                "phase": "PREFLIGHT",
                "status": "PRECHECK_PASSED",
                "repository": sandbox_test.EXPECTED_REPOSITORY,
                "pull_request_number": 32,
                "base_sha": BASE_SHA,
                "head_sha": HEAD_SHA,
                "proposal_id": "a" * 32,
                "proposal_hash": PROPOSAL_HASH,
                "approval_id": "b" * 32,
                "approval_record_hash": APPROVAL_HASH,
                "validation_request_actor": "validator",
                "policy_hash": POLICY_HASH,
            },
            result_hash=PREFLIGHT_HASH,
            artifact_id=102,
            artifact_name="sandbox-validation-preflight-test",
            workflow_run_id=202,
            workflow_name=sandbox_test.preflight.VALIDATOR_WORKFLOW_NAME,
        )

    def apply_result(self, *, overrides=None):
        proposal_bundle = self.proposal_bundle()
        patch_file_hash = sandbox_test.apply.sha256_hex_bytes(
            sandbox_test.apply.combined_patch_text(proposal_bundle.data).encode("utf-8")
        )
        check_pass = sandbox_test.check_result("PASS", "ok")
        artifact = {
            "artifact_id": 100,
            "artifact_name": "artifact",
            "workflow_run_id": 200,
            "workflow_name": "Workflow",
            "repository": sandbox_test.EXPECTED_REPOSITORY,
            "pull_request_number": 32,
            "head_sha": HEAD_SHA,
        }
        result = {
            "schema_version": "sandbox-validation-result-v1",
            "validation_id": "d" * 32,
            "phase": "SANDBOX_APPLY",
            "repository": sandbox_test.EXPECTED_REPOSITORY,
            "pull_request_number": 32,
            "base_sha": BASE_SHA,
            "head_sha": HEAD_SHA,
            "proposal_id": "a" * 32,
            "proposal_hash": PROPOSAL_HASH,
            "approval_id": "b" * 32,
            "approval_record_hash": APPROVAL_HASH,
            "approved_by": "approver",
            "approved_by_repository_permission": "admin",
            "approved_by_repository_role": "admin",
            "validation_request_actor": "validator",
            "validation_request_actor_repository_permission": "maintain",
            "validation_request_actor_repository_role": "maintain",
            "live_labels": [
                "ai-fix-proposal",
                "ai-fix-approved",
                "ai-fix-validate",
                "ai-fix-apply-sandbox",
            ],
            "proposal_artifact": dict(artifact),
            "approval_artifact": dict(artifact),
            "schema_versions": {
                "proposal": "1.0",
                "approval": "approval-record-v3",
                "validation_result": "sandbox-validation-result-v1",
            },
            "policy_hash": POLICY_HASH,
            "test_plan_hash": TEST_POLICY_HASH,
            "started_at": "2026-07-18T00:00:00Z",
            "completed_at": "2026-07-18T00:00:01Z",
            "status": "APPLY_PASSED",
            "failure_class": None,
            "failure_code": None,
            "patch_check": dict(check_pass),
            "patch_apply": dict(check_pass),
            "expected_files": ["canary/example.py"],
            "actual_changed_files": ["canary/example.py"],
            "protected_path_check": dict(check_pass),
            "blob_sha_check": dict(check_pass),
            "target_blob_checks": [
                {
                    "path": "canary/example.py",
                    "expected_blob_sha": "9" * 40,
                    "actual_blob_sha": "9" * 40,
                    "file_type": "blob",
                    "mode": "100644",
                    "size": 12,
                    "status": "PASS",
                }
            ],
            "patch_metadata_check": {
                "status": "PASS",
                "message": "ok",
                "patch_bytes": 127,
            },
            "tests_requested": [],
            "tests_executed": [],
            "test_results": [],
            "changed_files_match_expected": True,
            "persistent_repository_modified": False,
            "sandbox_worktree_modified": True,
            "sandbox_checkout_performed": True,
            "patch_check_performed": True,
            "patch_applied": True,
            "test_execution_performed": False,
            "commit_created": False,
            "push_performed": False,
            "merge_performed": False,
            "sandbox_destroyed": True,
            "apply_request_actor": "applier",
            "apply_request_actor_repository_permission": "admin",
            "apply_request_actor_repository_role": "admin",
            "preflight_validation_id": "c" * 32,
            "preflight_result_hash": PREFLIGHT_HASH,
            "preflight_artifact": dict(artifact),
            "checkout_performed": True,
            "checkout_sha": HEAD_SHA,
            "detached_head": True,
            "credentials_persisted": False,
            "patch_file_hash": patch_file_hash,
            "git_apply_check": dict(check_pass),
            "git_apply": dict(check_pass),
            "expected_changed_files": ["canary/example.py"],
            "resulting_file_hashes": [
                {
                    "path": "canary/example.py",
                    "resulting_blob_sha": "8" * 40,
                }
            ],
            "diff_binding": dict(check_pass),
            "tests_planned": ["unit", "compileall"],
            "sandbox_cleanup": dict(check_pass),
        }
        if overrides:
            result.update(overrides)
        return result

    def apply_bundle(self, *, result_overrides=None):
        return sandbox_test.ApplyBundle(
            result=self.apply_result(overrides=result_overrides),
            result_hash=APPLY_HASH,
            artifact_id=103,
            artifact_name="sandbox-apply-result-test",
            workflow_run_id=203,
            workflow_name=sandbox_test.apply.APPLY_WORKFLOW_NAME,
        )

    def make_test_context(self, *, apply_result_overrides=None):
        return sandbox_test.build_test_context(
            manifest=self.manifest(),
            proposal_bundle=self.proposal_bundle(),
            approval_bundle=self.approval_bundle(),
            preflight_bundle=self.preflight_bundle(),
            apply_bundle=self.apply_bundle(result_overrides=apply_result_overrides),
            test_policy=self.sandbox_test_policy(),
            test_commands=(
                self.sandbox_test_policy().commands["unit"],
                self.sandbox_test_policy().commands["compileall"],
            ),
            test_actor="tester",
            test_actor_permission="admin",
            test_actor_role="admin",
            validation_actor_permission="maintain",
            validation_actor_role="maintain",
            approval_actor_permission="admin",
            approval_actor_role="admin",
            apply_actor_permission="admin",
            apply_actor_role="admin",
            live_labels=[
                str(label["name"])
                for label in self.live_issue()["labels"]
            ],
        )

    def test_valid_test_manifest_and_live_gate(self):
        labels = sandbox_test.validate_live_test_gate(
            manifest=self.manifest(),
            live_pull=self.live_pull(),
            live_issue=self.live_issue(),
            policy=self.policy(),
            test_policy=self.sandbox_test_policy(),
            test_actor="tester",
            test_actor_permission="admin",
        )
        self.assertIn("ai-fix-test-sandbox", labels)

    def test_wrong_label_is_rejected(self):
        with self.assertRaises(sandbox_test.fix.FixProposalFailure):
            sandbox_test.validate_request_manifest_shape(
                self.manifest(event_label="ai-fix-apply-sandbox")
            )

    def test_missing_prior_live_label_is_rejected(self):
        with self.assertRaises(sandbox_test.fix.FixProposalFailure):
            sandbox_test.validate_live_test_gate(
                manifest=self.manifest(labels=["ai-fix-test-sandbox"]),
                live_pull=self.live_pull(),
                live_issue=self.live_issue(labels=["ai-fix-test-sandbox"]),
                policy=self.policy(),
                test_policy=self.sandbox_test_policy(),
                test_actor="tester",
                test_actor_permission="admin",
            )

    def test_fork_pr_is_rejected(self):
        with self.assertRaises(sandbox_test.fix.FixProposalFailure):
            sandbox_test.validate_live_test_gate(
                manifest=self.manifest(head_repository="fork/repo"),
                live_pull=self.live_pull(head_repo="fork/repo"),
                live_issue=self.live_issue(),
                policy=self.policy(),
                test_policy=self.sandbox_test_policy(),
                test_actor="tester",
                test_actor_permission="admin",
            )

    def test_write_permission_is_rejected(self):
        with self.assertRaises(sandbox_test.fix.FixProposalFailure):
            sandbox_test.validate_live_test_gate(
                manifest=self.manifest(),
                live_pull=self.live_pull(),
                live_issue=self.live_issue(),
                policy=self.policy(),
                test_policy=self.sandbox_test_policy(),
                test_actor="tester",
                test_actor_permission="write",
            )

    def test_stale_head_is_rejected(self):
        with self.assertRaises(sandbox_test.SandboxTestStatus):
            sandbox_test.validate_live_test_gate(
                manifest=self.manifest(),
                live_pull=self.live_pull(head_sha="d" * 40),
                live_issue=self.live_issue(),
                policy=self.policy(),
                test_policy=self.sandbox_test_policy(),
                test_actor="tester",
                test_actor_permission="maintain",
            )

    def test_trusted_test_id_resolves_to_fixed_command(self):
        recommendations = ["stage2c-b1-clamp"]
        commands = sandbox_test.resolve_requested_test_commands(
            recommendations,
            self.sandbox_test_policy(),
        )
        self.assertEqual(1, len(commands))
        self.assertEqual("stage2c-b1-clamp", commands[0].test_id)
        self.assertEqual(
            ("python3", "-m", "unittest", "stage2c_b1_clamp_tests"),
            commands[0].argv,
        )

    def test_all_fix_policy_test_ids_resolve_to_trusted_commands(self):
        recommendations = list(
            sandbox_test.preflight.load_sandbox_test_ids(
                REPO_ROOT / ".github" / "codex" / "fix-policy.yml"
            )
        )
        commands = sandbox_test.resolve_requested_test_commands(
            recommendations,
            self.sandbox_test_policy(),
        )
        self.assertEqual(recommendations, [command.test_id for command in commands])
        for command in commands:
            with self.subTest(test_id=command.test_id):
                self.assertEqual(("python3", "-m", "unittest"), command.argv[:3])
                self.assertNotIn(" ", command.test_id)

    def test_empty_tests_are_rejected(self):
        with self.assertRaises(sandbox_test.SandboxTestStatus):
            sandbox_test.resolve_requested_test_commands([], self.sandbox_test_policy())

    def test_unknown_or_natural_language_recommendation_is_rejected(self):
        cases = [
            ["python -m unittest discover"],
            [
                "Run the targeted clamp checks for clamp(5, 1, 3), clamp(0, 1, 3), and clamp(2, 1, 3).",
            ],
        ]
        for recommendations in cases:
            with self.subTest(recommendations=recommendations):
                with self.assertRaises(sandbox_test.SandboxTestStatus):
                    sandbox_test.resolve_requested_test_commands(
                        recommendations,
                        self.sandbox_test_policy(),
                    )

    def assert_bad_argv(self, argv):
        with self.assertRaises(sandbox_test.SandboxTestStatus):
            sandbox_test.validate_argv("bad", tuple(argv))

    def test_command_rejects_shell_and_unapproved_runners(self):
        self.assert_bad_argv(["bash", "-c", "echo bad"])
        self.assert_bad_argv(["sh", "-c", "echo bad"])
        self.assert_bad_argv(["git", "status"])
        self.assert_bad_argv(["pip", "install", "x"])
        self.assert_bad_argv(["curl", "https://example.test"])

    def test_command_rejects_inline_code_and_unsafe_args(self):
        self.assert_bad_argv(["python3", "-c", "print(1)"])
        self.assert_bad_argv(["python3", "-m", "os"])
        self.assert_bad_argv(["python3", "-m", "unittest", "../bad"])
        self.assert_bad_argv(["python3", "-m", "unittest", "/tmp/bad"])
        self.assert_bad_argv(["python3", "-m", "unittest", "bad\nname"])
        self.assert_bad_argv(["python3", "-m", "unittest", "bad\x00name"])
        self.assert_bad_argv(["python3", "-m", "unittest", "tests.*"])

    def test_python_runner_is_allowed_only_as_executable(self):
        sandbox_test.validate_argv(
            "ok",
            ("python", "-m", "unittest", "stage2c_b1_clamp_tests"),
        )

    def test_sandbox_test_id_is_deterministic(self):
        kwargs = {
            "repository": sandbox_test.EXPECTED_REPOSITORY,
            "pull_request_number": 32,
            "head_sha": HEAD_SHA,
            "proposal_id": "a" * 32,
            "proposal_hash": PROPOSAL_HASH,
            "approval_id": "b" * 32,
            "approval_record_hash": APPROVAL_HASH,
            "preflight_validation_id": "c" * 32,
            "preflight_result_hash": PREFLIGHT_HASH,
            "sandbox_apply_id": "d" * 32,
            "sandbox_apply_result_hash": APPLY_HASH,
            "test_request_actor": "tester",
            "policy_hash": POLICY_HASH,
            "sandbox_test_policy_hash": TEST_POLICY_HASH,
            "test_plan_hash": "4" * 64,
            "patch_file_hash": PATCH_HASH,
        }
        first = sandbox_test.sandbox_test_id_for(**kwargs)
        second = sandbox_test.sandbox_test_id_for(**kwargs)
        self.assertEqual(first, second)
        self.assertEqual(32, len(first))

    def test_policy_commands_use_logical_sandbox_cwd(self):
        commands = self.sandbox_test_policy().commands
        self.assertTrue(commands)
        for command in commands.values():
            with self.subTest(test_id=command.test_id):
                self.assertEqual(".", command.working_directory)

    def test_apply_contract_accepts_canonical_patch_file_hash(self):
        result = self.apply_result()
        sandbox_test.validate_apply_result_for_test(
            result=result,
            manifest=self.manifest(),
            proposal_bundle=self.proposal_bundle(),
            approval_bundle=self.approval_bundle(),
            preflight_bundle=self.preflight_bundle(),
            policy_hash=POLICY_HASH,
            schema_path=self.sandbox_apply_schema_path(),
        )

    def test_apply_contract_missing_patch_file_hash_fails_cleanly(self):
        result = self.apply_result()
        result.pop("patch_file_hash")
        with self.assertRaises(sandbox_test.fix.FixProposalFailure) as caught:
            sandbox_test.validate_apply_result_for_test(
                result=result,
                manifest=self.manifest(),
                proposal_bundle=self.proposal_bundle(),
                approval_bundle=self.approval_bundle(),
                preflight_bundle=self.preflight_bundle(),
                policy_hash=POLICY_HASH,
                schema_path=self.sandbox_apply_schema_path(),
            )
        self.assertIn("patch_file_hash", caught.exception.message)

    def test_apply_contract_rejects_bad_patch_file_hash_values(self):
        cases = [
            ("wrong type", 123),
            ("empty", ""),
            ("malformed", "not-a-sha"),
            ("mismatch", "0" * 64),
        ]
        for name, value in cases:
            with self.subTest(name=name):
                with self.assertRaises(sandbox_test.fix.FixProposalFailure):
                    sandbox_test.validate_apply_result_for_test(
                        result=self.apply_result(overrides={"patch_file_hash": value}),
                        manifest=self.manifest(),
                        proposal_bundle=self.proposal_bundle(),
                        approval_bundle=self.approval_bundle(),
                        preflight_bundle=self.preflight_bundle(),
                        policy_hash=POLICY_HASH,
                        schema_path=self.sandbox_apply_schema_path(),
                    )

    def test_apply_contract_rejects_legacy_synonym_without_canonical_field(self):
        result = self.apply_result()
        result["patch_hash"] = result.pop("patch_file_hash")
        with self.assertRaises(sandbox_test.fix.FixProposalFailure):
            sandbox_test.validate_apply_result_for_test(
                result=result,
                manifest=self.manifest(),
                proposal_bundle=self.proposal_bundle(),
                approval_bundle=self.approval_bundle(),
                preflight_bundle=self.preflight_bundle(),
                policy_hash=POLICY_HASH,
                schema_path=self.sandbox_apply_schema_path(),
            )

    def test_apply_contract_rejects_resulting_file_hash_mismatch(self):
        result = self.apply_result(
            overrides={
                "resulting_file_hashes": [
                    {"path": "canary/other.py", "resulting_blob_sha": "8" * 40}
                ]
            }
        )
        with self.assertRaises(sandbox_test.fix.FixProposalFailure):
            sandbox_test.validate_apply_result_for_test(
                result=result,
                manifest=self.manifest(),
                proposal_bundle=self.proposal_bundle(),
                approval_bundle=self.approval_bundle(),
                preflight_bundle=self.preflight_bundle(),
                policy_hash=POLICY_HASH,
                schema_path=self.sandbox_apply_schema_path(),
            )

    def test_test_context_records_apply_bindings_before_execution(self):
        context = self.make_test_context()
        self.assertEqual(
            context["sandbox_apply_result"]["patch_file_hash"],
            context["patch_file_hash"],
        )
        self.assertEqual(
            sandbox_test.sha256_hex_json(context["sandbox_apply_result"]["diff_binding"]),
            context["resulting_diff_hash"],
        )
        sandbox_test.validate_test_context_contract(context)

    def test_test_context_rejects_patch_file_hash_mismatch(self):
        context = self.make_test_context()
        context["patch_file_hash"] = "0" * 64
        with self.assertRaises(sandbox_test.SandboxTestStatus) as caught:
            sandbox_test.validate_test_context_contract(context)
        self.assertEqual("PATCH_HASH_MISMATCH", caught.exception.code)

    def test_test_context_rejects_missing_patch_file_hash_cleanly(self):
        context = self.make_test_context()
        context.pop("patch_file_hash")
        with self.assertRaises(sandbox_test.SandboxTestStatus) as caught:
            sandbox_test.validate_test_context_contract(context)
        self.assertEqual("APPLY_CONTRACT_INVALID", caught.exception.code)

    def test_test_context_rejects_resulting_file_hash_mismatch(self):
        context = self.make_test_context()
        context["sandbox_apply_result"]["resulting_file_hashes"] = [
            {"path": "canary/other.py", "resulting_blob_sha": "8" * 40}
        ]
        with self.assertRaises(sandbox_test.SandboxTestStatus) as caught:
            sandbox_test.validate_test_context_contract(context)
        self.assertEqual("RESULTING_FILE_HASH_MISMATCH", caught.exception.code)

    def test_test_context_rejects_resulting_diff_hash_mismatch(self):
        context = self.make_test_context()
        context["resulting_diff_hash"] = "0" * 64
        with self.assertRaises(sandbox_test.SandboxTestStatus) as caught:
            sandbox_test.validate_test_context_contract(context)
        self.assertEqual("RESULTING_DIFF_HASH_MISMATCH", caught.exception.code)

    def test_test_context_rejects_trusted_support_as_cwd_before_execution(self):
        context = self.make_test_context()
        context["test_commands"][0]["working_directory"] = "trusted-support"
        with self.assertRaises(sandbox_test.SandboxTestStatus) as caught:
            sandbox_test.validate_test_context_contract(context)
        self.assertEqual("UNAPPROVED_WORKING_DIRECTORY", caught.exception.code)

    def test_failure_result_uses_logical_cwd_and_validates_schema(self):
        context = self.make_test_context()
        result = sandbox_test.base_test_result(
            context=context,
            status=sandbox_test.RESULT_STATUS_BINDING_MISMATCH,
            failure_class=sandbox_test.RESULT_STATUS_BINDING_MISMATCH,
            failure_code="APPLY_CONTRACT_INVALID",
            failed_operation="sandbox_test_context_validation",
            last_error="apply contract invalid",
        )
        sandbox_test.validate_test_result_against_schema(
            result,
            self.sandbox_test_schema_path(),
        )
        self.assertEqual([".", "."], result["working_directories"])
        self.assertEqual(".", result["tests_requested"][0]["working_directory"])

    def test_success_result_uses_patch_file_hash_and_validates_schema(self):
        context = self.make_test_context()
        result = sandbox_test.base_test_result(
            context=context,
            status=sandbox_test.RESULT_STATUS_TESTS_PASSED,
            failure_class=None,
            failure_code=None,
        )
        pass_records = [
            sandbox_test.command_record(
                sandbox_test.TestCommandSpec(
                    test_id=str(item["test_id"]),
                    argv=tuple(str(arg) for arg in item["argv"]),
                    working_directory=str(item["working_directory"]),
                    timeout_seconds=int(item["timeout_seconds"]),
                ),
                status="PASS",
            )
            for item in context["test_commands"]
        ]
        result.update(
            {
                "tests_requested": pass_records,
                "tests_executed": pass_records,
                "commands": [record["argv"] for record in pass_records],
                "working_directories": [record["working_directory"] for record in pass_records],
                "exit_codes": [0 for _ in pass_records],
                "timeouts": [False for _ in pass_records],
                "stdout_hashes": [record["stdout_hash"] for record in pass_records],
                "stderr_hashes": [record["stderr_hash"] for record in pass_records],
                "stdout_truncated": [False for _ in pass_records],
                "stderr_truncated": [False for _ in pass_records],
                "stdout_byte_counts": [0 for _ in pass_records],
                "stderr_byte_counts": [0 for _ in pass_records],
                "credentials_available": False,
                "patch_apply_result": sandbox_test.check_result("PASS", "ok"),
                "cleanup_performed": True,
                "sandbox_destroyed": True,
            }
        )
        sandbox_test.validate_test_result_against_schema(
            result,
            self.sandbox_test_schema_path(),
        )
        self.assertIn("patch_file_hash", result)
        self.assertNotIn("patch_hash", result)

    def test_schema_rejects_trusted_support_working_directory(self):
        context = self.make_test_context()
        result = sandbox_test.base_test_result(
            context=context,
            status=sandbox_test.RESULT_STATUS_BINDING_MISMATCH,
            failure_class=sandbox_test.RESULT_STATUS_BINDING_MISMATCH,
            failure_code="APPLY_CONTRACT_INVALID",
        )
        result["tests_requested"][0]["working_directory"] = "trusted-support"
        result["working_directories"][0] = "trusted-support"
        with self.assertRaises(sandbox_test.apply.SchemaValidationError):
            sandbox_test.validate_test_result_against_schema(
                result,
                self.sandbox_test_schema_path(),
            )

    def test_command_run_tests_rejects_bad_cwd_before_command_execution(self):
        context = self.make_test_context()
        context["test_commands"][0]["working_directory"] = "trusted-support"
        called = False
        old_run_one_test = sandbox_test.run_one_test
        old_env = os.environ.copy()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            context_dir = root / "context"
            context_dir.mkdir()
            sandbox_test.write_json_file(
                context_dir / sandbox_test.TEST_CONTEXT_FILE,
                context,
            )
            os.environ.update(
                {
                    "TEST_CONTEXT_DIR": str(context_dir),
                    "TEST_RESULT_DIR": str(root / "result"),
                    "SANDBOX_WORKTREE": str(root / "worktree"),
                    "PATCH_FILE": str(root / "patch.diff"),
                    "SANDBOX_TEST_RESULT_SCHEMA": str(self.sandbox_test_schema_path()),
                    "TEST_SUPPORT_DIR": str(REPO_ROOT / "scripts" / "sandbox_test_support"),
                }
            )

            def forbidden_run_one_test(**_kwargs):
                nonlocal called
                called = True
                raise AssertionError("test command should not execute")

            sandbox_test.run_one_test = forbidden_run_one_test
            try:
                self.assertEqual(0, sandbox_test.command_run_tests(None))
                result = sandbox_test.read_json_file(
                    root / "result" / "sandbox-test-result.json"
                )
                sandbox_test.validate_test_result_against_schema(
                    result,
                    self.sandbox_test_schema_path(),
                )
                self.assertEqual("TEST_COMMAND_REJECTED", result["status"])
                self.assertEqual("UNAPPROVED_WORKING_DIRECTORY", result["failure_code"])
                self.assertEqual(0, len(result["tests_executed"]))
            finally:
                sandbox_test.run_one_test = old_run_one_test
                os.environ.clear()
                os.environ.update(old_env)
        self.assertFalse(called)

    def test_secret_environment_is_not_propagated(self):
        old = os.environ.get("GITHUB_TOKEN")
        os.environ["GITHUB_TOKEN"] = "secret"
        try:
            env = sandbox_test.test_environment(
                allowed_environment=("PATH", "PYTHONPATH"),
                support_dir=REPO_ROOT / "scripts" / "sandbox_test_support",
            )
        finally:
            if old is None:
                os.environ.pop("GITHUB_TOKEN", None)
            else:
                os.environ["GITHUB_TOKEN"] = old
        self.assertNotIn("GITHUB_TOKEN", env)
        self.assertIn("PYTHONPATH", env)

    def test_test_runner_step_does_not_export_github_token(self):
        workflow = (
            REPO_ROOT / ".github" / "workflows" / "fix-sandbox-test.yml"
        ).read_text(encoding="utf-8")
        marker = "      - name: Run approved tests in ephemeral sandbox"
        start = workflow.index(marker)
        end = workflow.find("\n      - name:", start + len(marker))
        step = workflow[start:] if end == -1 else workflow[start:end]
        self.assertNotIn("GITHUB_TOKEN", step)

    def test_total_timeout_limits_effective_command_timeout(self):
        current = sandbox_test.time.monotonic
        try:
            sandbox_test.time.monotonic = lambda: 105.0
            timeout = sandbox_test.effective_command_timeout(
                start_time=100.0,
                total_timeout_seconds=30,
                command_timeout_seconds=120,
            )
            self.assertEqual(25, timeout)
        finally:
            sandbox_test.time.monotonic = current

    def test_total_timeout_expiry_is_rejected(self):
        current = sandbox_test.time.monotonic
        try:
            sandbox_test.time.monotonic = lambda: 131.0
            with self.assertRaises(sandbox_test.SandboxTestStatus):
                sandbox_test.effective_command_timeout(
                    start_time=100.0,
                    total_timeout_seconds=30,
                    command_timeout_seconds=120,
                )
        finally:
            sandbox_test.time.monotonic = current

    def test_output_truncation_records_flag(self):
        truncated, flag = sandbox_test.redacted_output(b"abcdef", 3)
        self.assertEqual(b"abc", truncated)
        self.assertTrue(flag)

    @unittest.skipUnless(python3_works(), "python3 is unavailable locally")
    def test_approved_unittest_command_passes_against_trusted_support(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "canary").mkdir()
            (root / "canary" / "__init__.py").write_text("", encoding="utf-8")
            (root / "canary" / "stage2c_b1_clamp.py").write_text(
                "\n".join(
                    [
                        "def clamp(value: int, minimum: int, maximum: int) -> int:",
                        "    return min(max(value, minimum), maximum)",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            env = sandbox_test.test_environment(
                allowed_environment=("PATH", "PYTHONPATH"),
                support_dir=REPO_ROOT / "scripts" / "sandbox_test_support",
                worktree=root,
            )
            command = self.sandbox_test_policy().commands["stage2c-b1-clamp"]
            record, _, _ = sandbox_test.run_one_test(
                command=command,
                worktree=root,
                support_dir=REPO_ROOT / "scripts" / "sandbox_test_support",
                env=env,
                stdout_limit=100000,
                stderr_limit=100000,
            )
            self.assertEqual("PASS", record["status"])
            self.assertEqual(0, record["exit_code"])

    @unittest.skipUnless(python3_works(), "python3 is unavailable locally")
    def test_approved_unittest_command_reports_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "canary").mkdir()
            (root / "canary" / "__init__.py").write_text("", encoding="utf-8")
            (root / "canary" / "stage2c_b1_clamp.py").write_text(
                "\n".join(
                    [
                        "def clamp(value: int, minimum: int, maximum: int) -> int:",
                        "    return min(minimum, max(value, maximum))",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            env = sandbox_test.test_environment(
                allowed_environment=("PATH", "PYTHONPATH"),
                support_dir=REPO_ROOT / "scripts" / "sandbox_test_support",
                worktree=root,
            )
            command = self.sandbox_test_policy().commands["stage2c-b1-clamp"]
            record, _, _ = sandbox_test.run_one_test(
                command=command,
                worktree=root,
                support_dir=REPO_ROOT / "scripts" / "sandbox_test_support",
                env=env,
                stdout_limit=100000,
                stderr_limit=100000,
            )
            self.assertEqual("FAIL", record["status"])

    @unittest.skipUnless(python3_works(), "python3 is unavailable locally")
    def test_worktree_cannot_shadow_trusted_support_test_module(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "canary").mkdir()
            (root / "canary" / "__init__.py").write_text("", encoding="utf-8")
            (root / "canary" / "stage2c_b1_clamp.py").write_text(
                "\n".join(
                    [
                        "def clamp(value: int, minimum: int, maximum: int) -> int:",
                        "    return value",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (root / "stage2c_b1_clamp_tests.py").write_text(
                "\n".join(
                    [
                        "import unittest",
                        "",
                        "class ShadowedTests(unittest.TestCase):",
                        "    def test_shadow_would_pass(self):",
                        "        self.assertTrue(True)",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            support_dir = REPO_ROOT / "scripts" / "sandbox_test_support"
            env = sandbox_test.test_environment(
                allowed_environment=("PATH", "PYTHONPATH"),
                support_dir=support_dir,
                worktree=root,
            )
            command = self.sandbox_test_policy().commands["stage2c-b1-clamp"]
            record, _, _ = sandbox_test.run_one_test(
                command=command,
                worktree=root,
                support_dir=support_dir,
                env=env,
                stdout_limit=100000,
                stderr_limit=100000,
            )
            self.assertEqual("FAIL", record["status"])
            self.assertNotEqual(0, record["exit_code"])


if __name__ == "__main__":
    unittest.main()
