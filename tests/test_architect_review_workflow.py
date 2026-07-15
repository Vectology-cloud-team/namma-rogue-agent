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

    def test_pr_prompt_is_not_used_as_review_prompt(self):
        workflow = check_architect_review_workflow.WORKFLOW_PATH.read_text(
            encoding="utf-8"
        )
        labels = self.failed_labels(
            check_architect_review_workflow.check_workflow_text(workflow)
        )
        self.assertNotIn("uses trusted base prompt file", labels)
        self.assertNotIn("does not use PR prompt as prompt-file", labels)
        self.assertIn(
            "prompt-file: ${{ github.workspace }}/trusted-base/.github/codex/prompts/architect-review.md",
            workflow,
        )
        self.assertNotIn(
            "prompt-file: .github/codex/prompts/architect-review.md",
            workflow,
        )

    def test_missing_base_prompt_fail_closed_check_is_required(self):
        workflow = check_architect_review_workflow.WORKFLOW_PATH.read_text(
            encoding="utf-8"
        )
        workflow = workflow.replace(
            "Trusted architect-review prompt is missing from the base SHA.",
            "Prompt missing; using PR copy.",
        )
        labels = self.failed_labels(
            check_architect_review_workflow.check_workflow_text(workflow)
        )
        self.assertIn("trusted prompt is verified", labels)

    def test_mutable_action_tag_is_rejected(self):
        workflow = check_architect_review_workflow.WORKFLOW_PATH.read_text(
            encoding="utf-8"
        )
        workflow = workflow.replace(
            "actions/checkout@93cb6efe18208431cddfb8368fd83d5badbf9bfd # v5",
            "actions/checkout@v5",
        )
        labels = self.failed_labels(
            check_architect_review_workflow.check_workflow_text(workflow)
        )
        self.assertIn("all actions use full commit SHAs", labels)
        self.assertIn("actions/checkout is pinned to reviewed SHA", labels)

    def test_unapproved_action_is_rejected(self):
        workflow = check_architect_review_workflow.WORKFLOW_PATH.read_text(
            encoding="utf-8"
        )
        workflow = workflow.replace(
            "actions/github-script@f28e40c7f34bde8b3046d885e986cb6290c5673b # v7",
            "third-party/example@1111111111111111111111111111111111111111 # v1",
        )
        labels = self.failed_labels(
            check_architect_review_workflow.check_workflow_text(workflow)
        )
        self.assertIn("only allowed actions are used", labels)
        self.assertIn("actions/github-script action is used", labels)

    def test_missing_action_version_comment_is_rejected(self):
        workflow = check_architect_review_workflow.WORKFLOW_PATH.read_text(
            encoding="utf-8"
        )
        workflow = workflow.replace(
            "openai/codex-action@52fe01ec70a42f454c9d2ebd47598f9fd6893d56 # v1",
            "openai/codex-action@52fe01ec70a42f454c9d2ebd47598f9fd6893d56",
        )
        labels = self.failed_labels(
            check_architect_review_workflow.check_workflow_text(workflow)
        )
        self.assertIn("openai/codex-action keeps version comment", labels)

    def test_same_pr_different_head_sha_uses_sticky_comment(self):
        workflow = check_architect_review_workflow.WORKFLOW_PATH.read_text(
            encoding="utf-8"
        )
        post_job = check_architect_review_workflow._job_section(
            workflow,
            "post_feedback",
        )
        existing_block = check_architect_review_workflow.existing_comment_block(
            post_job
        )
        self.assertIn("comment.body.includes(marker)", existing_block)
        self.assertNotIn("reviewedSha", existing_block)
        self.assertNotIn("Reviewed commit", existing_block)

    def test_existing_marker_comment_is_updated(self):
        workflow = check_architect_review_workflow.WORKFLOW_PATH.read_text(
            encoding="utf-8"
        )
        labels = self.failed_labels(
            check_architect_review_workflow.check_workflow_text(workflow)
        )
        self.assertNotIn("deduplicates by marker", labels)
        self.assertNotIn("sticky comment ignores reviewed SHA for matching", labels)
        self.assertIn("github.rest.issues.updateComment", workflow)

    def test_missing_marker_comment_is_created(self):
        workflow = check_architect_review_workflow.WORKFLOW_PATH.read_text(
            encoding="utf-8"
        )
        self.assertIn("github.rest.issues.createComment", workflow)

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
