from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "approval_record.py"
REPO_ROOT = SCRIPT_PATH.parents[1]
SCRIPTS_DIR = SCRIPT_PATH.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
SPEC = importlib.util.spec_from_file_location("approval_record", SCRIPT_PATH)
approval_record = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = approval_record
SPEC.loader.exec_module(approval_record)


BASE_SHA = "a" * 40
HEAD_SHA = "b" * 40
PROPOSAL_HASH = "c" * 64
PROPOSAL_ID = PROPOSAL_HASH[:32]
ORIGINAL_BLOB_SHA = "d" * 40


class ApprovalRecordTests(unittest.TestCase):
    def policy(self):
        return approval_record.fix.load_fix_proposal_policy(
            REPO_ROOT / ".github" / "codex" / "fix-policy.yml"
        )

    def manifest(self, *, labels=None, head_sha=HEAD_SHA, event_label="ai-fix-approved"):
        return {
            "schema_version": "fix-approval-request-v1",
            "repository": approval_record.EXPECTED_REPOSITORY,
            "pull_request_number": 17,
            "base_sha": BASE_SHA,
            "head_sha": head_sha,
            "actor": "shinoda",
            "author_association": "MEMBER",
            "draft": False,
            "base_repository": approval_record.EXPECTED_REPOSITORY,
            "head_repository": approval_record.EXPECTED_REPOSITORY,
            "labels": labels if labels is not None else ["ai-fix-approved"],
            "event_action": "labeled",
            "event_label": event_label,
            "collector_workflow_name": approval_record.COLLECTOR_WORKFLOW_NAME,
            "collector_workflow_run_id": 123,
        }

    def live_pull(self, *, head_sha=HEAD_SHA):
        return {
            "number": 17,
            "draft": False,
            "head": {
                "sha": head_sha,
            },
            "base": {
                "sha": BASE_SHA,
            },
            "user": {
                "type": "User",
            },
        }

    def live_issue(self, *, labels=None):
        labels = labels if labels is not None else ["ai-fix-approved"]
        return {
            "labels": [
                {
                    "name": label,
                }
                for label in labels
            ],
        }

    def proposal(self):
        policy_hash = self.policy().policy_hash
        return {
            "schema_version": "1.0",
            "proposal_id": PROPOSAL_ID,
            "repository": approval_record.EXPECTED_REPOSITORY,
            "pull_request_number": 17,
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
            "summary": "Fix the canary clamp bounds.",
            "findings_addressed": [
                {
                    "finding_id": "finding-canary",
                    "severity": "high",
                    "category": "correctness",
                }
            ],
            "changes": [
                {
                    "path": "canary/example.py",
                    "operation": "modify",
                    "original_blob_sha": ORIGINAL_BLOB_SHA,
                    "patch": "\n".join(
                        [
                            "diff --git a/canary/example.py b/canary/example.py",
                            "--- a/canary/example.py",
                            "+++ b/canary/example.py",
                            "@@ -1 +1 @@",
                            "-return False",
                            "+return True",
                        ]
                    ),
                    "rationale": "Correct the boolean result.",
                }
            ],
            "tests_recommended": [
                "python -m unittest tests/test_stage2a_canary.py",
            ],
            "risks": [
                "Low risk canary-only change.",
            ],
            "human_approval_required": True,
        }

    def metadata(self, *, status="PROPOSAL_READY", policy_hash=None):
        policy_hash = policy_hash or self.policy().policy_hash
        return {
            "schema_version": "fix-proposal-metadata-v1",
            "status": status,
            "proposal_id": PROPOSAL_ID,
            "proposal_hash": PROPOSAL_HASH,
            "proposal_input_hash": "e" * 64,
            "repository": approval_record.EXPECTED_REPOSITORY,
            "pull_request_number": 17,
            "base_sha": BASE_SHA,
            "head_sha": HEAD_SHA,
            "policy_hash": policy_hash,
            "schema_id": "fix-proposal.schema.json",
            "generator_model": "gpt-5.5",
            "reasoning_effort": "medium",
            "generated_at": "2026-07-17T00:01:00Z",
            "source_review_run_id": 456,
            "source_review_artifact_id": "architect-review-result-456",
            "source_review_hash": "f" * 64,
        }

    def assert_failure_code(self, expected_code, func, *args, **kwargs):
        with self.assertRaises(approval_record.fix.FixProposalFailure) as caught:
            func(*args, **kwargs)
        self.assertEqual(expected_code, caught.exception.code)

    def test_approval_record_normal_generation(self):
        policy = self.policy()
        manifest = self.manifest()
        proposal = self.proposal()
        metadata = self.metadata()
        approval_record.validate_approval_gate(
            manifest=manifest,
            live_pull=self.live_pull(),
            live_issue=self.live_issue(),
            policy=policy,
        )
        approval_record.validate_proposal_for_approval(
            manifest=manifest,
            proposal=proposal,
            metadata=metadata,
            policy=policy,
        )
        record = approval_record.build_approval_record(
            manifest=manifest,
            proposal=proposal,
            metadata=metadata,
            approved_at="2026-07-17T00:02:00Z",
        )
        self.assertEqual("APPROVED", record["status"])
        self.assertEqual(PROPOSAL_ID, record["proposal_id"])
        self.assertEqual(PROPOSAL_HASH, record["proposal_hash"])
        approval_record.validate_approval_record_shape(record)

    def test_proposal_hash_mismatch_is_rejected(self):
        proposal = self.proposal()
        proposal["proposal_id"] = "0" * 32
        self.assert_failure_code(
            approval_record.fix.FailureCode.INVALID_PROPOSAL,
            approval_record.validate_proposal_for_approval,
            manifest=self.manifest(),
            proposal=proposal,
            metadata=self.metadata(),
            policy=self.policy(),
        )

    def test_head_mismatch_is_rejected(self):
        self.assert_failure_code(
            approval_record.fix.FailureCode.SHA_MISMATCH,
            approval_record.validate_approval_gate,
            manifest=self.manifest(),
            live_pull=self.live_pull(head_sha="1" * 40),
            live_issue=self.live_issue(),
            policy=self.policy(),
        )

    def test_stale_proposal_is_rejected(self):
        self.assert_failure_code(
            approval_record.fix.FailureCode.STALE_ARTIFACT,
            approval_record.validate_proposal_for_approval,
            manifest=self.manifest(),
            proposal=self.proposal(),
            metadata=self.metadata(status="STALE"),
            policy=self.policy(),
        )

    def test_label_missing_is_rejected(self):
        self.assert_failure_code(
            approval_record.fix.FailureCode.LABEL_MISSING,
            approval_record.validate_approval_gate,
            manifest=self.manifest(labels=[]),
            live_pull=self.live_pull(),
            live_issue=self.live_issue(labels=[]),
            policy=self.policy(),
        )

    def test_approval_label_alone_does_not_create_record_without_proposal_artifact(self):
        with mock.patch.object(
            approval_record.stage1,
            "github_json",
            return_value=({"workflow_runs": []}, {}),
        ):
            self.assert_failure_code(
                approval_record.fix.FailureCode.REVIEW_NOT_READY,
                approval_record.find_latest_proposal_artifact,
                repo=approval_record.EXPECTED_REPOSITORY,
                token="token",
                pr_number=17,
                head_sha=HEAD_SHA,
                output_dir=Path("unused"),
                max_bytes=1000,
            )

    def test_policy_hash_mismatch_is_rejected(self):
        self.assert_failure_code(
            approval_record.fix.FailureCode.TRUST_BOUNDARY_VIOLATION,
            approval_record.validate_proposal_for_approval,
            manifest=self.manifest(),
            proposal=self.proposal(),
            metadata=self.metadata(policy_hash="0" * 64),
            policy=self.policy(),
        )

    def test_proposal_id_mismatch_is_rejected(self):
        metadata = self.metadata()
        metadata["proposal_id"] = "0" * 32
        self.assert_failure_code(
            approval_record.fix.FailureCode.INVALID_PROPOSAL,
            approval_record.validate_proposal_for_approval,
            manifest=self.manifest(),
            proposal=self.proposal(),
            metadata=metadata,
            policy=self.policy(),
        )

    def test_approval_id_is_deterministic(self):
        kwargs = {
            "manifest": self.manifest(),
            "proposal": self.proposal(),
            "metadata": self.metadata(),
            "approved_at": "2026-07-17T00:02:00Z",
        }
        first = approval_record.build_approval_record(**kwargs)
        second = approval_record.build_approval_record(**kwargs)
        self.assertEqual(first["approval_id"], second["approval_id"])

    def test_repository_change_automation_is_absent(self):
        script = SCRIPT_PATH.read_text(encoding="utf-8").lower()
        for token in (
            "subprocess",
            "os.system",
            "git push",
            "git merge",
            "createcommitonbranch",
            "createpullrequest",
        ):
            self.assertNotIn(token, script)

    def test_approval_comment_contains_no_repository_change_claim(self):
        record = approval_record.build_approval_record(
            manifest=self.manifest(),
            proposal=self.proposal(),
            metadata=self.metadata(),
            approved_at="2026-07-17T00:02:00Z",
        )
        body = approval_record.approval_comment_body(
            record=record,
            workflow_run_id="123",
            repo=approval_record.EXPECTED_REPOSITORY,
        )
        self.assertIn("Human Approval Recorded", body)
        self.assertIn("Repository変更なし", body)
        self.assertIn("Commitなし", body)
        self.assertIn("Pushなし", body)
        self.assertIn("Mergeなし", body)


if __name__ == "__main__":
    unittest.main()
