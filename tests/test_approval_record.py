from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
import urllib.error
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
            "labels": labels if labels is not None else [
                "ai-fix-proposal",
                "ai-fix-approved",
            ],
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
        labels = labels if labels is not None else [
            "ai-fix-proposal",
            "ai-fix-approved",
        ]
        return {
            "labels": [
                {
                    "name": label,
                }
                for label in labels
            ],
        }

    def proposal(
        self,
        *,
        proposal_hash=PROPOSAL_HASH,
        head_sha=HEAD_SHA,
        repository=None,
        pull_request_number=17,
        policy_hash=None,
    ):
        policy_hash = policy_hash or self.policy().policy_hash
        repository = repository or approval_record.EXPECTED_REPOSITORY
        return {
            "schema_version": "1.0",
            "proposal_id": proposal_hash[:32],
            "repository": repository,
            "pull_request_number": pull_request_number,
            "base_sha": BASE_SHA,
            "head_sha": head_sha,
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

    def metadata(
        self,
        *,
        status="PROPOSAL_READY",
        proposal_hash=PROPOSAL_HASH,
        head_sha=HEAD_SHA,
        repository=None,
        pull_request_number=17,
        policy_hash=None,
    ):
        policy_hash = policy_hash or self.policy().policy_hash
        repository = repository or approval_record.EXPECTED_REPOSITORY
        return {
            "schema_version": "fix-proposal-metadata-v1",
            "status": status,
            "proposal_id": proposal_hash[:32],
            "proposal_hash": proposal_hash,
            "proposal_input_hash": "e" * 64,
            "repository": repository,
            "pull_request_number": pull_request_number,
            "base_sha": BASE_SHA,
            "head_sha": head_sha,
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

    def write_candidate_artifact(
        self,
        output_dir,
        *,
        proposal=None,
        metadata=None,
    ):
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "fix-proposal.json").write_text(
            json.dumps(proposal or self.proposal(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (output_dir / "proposal-metadata.json").write_text(
            json.dumps(metadata or self.metadata(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def github_json_side_effect(self, *, runs, artifacts_by_run):
        def github_json(method, path, token):
            del method, token
            if "/actions/workflows/fix-proposal.yml/runs" in path:
                return {"workflow_runs": runs}, {}
            if "/actions/runs/" in path and path.endswith("/artifacts?per_page=100"):
                run_id = path.split("/actions/runs/", 1)[1].split("/", 1)[0]
                return {"artifacts": artifacts_by_run.get(run_id, [])}, {}
            raise AssertionError(f"unexpected GitHub path: {path}")

        return github_json

    def find_proposal_with_mocks(self, *, runs, artifacts_by_run, download):
        with tempfile.TemporaryDirectory() as temporary:
            output_dir = Path(temporary)
            with (
                mock.patch.object(
                    approval_record.stage1,
                    "github_json",
                    side_effect=self.github_json_side_effect(
                        runs=runs,
                        artifacts_by_run=artifacts_by_run,
                    ),
                ),
                mock.patch.object(
                    approval_record.fix,
                    "download_artifact_by_name",
                    side_effect=download,
                ),
            ):
                return approval_record.find_latest_proposal_artifact(
                    repo=approval_record.EXPECTED_REPOSITORY,
                    token="token",
                    manifest=self.manifest(),
                    policy=self.policy(),
                    output_dir=output_dir,
                    max_bytes=1000,
                )

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
            approval_actor="shinoda",
            approval_actor_association="MEMBER",
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
            approval_actor="shinoda",
            approval_actor_association="MEMBER",
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
            approval_actor="shinoda",
            approval_actor_association="MEMBER",
        )

    def test_proposal_label_missing_is_rejected(self):
        self.assert_failure_code(
            approval_record.fix.FailureCode.LABEL_MISSING,
            approval_record.validate_approval_gate,
            manifest=self.manifest(labels=["ai-fix-approved"]),
            live_pull=self.live_pull(),
            live_issue=self.live_issue(labels=["ai-fix-approved"]),
            policy=self.policy(),
            approval_actor="shinoda",
            approval_actor_association="MEMBER",
        )

    def test_collaborator_approval_actor_is_rejected(self):
        self.assert_failure_code(
            approval_record.fix.FailureCode.UNAUTHORIZED_ASSOCIATION,
            approval_record.validate_approval_gate,
            manifest=self.manifest(),
            live_pull=self.live_pull(),
            live_issue=self.live_issue(),
            policy=self.policy(),
            approval_actor="shinoda",
            approval_actor_association="COLLABORATOR",
        )

    def test_spoofed_manifest_actor_is_rejected(self):
        manifest = self.manifest()
        manifest["actor"] = "organization-owner"
        self.assert_failure_code(
            approval_record.fix.FailureCode.TRUST_BOUNDARY_VIOLATION,
            approval_record.validate_approval_gate,
            manifest=manifest,
            live_pull=self.live_pull(),
            live_issue=self.live_issue(),
            policy=self.policy(),
            approval_actor="labeler-member",
            approval_actor_association="MEMBER",
        )

    def test_pr_author_association_is_not_used_as_label_actor_association(self):
        manifest = self.manifest()
        manifest["author_association"] = "COLLABORATOR"
        approval_record.validate_approval_gate(
            manifest=manifest,
            live_pull=self.live_pull(),
            live_issue=self.live_issue(),
            policy=self.policy(),
            approval_actor="shinoda",
            approval_actor_association="MEMBER",
        )

    def test_approval_record_uses_trusted_approval_actor(self):
        manifest = self.manifest()
        record = approval_record.build_approval_record(
            manifest=manifest,
            proposal=self.proposal(),
            metadata=self.metadata(),
            approved_by="trusted-labeler",
            approved_at="2026-07-17T00:02:00Z",
        )
        self.assertEqual("trusted-labeler", record["approved_by"])

    def test_approval_label_alone_does_not_create_record_without_proposal_artifact(self):
        with mock.patch.object(
            approval_record.stage1,
            "github_json",
            return_value=({"workflow_runs": []}, {}),
        ):
            self.assert_failure_code(
                approval_record.fix.FailureCode.PROPOSAL_ARTIFACT_NOT_FOUND,
                approval_record.find_latest_proposal_artifact,
                repo=approval_record.EXPECTED_REPOSITORY,
                token="token",
                manifest=self.manifest(),
                policy=self.policy(),
                output_dir=Path("unused"),
                max_bytes=1000,
            )

    def test_latest_missing_proposal_artifact_skips_to_next_valid_candidate(self):
        calls = []

        def download(**kwargs):
            calls.append(kwargs["artifact_name"])
            if kwargs["artifact_name"] == "fix-proposal-missing":
                raise approval_record.fix.retryable(
                    approval_record.fix.FailureCode.ARTIFACT_TRANSIENT_ERROR,
                    "artifact fix-proposal-missing was not available yet",
                    "artifact_download",
                )
            self.write_candidate_artifact(kwargs["target_dir"])
            return 42

        proposal, metadata, artifact_id = self.find_proposal_with_mocks(
            runs=[
                {"id": 20, "conclusion": "success", "created_at": "2026-07-17T00:02:00Z"},
                {"id": 10, "conclusion": "success", "created_at": "2026-07-17T00:01:00Z"},
            ],
            artifacts_by_run={
                "20": [{"name": "fix-proposal-missing"}],
                "10": [{"name": "fix-proposal-valid"}],
            },
            download=download,
        )
        self.assertEqual(["fix-proposal-missing", "fix-proposal-valid"], calls)
        self.assertEqual(PROPOSAL_ID, proposal["proposal_id"])
        self.assertEqual(PROPOSAL_HASH, metadata["proposal_hash"])
        self.assertEqual(42, artifact_id)

    def test_latest_expired_proposal_artifact_skips_to_next_valid_candidate(self):
        calls = []

        def download(**kwargs):
            calls.append(kwargs["artifact_name"])
            if kwargs["artifact_name"] == "fix-proposal-expired":
                raise urllib.error.HTTPError(
                    url="https://api.github.com/artifacts/1/zip",
                    code=404,
                    msg="Not Found",
                    hdrs={},
                    fp=None,
                )
            self.write_candidate_artifact(kwargs["target_dir"])
            return 43

        _, metadata, artifact_id = self.find_proposal_with_mocks(
            runs=[
                {"id": 30, "conclusion": "success", "created_at": "2026-07-17T00:03:00Z"},
                {"id": 20, "conclusion": "success", "created_at": "2026-07-17T00:02:00Z"},
            ],
            artifacts_by_run={
                "30": [{"name": "fix-proposal-expired"}],
                "20": [{"name": "fix-proposal-valid"}],
            },
            download=download,
        )
        self.assertEqual(["fix-proposal-expired", "fix-proposal-valid"], calls)
        self.assertEqual(PROPOSAL_HASH, metadata["proposal_hash"])
        self.assertEqual(43, artifact_id)

    def test_all_missing_proposal_artifacts_report_not_found(self):
        def download(**kwargs):
            raise approval_record.fix.retryable(
                approval_record.fix.FailureCode.ARTIFACT_TRANSIENT_ERROR,
                f"artifact {kwargs['artifact_name']} was not available yet",
                "artifact_download",
            )

        self.assert_failure_code(
            approval_record.fix.FailureCode.PROPOSAL_ARTIFACT_NOT_FOUND,
            self.find_proposal_with_mocks,
            runs=[
                {"id": 30, "conclusion": "success", "created_at": "2026-07-17T00:03:00Z"},
                {"id": 20, "conclusion": "success", "created_at": "2026-07-17T00:02:00Z"},
            ],
            artifacts_by_run={
                "30": [{"name": "fix-proposal-missing-a"}],
                "20": [{"name": "fix-proposal-missing-b"}],
            },
            download=download,
        )

    def test_proposal_hash_mismatch_after_download_fails_without_fallback(self):
        calls = []

        def download(**kwargs):
            calls.append(kwargs["artifact_name"])
            if kwargs["artifact_name"] == "fix-proposal-bad-hash":
                self.write_candidate_artifact(
                    kwargs["target_dir"],
                    proposal=self.proposal(),
                    metadata=self.metadata(proposal_hash="0" * 64),
                )
                return 44
            self.write_candidate_artifact(kwargs["target_dir"])
            return 45

        self.assert_failure_code(
            approval_record.fix.FailureCode.INVALID_PROPOSAL,
            self.find_proposal_with_mocks,
            runs=[
                {"id": 40, "conclusion": "success", "created_at": "2026-07-17T00:04:00Z"},
                {"id": 30, "conclusion": "success", "created_at": "2026-07-17T00:03:00Z"},
            ],
            artifacts_by_run={
                "40": [{"name": "fix-proposal-bad-hash"}],
                "30": [{"name": "fix-proposal-valid"}],
            },
            download=download,
        )
        self.assertEqual(["fix-proposal-bad-hash"], calls)

    def test_head_mismatch_after_download_fails_without_fallback(self):
        calls = []

        def download(**kwargs):
            calls.append(kwargs["artifact_name"])
            if kwargs["artifact_name"] == "fix-proposal-stale-head":
                stale_head = "1" * 40
                self.write_candidate_artifact(
                    kwargs["target_dir"],
                    proposal=self.proposal(head_sha=stale_head),
                    metadata=self.metadata(head_sha=stale_head),
                )
                return 46
            self.write_candidate_artifact(kwargs["target_dir"])
            return 47

        self.assert_failure_code(
            approval_record.fix.FailureCode.SHA_MISMATCH,
            self.find_proposal_with_mocks,
            runs=[
                {"id": 50, "conclusion": "success", "created_at": "2026-07-17T00:05:00Z"},
                {"id": 40, "conclusion": "success", "created_at": "2026-07-17T00:04:00Z"},
            ],
            artifacts_by_run={
                "50": [{"name": "fix-proposal-stale-head"}],
                "40": [{"name": "fix-proposal-valid"}],
            },
            download=download,
        )
        self.assertEqual(["fix-proposal-stale-head"], calls)

    def test_latest_valid_matching_proposal_is_selected(self):
        latest_hash = "1" * 64

        def download(**kwargs):
            if kwargs["artifact_name"] == "fix-proposal-latest":
                self.write_candidate_artifact(
                    kwargs["target_dir"],
                    proposal=self.proposal(proposal_hash=latest_hash),
                    metadata=self.metadata(proposal_hash=latest_hash),
                )
                return 48
            self.write_candidate_artifact(kwargs["target_dir"])
            return 49

        proposal, metadata, artifact_id = self.find_proposal_with_mocks(
            runs=[
                {"id": 60, "conclusion": "success", "created_at": "2026-07-17T00:06:00Z"},
                {"id": 50, "conclusion": "success", "created_at": "2026-07-17T00:05:00Z"},
            ],
            artifacts_by_run={
                "50": [{"name": "fix-proposal-older"}],
                "60": [{"name": "fix-proposal-latest"}],
            },
            download=download,
        )
        self.assertEqual(latest_hash[:32], proposal["proposal_id"])
        self.assertEqual(latest_hash, metadata["proposal_hash"])
        self.assertEqual(48, artifact_id)

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
