from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import approval_record  # noqa: E402
import check_stage_label_triggers as trigger_check  # noqa: E402
import fix_proposal_generator  # noqa: E402
import sandbox_validation  # noqa: E402


BASE_SHA = "a" * 40
HEAD_SHA = "b" * 40
EXPECTED_REPOSITORY = "Vectology-cloud-team/namma-rogue-agent"


def proposal_manifest() -> dict[str, object]:
    return {
        "schema_version": "fix-proposal-request-v1",
        "request_stage": "FIX_PROPOSAL_REQUEST",
        "repository": EXPECTED_REPOSITORY,
        "pull_request_number": 30,
        "base_sha": BASE_SHA,
        "head_sha": HEAD_SHA,
        "actor": "shinoda",
        "author_association": "MEMBER",
        "draft": False,
        "base_repository": EXPECTED_REPOSITORY,
        "head_repository": EXPECTED_REPOSITORY,
        "labels": ["ai-fix-proposal"],
        "event_action": "labeled",
        "event_name": "pull_request",
        "event_label": "ai-fix-proposal",
        "collector_workflow_name": "Fix Proposal Request Collect",
        "collector_workflow_run_id": 100,
    }


def approval_manifest() -> dict[str, object]:
    return {
        "schema_version": "fix-approval-request-v1",
        "request_stage": "FIX_APPROVAL_REQUEST",
        "repository": EXPECTED_REPOSITORY,
        "pull_request_number": 30,
        "base_sha": BASE_SHA,
        "head_sha": HEAD_SHA,
        "actor": "shinoda",
        "author_association": "MEMBER",
        "draft": False,
        "base_repository": EXPECTED_REPOSITORY,
        "head_repository": EXPECTED_REPOSITORY,
        "labels": ["ai-fix-proposal", "ai-fix-approved"],
        "event_action": "labeled",
        "event_name": "pull_request",
        "event_label": "ai-fix-approved",
        "collector_workflow_name": "Fix Approval Request Collect",
        "collector_workflow_run_id": 200,
    }


def sandbox_manifest() -> dict[str, object]:
    return {
        "schema_version": "sandbox-validation-request-v1",
        "request_stage": "SANDBOX_VALIDATION_REQUEST",
        "repository": EXPECTED_REPOSITORY,
        "pull_request_number": 30,
        "base_sha": BASE_SHA,
        "head_sha": HEAD_SHA,
        "actor": "shinoda",
        "author_association": "MEMBER",
        "draft": False,
        "base_repository": EXPECTED_REPOSITORY,
        "head_repository": EXPECTED_REPOSITORY,
        "labels": ["ai-fix-proposal", "ai-fix-approved", "ai-fix-validate"],
        "event_action": "labeled",
        "event_name": "pull_request",
        "event_label": "ai-fix-validate",
        "collector_workflow_name": "Sandbox Validation Request Collector",
        "collector_workflow_run_id": 300,
        "requested_at": "2026-07-18T00:00:00Z",
    }


class StageLabelTriggerTests(unittest.TestCase):
    def assert_matrix(self, stage_key: str, expected_label: str) -> None:
        spec = trigger_check.STAGES[stage_key]
        cases = [
            ("labeled", expected_label, True),
            ("labeled", "ai-fix-proposal", expected_label == "ai-fix-proposal"),
            ("labeled", "ai-fix-approved", expected_label == "ai-fix-approved"),
            ("labeled", "ai-fix-validate", expected_label == "ai-fix-validate"),
            ("labeled", "other-label", False),
            ("unlabeled", expected_label, False),
            ("synchronize", None, False),
        ]
        for action, label, expected in cases:
            with self.subTest(stage=stage_key, action=action, label=label):
                self.assertIs(
                    trigger_check.collector_processes_event(
                        spec,
                        event_name="pull_request",
                        action=action,
                        label=label,
                    ),
                    expected,
                )

    def test_stage2a_collector_event_matrix(self):
        self.assert_matrix("stage2a", "ai-fix-proposal")

    def test_stage2b_collector_event_matrix(self):
        self.assert_matrix("stage2b", "ai-fix-approved")

    def test_stage2c_collector_event_matrix(self):
        self.assert_matrix("stage2c", "ai-fix-validate")

    def test_label_removal_and_synchronize_do_not_process_any_collector(self):
        for spec in trigger_check.STAGES.values():
            with self.subTest(stage=spec.name):
                self.assertFalse(
                    trigger_check.collector_processes_event(
                        spec,
                        event_name="pull_request",
                        action="unlabeled",
                        label=spec.label,
                    )
                )
                self.assertFalse(
                    trigger_check.collector_processes_event(
                        spec,
                        event_name="pull_request",
                        action="synchronize",
                        label=None,
                    )
                )

    def test_static_checker_passes_repository_workflows(self):
        failed = [result for result in trigger_check.run_checks() if not result.passed]
        self.assertEqual([], failed)

    def test_stage2a_validator_rejects_stage2b_collector_artifact(self):
        manifest = proposal_manifest()
        manifest["request_stage"] = "FIX_APPROVAL_REQUEST"
        manifest["event_label"] = "ai-fix-approved"
        manifest["collector_workflow_name"] = "Fix Approval Request Collect"
        with self.assertRaises(fix_proposal_generator.FixProposalFailure):
            fix_proposal_generator.validate_request_manifest_shape(manifest)

    def test_stage2a_validator_rejects_stage2c_collector_artifact(self):
        manifest = proposal_manifest()
        manifest["request_stage"] = "SANDBOX_VALIDATION_REQUEST"
        manifest["event_label"] = "ai-fix-validate"
        manifest["collector_workflow_name"] = "Sandbox Validation Request Collector"
        with self.assertRaises(fix_proposal_generator.FixProposalFailure):
            fix_proposal_generator.validate_request_manifest_shape(manifest)

    def test_stage2b_recorder_rejects_stage2a_collector_artifact(self):
        manifest = approval_manifest()
        manifest["request_stage"] = "FIX_PROPOSAL_REQUEST"
        manifest["event_label"] = "ai-fix-proposal"
        manifest["collector_workflow_name"] = "Fix Proposal Request Collect"
        with self.assertRaises(approval_record.fix.FixProposalFailure):
            approval_record.validate_request_manifest_shape(manifest)

    def test_stage2b_recorder_rejects_stage2c_collector_artifact(self):
        manifest = approval_manifest()
        manifest["request_stage"] = "SANDBOX_VALIDATION_REQUEST"
        manifest["event_label"] = "ai-fix-validate"
        manifest["collector_workflow_name"] = "Sandbox Validation Request Collector"
        with self.assertRaises(approval_record.fix.FixProposalFailure):
            approval_record.validate_request_manifest_shape(manifest)

    def test_stage2c_validator_rejects_stage2a_collector_artifact(self):
        manifest = sandbox_manifest()
        manifest["request_stage"] = "FIX_PROPOSAL_REQUEST"
        manifest["event_label"] = "ai-fix-proposal"
        manifest["collector_workflow_name"] = "Fix Proposal Request Collect"
        with self.assertRaises(sandbox_validation.fix.FixProposalFailure):
            sandbox_validation.validate_request_manifest_shape(manifest)

    def test_stage2c_validator_rejects_stage2b_collector_artifact(self):
        manifest = sandbox_manifest()
        manifest["request_stage"] = "FIX_APPROVAL_REQUEST"
        manifest["event_label"] = "ai-fix-approved"
        manifest["collector_workflow_name"] = "Fix Approval Request Collect"
        with self.assertRaises(sandbox_validation.fix.FixProposalFailure):
            sandbox_validation.validate_request_manifest_shape(manifest)

    def test_spoofed_manifest_stage_is_rejected(self):
        for manifest, validator, exception_type in (
            (
                proposal_manifest(),
                fix_proposal_generator.validate_request_manifest_shape,
                fix_proposal_generator.FixProposalFailure,
            ),
            (
                approval_manifest(),
                approval_record.validate_request_manifest_shape,
                approval_record.fix.FixProposalFailure,
            ),
            (
                sandbox_manifest(),
                sandbox_validation.validate_request_manifest_shape,
                sandbox_validation.fix.FixProposalFailure,
            ),
        ):
            with self.subTest(schema=manifest["schema_version"]):
                manifest["request_stage"] = "SPOOFED_STAGE"
                with self.assertRaises(exception_type):
                    validator(manifest)

    def test_mismatched_workflow_provenance_is_rejected(self):
        for manifest, validator, exception_type in (
            (
                proposal_manifest(),
                fix_proposal_generator.validate_request_manifest_shape,
                fix_proposal_generator.FixProposalFailure,
            ),
            (
                approval_manifest(),
                approval_record.validate_request_manifest_shape,
                approval_record.fix.FixProposalFailure,
            ),
            (
                sandbox_manifest(),
                sandbox_validation.validate_request_manifest_shape,
                sandbox_validation.fix.FixProposalFailure,
            ),
        ):
            with self.subTest(schema=manifest["schema_version"]):
                manifest["collector_workflow_name"] = "Almost Matching Collector"
                with self.assertRaises(exception_type):
                    validator(manifest)


if __name__ == "__main__":
    unittest.main()
