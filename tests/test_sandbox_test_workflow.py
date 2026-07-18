from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_sandbox_test_workflow.py"
SPEC = importlib.util.spec_from_file_location(
    "check_sandbox_test_workflow",
    SCRIPT_PATH,
)
check_sandbox_test_workflow = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = check_sandbox_test_workflow
SPEC.loader.exec_module(check_sandbox_test_workflow)


class SandboxTestWorkflowCheckerTests(unittest.TestCase):
    def test_policy_command_modules_are_discovered(self) -> None:
        policy = (
            REPO_ROOT
            / ".github"
            / "codex"
            / "sandbox-test-policy.yml"
        ).read_text(encoding="utf-8")
        self.assertEqual(
            {
                "unit_tests",
                "stage2c_targeted_tests",
                "workflow_checker_tests",
                "compileall_checks",
                "stage2c_b1_clamp_tests",
            },
            check_sandbox_test_workflow.sandbox_test_command_modules(policy),
        )

    def test_workflow_downloads_all_trusted_support_modules(self) -> None:
        policy = (
            REPO_ROOT
            / ".github"
            / "codex"
            / "sandbox-test-policy.yml"
        ).read_text(encoding="utf-8")
        workflow = (
            REPO_ROOT
            / ".github"
            / "workflows"
            / "fix-sandbox-test.yml"
        ).read_text(encoding="utf-8")
        for module in check_sandbox_test_workflow.sandbox_test_command_modules(policy):
            with self.subTest(module=module):
                self.assertIn(
                    f"scripts/sandbox_test_support/{module}.py",
                    workflow,
                )
        self.assertIn(
            "scripts/sandbox_test_support/support_paths.py",
            workflow,
        )


if __name__ == "__main__":
    unittest.main()
