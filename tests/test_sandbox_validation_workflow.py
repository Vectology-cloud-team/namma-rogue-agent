from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "check_sandbox_validation_workflow.py"
)
SPEC = importlib.util.spec_from_file_location(
    "check_sandbox_validation_workflow",
    SCRIPT_PATH,
)
check_sandbox_validation_workflow = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = check_sandbox_validation_workflow
SPEC.loader.exec_module(check_sandbox_validation_workflow)


class SandboxValidationWorkflowTests(unittest.TestCase):
    def failed_labels(self, results):
        return {result.label for result in results if not result.passed}

    def collector_text(self):
        return check_sandbox_validation_workflow.COLLECTOR_PATH.read_text(
            encoding="utf-8"
        )

    def validator_text(self):
        return check_sandbox_validation_workflow.VALIDATOR_PATH.read_text(
            encoding="utf-8"
        )

    def test_repository_sandbox_workflows_pass_static_checks(self):
        self.assertEqual(
            set(),
            self.failed_labels(check_sandbox_validation_workflow.run_checks()),
        )

    def test_collector_is_label_only_and_read_only(self):
        labels = self.failed_labels(
            check_sandbox_validation_workflow.check_collector(self.collector_text())
        )
        self.assertNotIn("sandbox collector requires validate label", labels)
        self.assertNotIn("sandbox collector rejects fork PRs", labels)
        self.assertNotIn("sandbox collector has no write permission", labels)
        self.assertNotIn("sandbox collector has no secrets", labels)
        self.assertNotIn("sandbox collector does not run Codex", labels)

    def test_validator_is_workflow_run_and_read_only(self):
        labels = self.failed_labels(
            check_sandbox_validation_workflow.check_validator(self.validator_text())
        )
        self.assertNotIn("sandbox validator uses workflow_run trigger", labels)
        self.assertNotIn("sandbox validator watches collector", labels)
        self.assertNotIn("preflight job has no write permission", labels)
        self.assertNotIn("preflight job has no OPENAI_API_KEY", labels)
        self.assertNotIn("preflight job has no checkout action", labels)

    def test_live_gate_and_actor_permission_checks_are_present(self):
        labels = self.failed_labels(
            check_sandbox_validation_workflow.check_validator(self.validator_text())
        )
        self.assertNotIn("sandbox script requires live three-label gate", labels)
        self.assertNotIn("sandbox script rechecks actor repository permission", labels)
        self.assertNotIn("sandbox script only allows admin maintain", labels)
        self.assertNotIn("sandbox script performs double head check", labels)

    def test_blob_patch_and_test_preflight_checks_are_present(self):
        labels = self.failed_labels(
            check_sandbox_validation_workflow.check_validator(self.validator_text())
        )
        self.assertNotIn("sandbox script verifies target blob metadata", labels)
        self.assertNotIn("sandbox script validates patch metadata only", labels)
        self.assertNotIn("sandbox script validates trusted test IDs", labels)

    def test_post_job_is_the_only_comment_writer(self):
        labels = self.failed_labels(
            check_sandbox_validation_workflow.check_validator(self.validator_text())
        )
        self.assertNotIn("post job can write issue comments", labels)
        self.assertNotIn("post job can write pull request sticky comments", labels)
        self.assertNotIn("post job has no contents write", labels)
        self.assertNotIn("post job downloads result before comment", labels)

    def test_forbidden_runtime_actions_are_rejected(self):
        text = self.validator_text() + "\nrun: git apply proposal.patch\n"
        labels = self.failed_labels(
            check_sandbox_validation_workflow.check_forbidden_automation(text)
        )
        self.assertIn("sandbox workflows do not contain git apply", labels)

    def test_contents_write_is_rejected(self):
        text = self.validator_text().replace("contents: read", "contents: write", 1)
        labels = self.failed_labels(
            check_sandbox_validation_workflow.check_forbidden_automation(text)
        )
        self.assertIn("sandbox workflows do not contain contents: write", labels)

    def test_actions_are_full_sha_pinned(self):
        text = self.validator_text().replace(
            "actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093 # v4",
            "actions/download-artifact@v4",
        )
        labels = self.failed_labels(
            check_sandbox_validation_workflow.check_action_pinning(text)
        )
        self.assertIn("all sandbox workflow actions use full commit SHAs", labels)

    def test_schema_and_policy_contracts_are_present(self):
        labels = self.failed_labels(
            check_sandbox_validation_workflow.check_schema_and_policy()
        )
        self.assertEqual(set(), labels)


if __name__ == "__main__":
    unittest.main()
