from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
SCRIPT_PATH = SCRIPTS_DIR / "check_sandbox_apply_workflow.py"
SPEC = importlib.util.spec_from_file_location("check_sandbox_apply_workflow", SCRIPT_PATH)
check_sandbox_apply_workflow = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = check_sandbox_apply_workflow
SPEC.loader.exec_module(check_sandbox_apply_workflow)


class SandboxApplyWorkflowTests(unittest.TestCase):
    def test_static_checker_passes(self):
        failed = [
            result
            for result in check_sandbox_apply_workflow.run_checks()
            if not result.passed
        ]
        self.assertEqual([], failed)

    def test_apply_collector_uses_only_apply_label(self):
        text = check_sandbox_apply_workflow.load_text(
            check_sandbox_apply_workflow.COLLECTOR_PATH
        )
        self.assertIn("github.event.action == 'labeled'", text)
        self.assertIn("github.event.label.name == 'ai-fix-apply-sandbox'", text)
        self.assertNotIn("github.event.label.name == 'ai-fix-validate'", text)
        self.assertNotIn("- synchronize", text)

    def test_apply_workflow_uses_exact_sha_checkout_without_credentials(self):
        text = check_sandbox_apply_workflow.load_text(
            check_sandbox_apply_workflow.APPLY_PATH
        )
        self.assertIn("ref: ${{ steps.prepare.outputs.head_sha }}", text)
        self.assertIn("persist-credentials: false", text)
        self.assertIn("submodules: false", text)
        self.assertIn("lfs: false", text)

    def test_only_comment_job_has_write_permission(self):
        text = check_sandbox_apply_workflow.load_text(
            check_sandbox_apply_workflow.APPLY_PATH
        )
        apply_job = check_sandbox_apply_workflow.job_section(text, "sandbox_apply")
        post_job = check_sandbox_apply_workflow.job_section(text, "post_sandbox_apply")
        self.assertNotIn(": write", apply_job)
        self.assertIn("issues: write", post_job)
        self.assertIn("pull-requests: write", post_job)
        self.assertNotIn("contents: write", post_job)


if __name__ == "__main__":
    unittest.main()
