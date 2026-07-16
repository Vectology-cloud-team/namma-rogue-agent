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
    def collector_text(self):
        return check_architect_review_workflow.COLLECTOR_WORKFLOW_PATH.read_text(
            encoding="utf-8"
        )

    def reviewer_text(self):
        return check_architect_review_workflow.REVIEWER_WORKFLOW_PATH.read_text(
            encoding="utf-8"
        )

    def failed_labels(self, results):
        return {result.label for result in results if not result.passed}

    def test_repository_workflows_pass_static_checks(self):
        results = check_architect_review_workflow.run_checks()
        self.assertEqual(set(), self.failed_labels(results))

    def test_collector_has_no_secrets_reference(self):
        labels = self.failed_labels(
            check_architect_review_workflow.check_collector_text(self.collector_text())
        )
        self.assertNotIn("collector has no secrets references", labels)
        self.assertNotIn("collector has no OpenAI API key", labels)

    def test_collector_has_no_codex_action(self):
        labels = self.failed_labels(
            check_architect_review_workflow.check_collector_text(self.collector_text())
        )
        self.assertNotIn("collector does not run Codex action", labels)

    def test_collector_has_no_write_permission(self):
        labels = self.failed_labels(
            check_architect_review_workflow.check_collector_text(self.collector_text())
        )
        self.assertNotIn("collector has no write permission", labels)
        self.assertIn("permissions:\n      contents: read", self.collector_text())

    def test_reviewer_only_references_openai_api_key(self):
        self.assertNotIn("OPENAI_API_KEY", self.collector_text())
        self.assertIn("OPENAI_API_KEY", self.reviewer_text())

    def test_reviewer_uses_workflow_run_trigger(self):
        labels = self.failed_labels(
            check_architect_review_workflow.check_reviewer_text(self.reviewer_text())
        )
        self.assertNotIn("reviewer uses workflow_run trigger", labels)
        self.assertNotIn("reviewer watches collector workflow", labels)

    def test_reviewer_checks_collector_workflow_name(self):
        reviewer = self.reviewer_text().replace(
            "github.event.workflow_run.name == 'Architect Review Collect'",
            "true",
        )
        labels = self.failed_labels(
            check_architect_review_workflow.check_reviewer_text(reviewer)
        )
        self.assertIn("reviewer checks workflow name", labels)

    def test_reviewer_checks_source_event_type(self):
        reviewer = self.reviewer_text().replace(
            "github.event.workflow_run.event == 'pull_request'",
            "true",
        )
        labels = self.failed_labels(
            check_architect_review_workflow.check_reviewer_text(reviewer)
        )
        self.assertIn("reviewer checks source event type", labels)

    def test_reviewer_checks_repository_identity(self):
        reviewer = self.reviewer_text().replace(
            "github.event.workflow_run.repository.full_name == github.repository",
            "true",
        )
        reviewer = reviewer.replace(
            "github.repository == 'Vectology-cloud-team/namma-rogue-agent'",
            "true",
        )
        labels = self.failed_labels(
            check_architect_review_workflow.check_reviewer_text(reviewer)
        )
        self.assertIn("reviewer checks workflow repository", labels)
        self.assertIn("reviewer checks expected repository", labels)

    def test_reviewer_validates_manifest_schema(self):
        script = check_architect_review_workflow.load_text(
            check_architect_review_workflow.REPO_ROOT
            / "scripts"
            / "architect_review_retry.py"
        )
        self.assertIn("EXPECTED_MANIFEST_KEYS", script)
        self.assertIn("schema_version", script)

    def test_reviewer_checks_current_pr_head_sha(self):
        script = check_architect_review_workflow.load_text(
            check_architect_review_workflow.REPO_ROOT
            / "scripts"
            / "architect_review_retry.py"
        )
        self.assertIn('manifest["head_sha"] != pull["head"]["sha"]', script)
        self.assertIn('manifest["base_sha"] != pull["base"]["sha"]', script)
        self.assertIn("validate_live_pr_files", script)
        self.assertIn("application/vnd.github.v3.diff", script)
        self.assertIn("STALE_ARTIFACT", script)

    def test_github_script_rejects_injected_identifier_redeclaration(self):
        for identifier in ("core", "github", "context"):
            for declaration in ("const", "let", "var"):
                with self.subTest(identifier=identifier, declaration=declaration):
                    reviewer = self.reviewer_text().replace(
                        "python3 reviewer-control/scripts/architect_review_retry.py "
                        "validate-review-input",
                        f"{declaration} {identifier} = null;\n"
                        "          python3 reviewer-control/scripts/"
                        "architect_review_retry.py validate-review-input",
                    )
                    labels = self.failed_labels(
                        check_architect_review_workflow.check_reviewer_text(reviewer)
                    )
                    self.assertIn(
                        "github-script does not redeclare injected identifiers",
                        labels,
                    )

    def test_stale_artifact_skips_comment(self):
        reviewer = self.reviewer_text()
        labels = self.failed_labels(
            check_architect_review_workflow.check_reviewer_text(reviewer)
        )
        self.assertNotIn("reviewer skips stale artifact without comment", labels)
        self.assertIn("needs.review.outputs.should_review == 'true'", reviewer)
        self.assertIn("needs.review.result == 'success'", reviewer)

    def test_artifact_size_limit_exists(self):
        collector_labels = self.failed_labels(
            check_architect_review_workflow.check_collector_text(self.collector_text())
        )
        reviewer_labels = self.failed_labels(
            check_architect_review_workflow.check_reviewer_text(self.reviewer_text())
        )
        self.assertNotIn("collector has max artifact bytes", collector_labels)
        self.assertNotIn("reviewer validates artifact size", reviewer_labels)

    def test_pr_strings_are_not_embedded_directly_in_shell(self):
        collector_labels = self.failed_labels(
            check_architect_review_workflow.check_collector_text(self.collector_text())
        )
        self.assertNotIn("collector does not shell-expand PR title", collector_labels)
        self.assertNotIn("github.event.pull_request.title", self.collector_text())

    def test_trusted_prompt_missing_fails_closed(self):
        reviewer = self.reviewer_text().replace(
            "architect_review_retry.py verify-prompt",
            "echo Using pull request prompt fallback.",
        )
        labels = self.failed_labels(
            check_architect_review_workflow.check_reviewer_text(reviewer)
        )
        self.assertIn("trusted prompt is verified", labels)

    def test_sticky_comment_is_one_per_pr(self):
        script = check_architect_review_workflow.load_text(
            check_architect_review_workflow.REPO_ROOT
            / "scripts"
            / "architect_review_retry.py"
        )
        self.assertIn("COMMENT_MARKER in comment", script)
        self.assertNotIn("reviewedSha", script)

    def test_existing_marker_comment_is_updated(self):
        script = check_architect_review_workflow.load_text(
            check_architect_review_workflow.REPO_ROOT
            / "scripts"
            / "architect_review_retry.py"
        )
        self.assertIn("/issues/comments/{existing['id']}", script)

    def test_missing_marker_comment_is_created(self):
        script = check_architect_review_workflow.load_text(
            check_architect_review_workflow.REPO_ROOT
            / "scripts"
            / "architect_review_retry.py"
        )
        self.assertIn("/issues/{issue_number}/comments", script)

    def test_all_actions_are_full_sha_pinned(self):
        combined = check_architect_review_workflow.all_workflow_text(
            self.collector_text(),
            self.reviewer_text(),
        )
        labels = self.failed_labels(
            check_architect_review_workflow.check_action_pinning(combined)
        )
        self.assertNotIn("all actions use full commit SHAs", labels)
        self.assertNotIn("only allowed actions are used", labels)

    def test_mutable_action_tag_is_rejected(self):
        combined = check_architect_review_workflow.all_workflow_text(
            self.collector_text(),
            self.reviewer_text(),
        ).replace(
            "actions/checkout@93cb6efe18208431cddfb8368fd83d5badbf9bfd # v5",
            "actions/checkout@v5",
        )
        labels = self.failed_labels(
            check_architect_review_workflow.check_action_pinning(combined)
        )
        self.assertIn("all actions use full commit SHAs", labels)
        self.assertIn("actions/checkout is pinned to reviewed SHA", labels)

    def test_unapproved_action_is_rejected(self):
        combined = check_architect_review_workflow.all_workflow_text(
            self.collector_text(),
            self.reviewer_text(),
        ).replace(
            "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02 # v4",
            "unknown/example@1111111111111111111111111111111111111111 # v1",
        )
        labels = self.failed_labels(
            check_architect_review_workflow.check_action_pinning(combined)
        )
        self.assertIn("only allowed actions are used", labels)
        self.assertIn("actions/upload-artifact action is used", labels)

    def test_prompt_requires_untrusted_diff_boundary(self):
        prompt = check_architect_review_workflow.PROMPT_PATH.read_text(
            encoding="utf-8"
        )
        labels = self.failed_labels(
            check_architect_review_workflow.check_prompt_text(prompt)
        )
        self.assertNotIn("prompt treats review input as untrusted", labels)
        self.assertNotIn("prompt forbids executing PR content", labels)


if __name__ == "__main__":
    unittest.main()
