from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "check_approval_workflow.py"
)
SPEC = importlib.util.spec_from_file_location(
    "check_approval_workflow",
    SCRIPT_PATH,
)
check_approval_workflow = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = check_approval_workflow
SPEC.loader.exec_module(check_approval_workflow)


class ApprovalWorkflowTests(unittest.TestCase):
    def failed_labels(self, results):
        return {result.label for result in results if not result.passed}

    def collector_text(self):
        return check_approval_workflow.COLLECTOR_PATH.read_text(encoding="utf-8")

    def recorder_text(self):
        return check_approval_workflow.RECORDER_PATH.read_text(encoding="utf-8")

    def test_repository_approval_workflows_pass_static_checks(self):
        self.assertEqual(
            set(),
            self.failed_labels(check_approval_workflow.run_checks()),
        )

    def test_collector_has_no_secrets_or_write_permissions(self):
        labels = self.failed_labels(
            check_approval_workflow.check_collector(self.collector_text())
        )
        self.assertNotIn("approval collector has no secrets", labels)
        self.assertNotIn("approval collector has no OPENAI_API_KEY", labels)
        self.assertNotIn("approval collector has no write permission", labels)

    def test_collector_does_not_run_codex_or_repo_scripts(self):
        labels = self.failed_labels(
            check_approval_workflow.check_collector(self.collector_text())
        )
        self.assertNotIn("approval collector does not run Codex", labels)
        self.assertNotIn("approval collector does not run repository scripts", labels)

    def test_collector_only_runs_on_labeled_pull_request_events(self):
        labels = self.failed_labels(
            check_approval_workflow.check_collector(self.collector_text())
        )
        self.assertNotIn("approval collector listens for labeled", labels)
        self.assertNotIn("approval collector does not listen for synchronize", labels)
        self.assertNotIn("approval collector does not listen for reopened", labels)
        self.assertNotIn("approval collector does not listen for ready_for_review", labels)

    def test_recorder_is_workflow_run_only(self):
        labels = self.failed_labels(
            check_approval_workflow.check_recorder(self.recorder_text())
        )
        self.assertNotIn("approval recorder uses workflow_run trigger", labels)
        self.assertNotIn("approval recorder watches collector", labels)
        self.assertNotIn("approval recorder has no workflow_dispatch", labels)

    def test_recorder_does_not_use_openai_key(self):
        combined = self.collector_text() + self.recorder_text()
        self.assertNotIn("OPENAI_API_KEY", combined)

    def test_record_job_has_no_write_permission(self):
        labels = self.failed_labels(
            check_approval_workflow.check_recorder(self.recorder_text())
        )
        self.assertNotIn("record job has no write permission", labels)

    def test_record_job_uses_trusted_workflow_actor(self):
        labels = self.failed_labels(
            check_approval_workflow.check_recorder(self.recorder_text())
        )
        self.assertNotIn("record job binds approval actor from workflow_run", labels)
        self.assertNotIn("approval rejects manifest actor spoofing", labels)

    def test_post_job_has_comment_permission_only(self):
        labels = self.failed_labels(
            check_approval_workflow.check_recorder(self.recorder_text())
        )
        self.assertNotIn("post job can write issue comments", labels)
        self.assertNotIn("post job can write pull request comments", labels)
        self.assertNotIn("post job has no contents write", labels)

    def test_proposal_workflow_cannot_write_approval_record(self):
        labels = self.failed_labels(
            check_approval_workflow.check_schema_and_scripts()
        )
        self.assertNotIn("proposal workflow cannot write approval record", labels)
        self.assertNotIn("proposal workflow cannot write approval marker", labels)
        self.assertNotIn("approval schema records approver association", labels)

    def test_all_actions_are_full_sha_pinned(self):
        combined = "\n".join(
            path.read_text(encoding="utf-8")
            for path in check_approval_workflow.workflow_files()
        )
        labels = self.failed_labels(
            check_approval_workflow.check_action_pinning(combined)
        )
        self.assertNotIn("all workflow actions use full commit SHAs", labels)
        self.assertNotIn("only allowed actions are used", labels)

    def test_mutable_action_is_rejected(self):
        combined = "\n".join(
            path.read_text(encoding="utf-8")
            for path in check_approval_workflow.workflow_files()
        ).replace(
            "actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093 # v4",
            "actions/download-artifact@v4",
        )
        labels = self.failed_labels(
            check_approval_workflow.check_action_pinning(combined)
        )
        self.assertIn("all workflow actions use full commit SHAs", labels)

    def test_forbidden_workflow_permissions_are_rejected(self):
        text = self.recorder_text().replace("contents: read", "contents: write", 1)
        labels = self.failed_labels(
            check_approval_workflow.check_forbidden_automation(text)
        )
        self.assertIn("approval workflows do not contain contents: write", labels)

    def test_merge_automation_is_rejected(self):
        text = self.recorder_text() + "\nrun: gh pr merge 21\n"
        labels = self.failed_labels(
            check_approval_workflow.check_forbidden_automation(text)
        )
        self.assertIn("approval workflows do not contain gh pr merge", labels)

    def test_issue_comments_are_used_instead_of_review_api(self):
        labels = self.failed_labels(
            check_approval_workflow.check_recorder(self.recorder_text())
        )
        self.assertNotIn("approval uses issue comment list endpoint", labels)
        self.assertNotIn("approval uses issue comment create endpoint", labels)
        self.assertNotIn("approval uses issue comment update endpoint", labels)
        self.assertNotIn("approval does not use PR review API", labels)
        self.assertNotIn("approval validates actor membership", labels)

    def test_validated_artifact_is_downloaded_before_comment(self):
        labels = self.failed_labels(
            check_approval_workflow.check_recorder(self.recorder_text())
        )
        self.assertNotIn("post job downloads record artifact before comment", labels)


if __name__ == "__main__":
    unittest.main()
