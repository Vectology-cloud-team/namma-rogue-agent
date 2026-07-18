from __future__ import annotations

import io
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
import stat
import warnings
import zipfile
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

    def schema_path(self) -> Path:
        return REPO_ROOT / ".github" / "codex" / "schemas" / "sandbox-validation-result.schema.json"

    def canonical_preflight_sidecars(
        self,
        *,
        result_overrides=None,
        proposal_manifest_overrides=None,
        approval_manifest_overrides=None,
        target_blob_checks=None,
        patch_metadata_overrides=None,
    ):
        proposal_bundle = self.proposal_bundle()
        approval_bundle = self.approval_bundle()
        patch_bytes = sandbox_apply.proposal_raw_patch_bytes(proposal_bundle.data)
        blob_checks = target_blob_checks
        if blob_checks is None:
            blob_checks = [
                {
                    "actual_blob_sha": "9" * 40,
                    "expected_blob_sha": "9" * 40,
                    "file_type": "blob",
                    "mode": "100644",
                    "path": "canary/example.py",
                    "size": 13,
                    "status": "PASS",
                }
            ]
        patch_metadata = {
            "expected_files": ["canary/example.py"],
            "message": "validated metadata for 1 file(s)",
            "patch_bytes": patch_bytes,
            "status": "PASS",
        }
        if patch_metadata_overrides:
            patch_metadata.update(patch_metadata_overrides)
        result = {
            **self.preflight_result(),
            "expected_files": ["canary/example.py"],
            "proposal_artifact": {
                "artifact_id": proposal_bundle.artifact_id,
                "artifact_name": proposal_bundle.artifact_name,
                "workflow_run_id": proposal_bundle.workflow_run_id,
                "workflow_name": proposal_bundle.workflow_name,
                "repository": sandbox_apply.EXPECTED_REPOSITORY,
                "pull_request_number": 31,
                "head_sha": HEAD_SHA,
            },
            "approval_artifact": {
                "artifact_id": approval_bundle.artifact_id,
                "artifact_name": approval_bundle.artifact_name,
                "workflow_run_id": approval_bundle.workflow_run_id,
                "workflow_name": approval_bundle.workflow_name,
                "repository": sandbox_apply.EXPECTED_REPOSITORY,
                "pull_request_number": 31,
                "head_sha": HEAD_SHA,
            },
            "protected_path_check": {"status": "PASS", "message": "ok"},
            "blob_sha_check": {"status": "PASS", "message": "ok"},
            "target_blob_checks": blob_checks,
            "patch_metadata_check": {
                "status": patch_metadata["status"],
                "message": patch_metadata["message"],
                "patch_bytes": patch_metadata["patch_bytes"],
            },
        }
        if result_overrides:
            result.update(result_overrides)
        proposal_manifest = {
            "artifact_id": proposal_bundle.artifact_id,
            "artifact_name": proposal_bundle.artifact_name,
            "workflow_run_id": proposal_bundle.workflow_run_id,
            "proposal_id": proposal_bundle.metadata["proposal_id"],
            "proposal_hash": proposal_bundle.metadata["proposal_hash"],
            "head_sha": proposal_bundle.metadata["head_sha"],
        }
        if proposal_manifest_overrides:
            proposal_manifest.update(proposal_manifest_overrides)
        approval_manifest = {
            "artifact_id": approval_bundle.artifact_id,
            "artifact_name": approval_bundle.artifact_name,
            "workflow_run_id": approval_bundle.workflow_run_id,
            "approval_id": approval_bundle.record["approval_id"],
            "approval_record_hash": approval_bundle.record["approval_record_hash"],
            "head_sha": approval_bundle.record["head_sha"],
        }
        if approval_manifest_overrides:
            approval_manifest.update(approval_manifest_overrides)
        return (
            {
                "sandbox-validation-result.json": result,
                "selected-proposal-manifest.json": proposal_manifest,
                "selected-approval-manifest.json": approval_manifest,
                "target-blob-checks.json": blob_checks,
                "patch-metadata-check.json": patch_metadata,
            },
            proposal_bundle,
            approval_bundle,
        )

    def preflight_zip_bytes(self, sidecars, *, duplicate_name=None, symlink_name=None):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            for name, value in sidecars.items():
                archive.writestr(name, sandbox_apply.canonical_json_bytes(value))
            if duplicate_name is not None:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
                    archive.writestr(duplicate_name, b"{}")
            if symlink_name is not None:
                info = zipfile.ZipInfo(symlink_name)
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                archive.writestr(info, b"target")
        return buffer.getvalue()

    def validate_sidecars(self, sidecars, proposal_bundle, approval_bundle):
        sandbox_apply.validate_preflight_sidecars(
            result=sidecars["sandbox-validation-result.json"],
            proposal_manifest=sidecars["selected-proposal-manifest.json"],
            approval_manifest=sidecars["selected-approval-manifest.json"],
            target_blob_checks=sidecars["target-blob-checks.json"],
            patch_metadata_check=sidecars["patch-metadata-check.json"],
            manifest=self.manifest(),
            proposal_bundle=proposal_bundle,
            approval_bundle=approval_bundle,
            policy_hash=self.policy().policy_hash,
        )

    def apply_context(
        self,
        *,
        head_sha=HEAD_SHA,
        expected_files=None,
        patch_text=None,
    ):
        proposal_bundle = self.proposal_bundle()
        approval_bundle = self.approval_bundle()
        if patch_text is None:
            patch_text = str(proposal_bundle.data["changes"][0]["patch"])
        proposal_bundle.data["head_sha"] = head_sha
        proposal_bundle.data["changes"][0]["patch"] = patch_text
        proposal_bundle.metadata["head_sha"] = head_sha
        approval_bundle.record["head_sha"] = head_sha
        return {
            "manifest": self.manifest(head_sha=head_sha),
            "proposal": proposal_bundle.data,
            "proposal_metadata": proposal_bundle.metadata,
            "approval_record": approval_bundle.record,
            "preflight_result": {
                **self.preflight_result(head_sha=head_sha),
                "protected_path_check": {"status": "PASS", "message": "ok"},
                "blob_sha_check": {"status": "PASS", "message": "ok"},
                "target_blob_checks": [],
                "patch_metadata_check": {
                    "status": "PASS",
                    "message": "ok",
                    "patch_bytes": len(patch_text.encode("utf-8")),
                },
            },
            "preflight_result_hash": PREFLIGHT_HASH,
            "proposal_artifact": {
                "artifact_id": proposal_bundle.artifact_id,
                "artifact_name": proposal_bundle.artifact_name,
                "workflow_run_id": proposal_bundle.workflow_run_id,
                "workflow_name": proposal_bundle.workflow_name,
                "repository": sandbox_apply.EXPECTED_REPOSITORY,
                "pull_request_number": 31,
                "head_sha": head_sha,
            },
            "approval_artifact": {
                "artifact_id": approval_bundle.artifact_id,
                "artifact_name": approval_bundle.artifact_name,
                "workflow_run_id": approval_bundle.workflow_run_id,
                "workflow_name": approval_bundle.workflow_name,
                "repository": sandbox_apply.EXPECTED_REPOSITORY,
                "pull_request_number": 31,
                "head_sha": head_sha,
            },
            "preflight_artifact": {
                "artifact_id": 102,
                "artifact_name": "sandbox-validation-preflight-test",
                "workflow_run_id": 202,
                "workflow_name": sandbox_apply.preflight.VALIDATOR_WORKFLOW_NAME,
                "repository": sandbox_apply.EXPECTED_REPOSITORY,
                "pull_request_number": 31,
                "head_sha": head_sha,
            },
            "apply_id": "5" * 32,
            "apply_request_actor": "applier",
            "apply_request_actor_repository_permission": "maintain",
            "apply_request_actor_repository_role": "maintain",
            "validation_request_actor": "validator",
            "validation_request_actor_repository_permission": "admin",
            "validation_request_actor_repository_role": "admin",
            "approved_by_repository_permission": "admin",
            "approved_by_repository_role": "admin",
            "live_labels": [
                "ai-fix-proposal",
                "ai-fix-approved",
                "ai-fix-validate",
                "ai-fix-apply-sandbox",
            ],
            "expected_files": expected_files or ["canary/example.py"],
            "patch_text": patch_text,
            "patch_file_hash": sandbox_apply.sha256_hex_bytes(patch_text.encode("utf-8")),
            "planned_test_ids": ["unit"],
            "test_plan_hash": "8" * 64,
            "started_at": "2026-07-18T00:00:00Z",
        }

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

    def test_canonical_five_member_preflight_artifact_is_accepted(self):
        sidecars, proposal_bundle, approval_bundle = self.canonical_preflight_sidecars()
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            sandbox_apply.safe_extract_canonical_preflight_zip(
                self.preflight_zip_bytes(sidecars),
                target,
                max_bytes=100000,
            )
            self.assertEqual(
                sandbox_apply.PREFLIGHT_ARTIFACT_MEMBERS,
                {path.name for path in target.iterdir()},
            )
            loaded = {
                name: sandbox_apply.read_json_file(target / name)
                for name in sandbox_apply.PREFLIGHT_ARTIFACT_MEMBERS
            }
        self.validate_sidecars(loaded, proposal_bundle, approval_bundle)

    def test_preflight_artifact_rejects_missing_selected_proposal(self):
        sidecars, _, _ = self.canonical_preflight_sidecars()
        del sidecars["selected-proposal-manifest.json"]
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(sandbox_apply.fix.FixProposalFailure):
                sandbox_apply.safe_extract_canonical_preflight_zip(
                    self.preflight_zip_bytes(sidecars),
                    Path(tmp),
                    max_bytes=100000,
                )

    def test_preflight_artifact_rejects_missing_selected_approval(self):
        sidecars, _, _ = self.canonical_preflight_sidecars()
        del sidecars["selected-approval-manifest.json"]
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(sandbox_apply.fix.FixProposalFailure):
                sandbox_apply.safe_extract_canonical_preflight_zip(
                    self.preflight_zip_bytes(sidecars),
                    Path(tmp),
                    max_bytes=100000,
                )

    def test_preflight_artifact_rejects_missing_target_blob_checks(self):
        sidecars, _, _ = self.canonical_preflight_sidecars()
        del sidecars["target-blob-checks.json"]
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(sandbox_apply.fix.FixProposalFailure):
                sandbox_apply.safe_extract_canonical_preflight_zip(
                    self.preflight_zip_bytes(sidecars),
                    Path(tmp),
                    max_bytes=100000,
                )

    def test_preflight_artifact_rejects_missing_patch_metadata(self):
        sidecars, _, _ = self.canonical_preflight_sidecars()
        del sidecars["patch-metadata-check.json"]
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(sandbox_apply.fix.FixProposalFailure):
                sandbox_apply.safe_extract_canonical_preflight_zip(
                    self.preflight_zip_bytes(sidecars),
                    Path(tmp),
                    max_bytes=100000,
                )

    def test_preflight_artifact_rejects_unknown_extra_member(self):
        sidecars, _, _ = self.canonical_preflight_sidecars()
        sidecars["unknown-extra.json"] = {"status": "PASS"}
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(sandbox_apply.fix.FixProposalFailure):
                sandbox_apply.safe_extract_canonical_preflight_zip(
                    self.preflight_zip_bytes(sidecars),
                    Path(tmp),
                    max_bytes=100000,
                )

    def test_preflight_artifact_rejects_duplicate_member(self):
        sidecars, _, _ = self.canonical_preflight_sidecars()
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(sandbox_apply.fix.FixProposalFailure):
                sandbox_apply.safe_extract_canonical_preflight_zip(
                    self.preflight_zip_bytes(
                        sidecars,
                        duplicate_name="sandbox-validation-result.json",
                    ),
                    Path(tmp),
                    max_bytes=100000,
                )

    def test_preflight_artifact_rejects_path_prefixed_expected_member(self):
        sidecars, _, _ = self.canonical_preflight_sidecars()
        sidecars["nested/sandbox-validation-result.json"] = sidecars.pop(
            "sandbox-validation-result.json"
        )
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(sandbox_apply.fix.FixProposalFailure):
                sandbox_apply.safe_extract_canonical_preflight_zip(
                    self.preflight_zip_bytes(sidecars),
                    Path(tmp),
                    max_bytes=100000,
                )

    def test_preflight_artifact_rejects_path_traversal_member(self):
        sidecars, _, _ = self.canonical_preflight_sidecars()
        sidecars["../sandbox-validation-result.json"] = sidecars.pop(
            "sandbox-validation-result.json"
        )
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(sandbox_apply.fix.FixProposalFailure):
                sandbox_apply.safe_extract_canonical_preflight_zip(
                    self.preflight_zip_bytes(sidecars),
                    Path(tmp),
                    max_bytes=100000,
                )

    def test_preflight_artifact_rejects_symlink_member(self):
        sidecars, _, _ = self.canonical_preflight_sidecars()
        del sidecars["patch-metadata-check.json"]
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(sandbox_apply.fix.FixProposalFailure):
                sandbox_apply.safe_extract_canonical_preflight_zip(
                    self.preflight_zip_bytes(
                        sidecars,
                        symlink_name="patch-metadata-check.json",
                    ),
                    Path(tmp),
                    max_bytes=100000,
                )

    def test_preflight_artifact_rejects_unicode_case_collision(self):
        sidecars, _, _ = self.canonical_preflight_sidecars()
        sidecars["Sandbox-Validation-Result.json"] = {"status": "PASS"}
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(sandbox_apply.fix.FixProposalFailure):
                sandbox_apply.safe_extract_canonical_preflight_zip(
                    self.preflight_zip_bytes(sidecars),
                    Path(tmp),
                    max_bytes=100000,
                )

    def test_preflight_sidecar_rejects_patch_metadata_failure(self):
        sidecars, proposal_bundle, approval_bundle = self.canonical_preflight_sidecars(
            patch_metadata_overrides={"status": "FAIL"}
        )
        with self.assertRaises(sandbox_apply.fix.FixProposalFailure):
            self.validate_sidecars(sidecars, proposal_bundle, approval_bundle)

    def test_preflight_sidecar_uses_raw_patch_bytes_without_trailing_newline(self):
        sidecars, proposal_bundle, approval_bundle = self.canonical_preflight_sidecars()
        proposal_bundle.data["changes"][0]["patch"] = str(
            proposal_bundle.data["changes"][0]["patch"]
        ).rstrip("\n")
        raw_bytes = sandbox_apply.proposal_raw_patch_bytes(proposal_bundle.data)
        sidecars["patch-metadata-check.json"]["patch_bytes"] = raw_bytes
        sidecars["sandbox-validation-result.json"]["patch_metadata_check"][
            "patch_bytes"
        ] = raw_bytes
        self.validate_sidecars(sidecars, proposal_bundle, approval_bundle)

    def test_preflight_sidecar_rejects_changed_files_mismatch(self):
        sidecars, proposal_bundle, approval_bundle = self.canonical_preflight_sidecars(
            patch_metadata_overrides={"expected_files": ["canary/other.py"]}
        )
        with self.assertRaises(sandbox_apply.fix.FixProposalFailure):
            self.validate_sidecars(sidecars, proposal_bundle, approval_bundle)

    def test_preflight_sidecar_rejects_proposal_id_mismatch(self):
        sidecars, proposal_bundle, approval_bundle = self.canonical_preflight_sidecars(
            proposal_manifest_overrides={"proposal_id": "x" * 32}
        )
        with self.assertRaises(sandbox_apply.fix.FixProposalFailure):
            self.validate_sidecars(sidecars, proposal_bundle, approval_bundle)

    def test_preflight_sidecar_rejects_proposal_hash_mismatch(self):
        sidecars, proposal_bundle, approval_bundle = self.canonical_preflight_sidecars(
            proposal_manifest_overrides={"proposal_hash": "x" * 64}
        )
        with self.assertRaises(sandbox_apply.fix.FixProposalFailure):
            self.validate_sidecars(sidecars, proposal_bundle, approval_bundle)

    def test_preflight_sidecar_rejects_approval_id_mismatch(self):
        sidecars, proposal_bundle, approval_bundle = self.canonical_preflight_sidecars(
            approval_manifest_overrides={"approval_id": "x" * 32}
        )
        with self.assertRaises(sandbox_apply.fix.FixProposalFailure):
            self.validate_sidecars(sidecars, proposal_bundle, approval_bundle)

    def test_preflight_sidecar_rejects_head_mismatch(self):
        sidecars, proposal_bundle, approval_bundle = self.canonical_preflight_sidecars(
            result_overrides={"head_sha": "4" * 40}
        )
        with self.assertRaises(sandbox_apply.fix.FixProposalFailure):
            self.validate_sidecars(sidecars, proposal_bundle, approval_bundle)

    def test_preflight_sidecar_rejects_blob_sha_mismatch(self):
        sidecars, proposal_bundle, approval_bundle = self.canonical_preflight_sidecars(
            target_blob_checks=[
                {
                    "actual_blob_sha": "8" * 40,
                    "expected_blob_sha": "8" * 40,
                    "file_type": "blob",
                    "mode": "100644",
                    "path": "canary/example.py",
                    "size": 13,
                    "status": "PASS",
                }
            ]
        )
        with self.assertRaises(sandbox_apply.fix.FixProposalFailure):
            self.validate_sidecars(sidecars, proposal_bundle, approval_bundle)

    def test_preflight_sidecar_rejects_provenance_mismatch(self):
        sidecars, proposal_bundle, approval_bundle = self.canonical_preflight_sidecars(
            result_overrides={
                "proposal_artifact": {
                    "artifact_id": 999,
                    "artifact_name": "fix-proposal-test",
                    "workflow_run_id": 200,
                    "workflow_name": sandbox_apply.fix.GENERATOR_WORKFLOW_NAME,
                    "repository": sandbox_apply.EXPECTED_REPOSITORY,
                    "pull_request_number": 31,
                    "head_sha": HEAD_SHA,
                }
            }
        )
        with self.assertRaises(sandbox_apply.fix.FixProposalFailure):
            self.validate_sidecars(sidecars, proposal_bundle, approval_bundle)

    def test_find_latest_preflight_accepts_pr32_regression_shape(self):
        sidecars, proposal_bundle, approval_bundle = self.canonical_preflight_sidecars()
        old_github_json = sandbox_apply.stage1.github_json
        old_github_api_request = sandbox_apply.stage1.github_api_request
        try:
            def fake_github_json(method, path, *, token):
                if path.endswith("/actions/workflows/fix-sandbox.yml/runs?status=completed&per_page=50"):
                    return {"workflow_runs": [{"id": 202, "conclusion": "success"}]}, {}
                if path.endswith("/actions/runs/202/artifacts?per_page=100"):
                    return {
                        "artifacts": [
                            {
                                "id": 102,
                                "name": "sandbox-validation-preflight-test",
                            }
                        ]
                    }, {}
                raise AssertionError(path)

            def fake_github_api_request(method, path, *, token, max_response_bytes):
                self.assertEqual("/repos/test/actions/artifacts/102/zip", path)
                return self.preflight_zip_bytes(sidecars), {}

            sandbox_apply.stage1.github_json = fake_github_json
            sandbox_apply.stage1.github_api_request = fake_github_api_request
            with tempfile.TemporaryDirectory() as tmp:
                bundle = sandbox_apply.find_latest_preflight_artifact(
                    repo="test",
                    token="token",
                    manifest=self.manifest(),
                    proposal_bundle=proposal_bundle,
                    approval_bundle=approval_bundle,
                    policy_hash=self.policy().policy_hash,
                    output_dir=Path(tmp),
                    max_bytes=100000,
                )
            self.assertEqual(102, bundle.artifact_id)
            self.assertEqual("1" * 32, bundle.result["validation_id"])
        finally:
            sandbox_apply.stage1.github_json = old_github_json
            sandbox_apply.stage1.github_api_request = old_github_api_request

    def test_find_latest_preflight_skips_missing_candidate(self):
        sidecars, proposal_bundle, approval_bundle = self.canonical_preflight_sidecars()
        old_github_json = sandbox_apply.stage1.github_json
        old_github_api_request = sandbox_apply.stage1.github_api_request
        try:
            def fake_github_json(method, path, *, token):
                if path.endswith("/actions/workflows/fix-sandbox.yml/runs?status=completed&per_page=50"):
                    return {
                        "workflow_runs": [
                            {"id": 203, "conclusion": "success"},
                            {"id": 202, "conclusion": "success"},
                        ]
                    }, {}
                if path.endswith("/actions/runs/203/artifacts?per_page=100"):
                    return {"artifacts": []}, {}
                if path.endswith("/actions/runs/202/artifacts?per_page=100"):
                    return {
                        "artifacts": [
                            {
                                "id": 102,
                                "name": "sandbox-validation-preflight-test",
                            }
                        ]
                    }, {}
                raise AssertionError(path)

            def fake_github_api_request(method, path, *, token, max_response_bytes):
                return self.preflight_zip_bytes(sidecars), {}

            sandbox_apply.stage1.github_json = fake_github_json
            sandbox_apply.stage1.github_api_request = fake_github_api_request
            with tempfile.TemporaryDirectory() as tmp:
                bundle = sandbox_apply.find_latest_preflight_artifact(
                    repo="test",
                    token="token",
                    manifest=self.manifest(),
                    proposal_bundle=proposal_bundle,
                    approval_bundle=approval_bundle,
                    policy_hash=self.policy().policy_hash,
                    output_dir=Path(tmp),
                    max_bytes=100000,
                )
            self.assertEqual(202, bundle.workflow_run_id)
        finally:
            sandbox_apply.stage1.github_json = old_github_json
            sandbox_apply.stage1.github_api_request = old_github_api_request

    def test_find_latest_preflight_does_not_fallback_after_downloaded_extra_member(self):
        valid_sidecars, proposal_bundle, approval_bundle = self.canonical_preflight_sidecars()
        invalid_sidecars = dict(valid_sidecars)
        invalid_sidecars["unknown-extra.json"] = {"status": "PASS"}
        old_github_json = sandbox_apply.stage1.github_json
        old_github_api_request = sandbox_apply.stage1.github_api_request
        downloaded: list[str] = []
        try:
            def fake_github_json(method, path, *, token):
                if path.endswith("/actions/workflows/fix-sandbox.yml/runs?status=completed&per_page=50"):
                    return {
                        "workflow_runs": [
                            {"id": 203, "conclusion": "success"},
                            {"id": 202, "conclusion": "success"},
                        ]
                    }, {}
                if path.endswith("/actions/runs/203/artifacts?per_page=100"):
                    return {
                        "artifacts": [
                            {
                                "id": 103,
                                "name": "sandbox-validation-preflight-new",
                            }
                        ]
                    }, {}
                if path.endswith("/actions/runs/202/artifacts?per_page=100"):
                    return {
                        "artifacts": [
                            {
                                "id": 102,
                                "name": "sandbox-validation-preflight-old",
                            }
                        ]
                    }, {}
                raise AssertionError(path)

            def fake_github_api_request(method, path, *, token, max_response_bytes):
                downloaded.append(path)
                if path.endswith("/103/zip"):
                    return self.preflight_zip_bytes(invalid_sidecars), {}
                return self.preflight_zip_bytes(valid_sidecars), {}

            sandbox_apply.stage1.github_json = fake_github_json
            sandbox_apply.stage1.github_api_request = fake_github_api_request
            with tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(sandbox_apply.fix.FixProposalFailure):
                    sandbox_apply.find_latest_preflight_artifact(
                        repo="test",
                        token="token",
                        manifest=self.manifest(),
                        proposal_bundle=proposal_bundle,
                        approval_bundle=approval_bundle,
                        policy_hash=self.policy().policy_hash,
                        output_dir=Path(tmp),
                        max_bytes=100000,
                    )
            self.assertEqual(["/repos/test/actions/artifacts/103/zip"], downloaded)
        finally:
            sandbox_apply.stage1.github_json = old_github_json
            sandbox_apply.stage1.github_api_request = old_github_api_request

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
        context = self.apply_context()
        result = sandbox_apply.base_apply_result(
            context=context,
            status="PATCH_REJECTED",
            failure_class="PATCH_REJECTED",
            failure_code="GIT_COMMAND_FAILED",
        )
        self.assertFalse(result["test_execution_performed"])
        self.assertEqual([], result["tests_executed"])
        self.assertEqual("SKIPPED", result["tests_requested"][0]["status"])

    def test_apply_passed_result_shape_validates_actual_json_schema(self):
        context = self.apply_context()
        result = sandbox_apply.base_apply_result(
            context=context,
            status=sandbox_apply.RESULT_STATUS_APPLY_PASSED,
            failure_class=None,
            failure_code=None,
        )
        result.update(
            {
                "patch_check": sandbox_apply.check_result("PASS", "check ok"),
                "patch_apply": sandbox_apply.check_result("PASS", "apply ok"),
                "actual_changed_files": ["canary/example.py"],
                "changed_files_match_expected": True,
                "sandbox_worktree_modified": True,
                "sandbox_checkout_performed": True,
                "patch_check_performed": True,
                "patch_applied": True,
                "sandbox_destroyed": True,
                "checkout_performed": True,
                "checkout_sha": HEAD_SHA,
                "detached_head": True,
                "credentials_persisted": False,
                "git_apply_check": sandbox_apply.check_result("PASS", "check ok"),
                "git_apply": sandbox_apply.check_result("PASS", "apply ok"),
                "resulting_file_hashes": [
                    {"path": "canary/example.py", "resulting_blob_sha": "6" * 40},
                ],
                "diff_binding": sandbox_apply.check_result("PASS", "diff ok"),
                "sandbox_cleanup": sandbox_apply.check_result("PASS", "cleanup ok"),
            }
        )
        sandbox_apply.validate_apply_result_against_schema(result, self.schema_path())

    def test_schema_validation_rejects_nested_diff_binding_extra_fields(self):
        context = self.apply_context()
        result = sandbox_apply.base_apply_result(
            context=context,
            status=sandbox_apply.RESULT_STATUS_APPLY_PASSED,
            failure_class=None,
            failure_code=None,
        )
        result.update(
            {
                "patch_check": sandbox_apply.check_result("PASS", "check ok"),
                "patch_apply": sandbox_apply.check_result("PASS", "apply ok"),
                "actual_changed_files": ["canary/example.py"],
                "changed_files_match_expected": True,
                "sandbox_worktree_modified": True,
                "sandbox_checkout_performed": True,
                "patch_check_performed": True,
                "patch_applied": True,
                "sandbox_destroyed": True,
                "checkout_performed": True,
                "checkout_sha": HEAD_SHA,
                "detached_head": True,
                "credentials_persisted": False,
                "git_apply_check": sandbox_apply.check_result("PASS", "check ok"),
                "git_apply": sandbox_apply.check_result("PASS", "apply ok"),
                "resulting_file_hashes": [
                    {"path": "canary/example.py", "resulting_blob_sha": "6" * 40},
                ],
                "diff_binding": {
                    "status": "PASS",
                    "message": "old detailed shape",
                    "expected_paths": ["canary/example.py"],
                },
                "sandbox_cleanup": sandbox_apply.check_result("PASS", "cleanup ok"),
            }
        )
        with self.assertRaises(sandbox_apply.fix.FixProposalFailure):
            sandbox_apply.validate_apply_result_against_schema(result, self.schema_path())

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

    def test_post_apply_rejection_preserves_executed_step_state(self):
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
            patch_text = "diff --git a/canary/example.py b/canary/example.py\n"
            patch_text += "--- a/canary/example.py\n"
            patch_text += "+++ b/canary/example.py\n"
            patch_text += "@@ -1 +1 @@\n"
            patch_text += "-return False\n"
            patch_text += "+return True\n"
            context = self.apply_context(head_sha=head, patch_text=patch_text)
            context_dir = root / "context"
            output_dir = root / "out"
            context_dir.mkdir()
            sandbox_apply.write_json_file(
                context_dir / sandbox_apply.APPLY_CONTEXT_FILE,
                context,
            )
            old_env = os.environ.copy()
            old_validate_final_head = sandbox_apply.validate_final_head
            old_verify_changed_files = sandbox_apply.verify_changed_files
            old_github_output = sandbox_apply.github_output
            old_write_job_summary = sandbox_apply.write_job_summary
            try:
                os.environ.update(
                    {
                        "APPLY_CONTEXT_DIR": str(context_dir),
                        "APPLY_RESULT_DIR": str(output_dir),
                        "SANDBOX_WORKTREE": str(repo),
                        "PATCH_FILE": str(root / "namma-fix.patch"),
                        "SANDBOX_RESULT_SCHEMA": str(self.schema_path()),
                        "GITHUB_REPOSITORY": sandbox_apply.EXPECTED_REPOSITORY,
                        "GITHUB_TOKEN": "dummy-token",
                    }
                )

                def fail_after_apply(*, worktree, context):
                    raise sandbox_apply.ApplyStatus(
                        sandbox_apply.RESULT_STATUS_PATCH_REJECTED,
                        "DIFF_BINDING_MISMATCH",
                        "forced diff binding failure",
                    )

                sandbox_apply.validate_final_head = lambda **_: None
                sandbox_apply.verify_changed_files = fail_after_apply
                sandbox_apply.github_output = lambda values: None
                sandbox_apply.write_job_summary = lambda text: None
                self.assertEqual(0, sandbox_apply.command_apply(None))
            finally:
                sandbox_apply.validate_final_head = old_validate_final_head
                sandbox_apply.verify_changed_files = old_verify_changed_files
                sandbox_apply.github_output = old_github_output
                sandbox_apply.write_job_summary = old_write_job_summary
                os.environ.clear()
                os.environ.update(old_env)
            result = sandbox_apply.read_json_file(output_dir / "sandbox-validation-result.json")
            self.assertEqual(sandbox_apply.RESULT_STATUS_PATCH_REJECTED, result["status"])
            self.assertEqual("DIFF_BINDING_MISMATCH", result["failure_code"])
            self.assertTrue(result["patch_check_performed"])
            self.assertTrue(result["patch_applied"])
            self.assertTrue(result["sandbox_worktree_modified"])
            self.assertEqual("PASS", result["git_apply_check"]["status"])
            self.assertEqual("PASS", result["git_apply"]["status"])
            self.assertEqual("FAIL", result["diff_binding"]["status"])
            self.assertFalse(result["test_execution_performed"])
            self.assertTrue(result["sandbox_destroyed"])

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
