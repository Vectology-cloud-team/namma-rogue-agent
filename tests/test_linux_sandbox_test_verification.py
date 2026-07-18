from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "linux_sandbox_test_verification.py"
CHECKER_PATH = REPO_ROOT / "scripts" / "check_linux_sandbox_test_verification_workflow.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


linux_verification = load_module("linux_sandbox_test_verification", SCRIPT_PATH)
linux_checker = load_module(
    "check_linux_sandbox_test_verification_workflow",
    CHECKER_PATH,
)


class LinuxSandboxTestVerificationTests(unittest.TestCase):
    def test_policy_commands_are_parsed(self) -> None:
        commands = linux_verification.parse_command_policy(
            REPO_ROOT / ".github" / "codex" / "sandbox-test-policy.yml"
        )
        self.assertEqual(
            ("python3", "-m", "unittest", "stage2c_b1_clamp_tests"),
            commands["stage2c-b1-clamp"],
        )
        self.assertEqual(
            {
                "unit",
                "stage2c-targeted",
                "workflow-checkers",
                "compileall",
                "stage2c-b1-clamp",
            },
            set(commands),
        )

    def test_fix_policy_test_ids_match_sandbox_policy(self) -> None:
        fix_ids = linux_verification.parse_fix_policy_ids(
            REPO_ROOT / ".github" / "codex" / "fix-policy.yml"
        )
        commands = linux_verification.parse_command_policy(
            REPO_ROOT / ".github" / "codex" / "sandbox-test-policy.yml"
        )
        self.assertEqual(set(fix_ids), set(commands))

    def test_windows_python3_skip_tests_are_identified_from_source(self) -> None:
        skipped = linux_verification.source_python3_skip_tests(
            REPO_ROOT / "tests" / "test_sandbox_test.py"
        )
        self.assertEqual(
            [
                "tests.test_sandbox_test.SandboxTestTests."
                "test_approved_unittest_command_passes_against_trusted_support",
                "tests.test_sandbox_test.SandboxTestTests."
                "test_approved_unittest_command_reports_failure",
                "tests.test_sandbox_test.SandboxTestTests."
                "test_worktree_cannot_shadow_trusted_support_test_module",
            ],
            skipped,
        )

    def test_parse_unittest_output_records_skips_and_counts(self) -> None:
        command = linux_verification.CommandResult(
            argv=("python3", "-m", "unittest"),
            returncode=0,
            output="\n".join(
                [
                    "test_ok (tests.sample.SampleTests.test_ok) ... ok",
                    "test_skip (tests.sample.SampleTests.test_skip) ... "
                    "skipped 'set ROGUE_BINARY to run the Rogue launch test'",
                    "",
                    "----------------------------------------------------------------------",
                    "Ran 2 tests in 0.001s",
                    "",
                    "OK (skipped=1)",
                    "",
                ]
            ),
            log_path="sample.log",
        )
        parsed = linux_verification.parse_unittest_output(command)
        self.assertEqual(2, parsed["run"])
        self.assertEqual(1, parsed["passed"])
        self.assertEqual(1, parsed["skipped"])
        self.assertEqual(
            [
                {
                    "test": "tests.sample.SampleTests.test_skip",
                    "reason": "set ROGUE_BINARY to run the Rogue launch test",
                }
            ],
            parsed["skipped_tests"],
        )

    def test_skip_classification_recovers_python3_skips(self) -> None:
        expected = ["tests.test_sandbox_test.SandboxTestTests.test_shadow"]
        full = {
            "successes": expected,
            "skipped_tests": [
                {
                    "test": "tests.test_rogue_launch.RogueLaunchTest.test_launch",
                    "reason": "set ROGUE_BINARY to run the Rogue launch test",
                }
            ],
        }
        targeted = {"successes": [], "skipped_tests": []}
        info = linux_verification.classify_skips(full, targeted, expected)
        self.assertEqual(expected, info["windows_python3_skips_recovered"])
        self.assertEqual([], info["unexpected_linux_skips"])

    def test_policy_summary_matches_download_list(self) -> None:
        summary = linux_verification.trusted_policy_summary()
        self.assertTrue(summary["policy_download_list_match"])
        self.assertEqual([], summary["missing_commands"])
        self.assertEqual([], summary["missing_downloads"])
        self.assertEqual([], summary["orphan_downloads"])
        self.assertEqual(
            ["python3", "-m", "unittest", "stage2c_b1_clamp_tests"],
            summary["stage2c_b1_clamp_argv"],
        )

    def test_status_is_verified_when_linux_recovers_python3_skips(self) -> None:
        expected = [
            "tests.test_sandbox_test.SandboxTestTests."
            "test_worktree_cannot_shadow_trusted_support_test_module"
        ]
        full = {
            "returncode": 0,
            "successes": expected,
            "skipped_tests": [
                {
                    "test": "tests.test_rogue_launch.RogueLaunchTest.test_launch",
                    "reason": "set ROGUE_BINARY to run the Rogue launch test",
                }
            ],
        }
        full.update({"failures": 0, "errors": 0})
        targeted = {"returncode": 0, "successes": [], "skipped_tests": []}
        policy = linux_verification.trusted_policy_summary()
        skip_info = {
            "windows_python3_skips_identified": expected,
            "windows_python3_skips_recovered": expected,
            "unexpected_linux_skips": [],
        }
        self.assertEqual(
            "VERIFIED",
            linux_verification.determine_status(
                env={"python3_path": "/usr/bin/python3"},
                full=full,
                targeted=targeted,
                skip_info=skip_info,
                policy=policy,
            ),
        )

    def test_status_rejects_unexpected_linux_skip(self) -> None:
        policy = linux_verification.trusted_policy_summary()
        status = linux_verification.determine_status(
            env={"python3_path": "/usr/bin/python3"},
            full={"returncode": 0, "successes": [], "skipped_tests": []},
            targeted={"returncode": 0, "successes": [], "skipped_tests": []},
            skip_info={
                "windows_python3_skips_identified": [],
                "windows_python3_skips_recovered": [],
                "unexpected_linux_skips": [
                    {"test": "tests.x.Test.test_y", "reason": "unexpected"}
                ],
            },
            policy=policy,
        )
        self.assertEqual("UNEXPECTED_SKIP", status)

    def test_checker_passes_current_workflow(self) -> None:
        failed = [result for result in linux_checker.run_checks() if not result.passed]
        self.assertEqual([], failed)

    def test_workflow_uses_read_only_permissions(self) -> None:
        workflow = (
            REPO_ROOT
            / ".github"
            / "workflows"
            / "trusted-sandbox-test-linux-verification.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("contents: read", workflow)
        self.assertNotIn(": write", workflow)

    def test_script_writes_required_artifact_files_when_python3_missing(self) -> None:
        current = linux_verification.shutil.which
        try:
            linux_verification.shutil.which = lambda name: None
            with tempfile.TemporaryDirectory() as tmp:
                code = linux_verification.run_verification(Path(tmp))
                self.assertEqual(1, code)
                self.assertTrue((Path(tmp) / "environment.txt").is_file())
                self.assertTrue(
                    (Path(tmp) / "linux-verification-summary.json").is_file()
                )
        finally:
            linux_verification.shutil.which = current


if __name__ == "__main__":
    unittest.main()
