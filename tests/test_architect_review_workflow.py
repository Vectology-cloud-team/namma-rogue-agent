from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "check_architect_review_workflow.py"
)
SPEC = importlib.util.spec_from_file_location(
    "check_architect_review_workflow",
    SCRIPT_PATH,
)
check_architect_review_workflow = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = check_architect_review_workflow
SPEC.loader.exec_module(check_architect_review_workflow)


class ArchitectReviewWorkflowTests(unittest.TestCase):
    def failed_labels(self, results):
        return {result.label for result in results if not result.passed}

    def test_repository_workflow_passes_static_checks(self):
        results = check_architect_review_workflow.run_checks()
        self.assertEqual(set(), self.failed_labels(results))

    def test_pull_request_target_is_rejected(self):
        workflow = check_architect_review_workflow.WORKFLOW_PATH.read_text(
            encoding="utf-8"
        )
        workflow = workflow.replace("pull_request:", "pull_request_target:")
        labels = self.failed_labels(
            check_architect_review_workflow.check_workflow_text(workflow)
        )
        self.assertIn("does not use pull_request_target", labels)

    def test_dangerous_codex_permission_profile_is_rejected(self):
        workflow = check_architect_review_workflow.WORKFLOW_PATH.read_text(
            encoding="utf-8"
        )
        workflow = workflow.replace(
            'permission-profile: ":read-only"',
            "permission-profile: danger-full-access",
        )
        labels = self.failed_labels(
            check_architect_review_workflow.check_workflow_text(workflow)
        )
        self.assertIn("uses read-only permission profile", labels)
        self.assertIn("does not use danger-full-access", labels)

    def test_workspace_write_permission_profile_is_rejected(self):
        workflow = check_architect_review_workflow.WORKFLOW_PATH.read_text(
            encoding="utf-8"
        )
        workflow = workflow.replace(
            'permission-profile: ":read-only"',
            "permission-profile: workspace-write",
        )
        labels = self.failed_labels(
            check_architect_review_workflow.check_workflow_text(workflow)
        )
        self.assertIn("uses read-only permission profile", labels)
        self.assertIn("does not use workspace-write", labels)

    def test_post_feedback_openai_key_is_rejected(self):
        workflow = check_architect_review_workflow.WORKFLOW_PATH.read_text(
            encoding="utf-8"
        )
        workflow = workflow.replace(
            "    permissions:\n      issues: write\n      pull-requests: write\n",
            "    permissions:\n      issues: write\n      pull-requests: write\n"
            "    env:\n      OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}\n",
        )
        labels = self.failed_labels(
            check_architect_review_workflow.check_workflow_text(workflow)
        )
        self.assertIn("post_feedback has no OpenAI API key", labels)

    def test_checkout_credential_persistence_is_rejected(self):
        workflow = check_architect_review_workflow.WORKFLOW_PATH.read_text(
            encoding="utf-8"
        )
        workflow = workflow.replace(
            "persist-credentials: false",
            "persist-credentials: true",
        )
        labels = self.failed_labels(
            check_architect_review_workflow.check_workflow_text(workflow)
        )
        self.assertIn("checkout does not persist credentials", labels)

    def test_explicit_model_and_effort_are_rejected_for_stage1(self):
        workflow = check_architect_review_workflow.WORKFLOW_PATH.read_text(
            encoding="utf-8"
        )
        workflow = workflow.replace(
            "safety-strategy: drop-sudo",
            "safety-strategy: drop-sudo\n          model: gpt-test\n"
            "          effort: high",
        )
        labels = self.failed_labels(
            check_architect_review_workflow.check_workflow_text(workflow)
        )
        self.assertIn("does not set explicit model", labels)
        self.assertIn("does not set explicit effort", labels)

    def test_prompt_requires_verdict_and_sections(self):
        prompt = check_architect_review_workflow.PROMPT_PATH.read_text(
            encoding="utf-8"
        )
        results = check_architect_review_workflow.check_prompt_text(prompt)
        self.assertEqual(set(), self.failed_labels(results))


if __name__ == "__main__":
    unittest.main()
