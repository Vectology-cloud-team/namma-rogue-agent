from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "check_fix_proposal_workflow.py"
)
SPEC = importlib.util.spec_from_file_location(
    "check_fix_proposal_workflow",
    SCRIPT_PATH,
)
check_fix_proposal_workflow = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = check_fix_proposal_workflow
SPEC.loader.exec_module(check_fix_proposal_workflow)


class FixProposalWorkflowTests(unittest.TestCase):
    def failed_labels(self, results):
        return {result.label for result in results if not result.passed}

    def collector_text(self):
        return check_fix_proposal_workflow.COLLECTOR_PATH.read_text(encoding="utf-8")

    def generator_text(self):
        return check_fix_proposal_workflow.GENERATOR_PATH.read_text(encoding="utf-8")

    def test_repository_stage2a_workflows_pass_static_checks(self):
        self.assertEqual(
            set(),
            self.failed_labels(check_fix_proposal_workflow.run_checks()),
        )

    def test_workflow_files_include_yml_and_yaml(self):
        paths = check_fix_proposal_workflow.workflow_files()
        self.assertIn(check_fix_proposal_workflow.COLLECTOR_PATH, paths)
        self.assertIn(check_fix_proposal_workflow.GENERATOR_PATH, paths)
        self.assertTrue(
            all(path.suffix in {".yml", ".yaml"} for path in paths)
        )

    def test_collector_has_no_secrets_or_write_permissions(self):
        labels = self.failed_labels(
            check_fix_proposal_workflow.check_collector(self.collector_text())
        )
        self.assertNotIn("collector has no secrets", labels)
        self.assertNotIn("collector has no OPENAI_API_KEY", labels)
        self.assertNotIn("collector has no write permission", labels)

    def test_collector_has_no_codex_action_or_repo_script(self):
        labels = self.failed_labels(
            check_fix_proposal_workflow.check_collector(self.collector_text())
        )
        self.assertNotIn("collector does not run Codex", labels)
        self.assertNotIn("collector does not run repository scripts", labels)

    def test_generator_is_workflow_run_only(self):
        labels = self.failed_labels(
            check_fix_proposal_workflow.check_generator(self.generator_text())
        )
        self.assertNotIn("generator uses workflow_run trigger", labels)
        self.assertNotIn("generator watches collector", labels)
        self.assertNotIn("generator has no workflow_dispatch", labels)

    def test_generator_only_references_openai_api_key(self):
        self.assertNotIn("OPENAI_API_KEY", self.collector_text())
        self.assertIn("OPENAI_API_KEY", self.generator_text())

    def test_generator_verifies_gate_before_codex(self):
        labels = self.failed_labels(
            check_fix_proposal_workflow.check_generator(self.generator_text())
        )
        self.assertNotIn("gate runs before Codex", labels)
        self.assertNotIn("Codex only runs when gate passes", labels)

    def test_generator_comments_only_for_verified_proposal(self):
        text = self.generator_text()
        self.assertIn(
            "should_comment: ${{ steps.finalize_proposal.outputs.proposal_ready == 'true' }}",
            text,
        )
        self.assertNotIn("steps.prepare.outputs.should_generate != 'true'", text)

    def test_generator_passes_trusted_target_contents_to_codex_and_finalize(self):
        text = self.generator_text()
        self.assertIn("TRUSTED_TARGET_CONTENTS:", text)
        self.assertIn("target-file-contents.json", text)
        self.assertIn("TRUSTED_TARGET_CONTENTS_PATH:", text)

    def test_all_actions_are_full_sha_pinned(self):
        combined = "\n".join(
            path.read_text(encoding="utf-8")
            for path in check_fix_proposal_workflow.workflow_files()
        )
        labels = self.failed_labels(
            check_fix_proposal_workflow.check_action_pinning(combined)
        )
        self.assertNotIn("all workflow actions use full commit SHAs", labels)
        self.assertNotIn("only allowed actions are used", labels)

    def test_mutable_action_is_rejected(self):
        combined = "\n".join(
            path.read_text(encoding="utf-8")
            for path in check_fix_proposal_workflow.workflow_files()
        ).replace(
            "openai/codex-action@52fe01ec70a42f454c9d2ebd47598f9fd6893d56 # v1",
            "openai/codex-action@v1",
        )
        labels = self.failed_labels(
            check_fix_proposal_workflow.check_action_pinning(combined)
        )
        self.assertIn("all workflow actions use full commit SHAs", labels)

    def test_forbidden_automation_is_rejected(self):
        text = self.generator_text() + "\nrun: git push origin main\n"
        labels = self.failed_labels(
            check_fix_proposal_workflow.check_forbidden_automation(text)
        )
        self.assertIn("workflow does not contain git push", labels)

    def test_contents_write_is_rejected(self):
        text = self.generator_text().replace("contents: read", "contents: write", 1)
        labels = self.failed_labels(
            check_fix_proposal_workflow.check_forbidden_automation(text)
        )
        self.assertIn("workflow does not contain contents: write", labels)

    def test_policy_prompt_and_schema_contracts(self):
        labels = self.failed_labels(
            check_fix_proposal_workflow.check_policy_prompt_and_schema()
        )
        self.assertEqual(set(), labels)

    def test_fix_proposal_marker_is_separate_from_stage1_marker(self):
        script = check_fix_proposal_workflow.SCRIPT_PATH.read_text(encoding="utf-8")
        self.assertIn("<!-- namma-ai-fix-proposal -->", script)
        self.assertNotIn("<!-- namma-ai-architect-review -->", script)

    def test_no_stage2b_or_stage2c_workflow(self):
        combined = "\n".join(
            path.read_text(encoding="utf-8")
            for path in check_fix_proposal_workflow.workflow_files()
        )
        self.assertNotIn("Stage 2B", combined)
        self.assertNotIn("Stage 2C", combined)


if __name__ == "__main__":
    unittest.main()
