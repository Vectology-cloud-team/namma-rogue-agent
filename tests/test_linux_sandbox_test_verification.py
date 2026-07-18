from __future__ import annotations

import importlib.util
import subprocess
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

    def test_policy_duplicate_command_ids_are_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            policy = Path(tmp) / "sandbox-test-policy.yml"
            policy.write_text(
                "\n".join(
                    [
                        "commands:",
                        "  unit: python3|-m|unittest|unit_tests",
                        "  unit: python3|-m|unittest|other_tests",
                        "  compileall: python3|-m|unittest|compileall_checks",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            self.assertEqual(
                ("unit",),
                linux_verification.parse_command_policy_duplicate_ids(policy),
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

    def test_run_command_writes_completed_process_stdout(self) -> None:
        current = linux_verification.subprocess.run
        captured: dict[str, object] = {}

        def fake_run(*args, **kwargs):
            captured["cwd"] = kwargs["cwd"]
            captured["env"] = kwargs["env"]
            kwargs["stdout"].write(b"sample output\n")
            return subprocess.CompletedProcess(
                args=args[0],
                returncode=0,
            )

        try:
            linux_verification.subprocess.run = fake_run
            with tempfile.TemporaryDirectory() as tmp:
                result = linux_verification.run_command(
                    ["python3", "--version"],
                    output_dir=Path(tmp),
                    log_name="command.log",
                )
                self.assertEqual("sample output\n", result.output)
                self.assertEqual(
                    "sample output\n",
                    (Path(tmp) / "command.log").read_text(encoding="utf-8"),
                )
                self.assertEqual(linux_verification.SUPPORT_DIR, captured["cwd"])
                env = captured["env"]
                self.assertIsInstance(env, dict)
                python_path = str(env["PYTHONPATH"]).split(linux_verification.os.pathsep)
                self.assertEqual(str(linux_verification.SUPPORT_DIR), python_path[0])
                self.assertEqual(str(linux_verification.REPO_ROOT), python_path[1])
        finally:
            linux_verification.subprocess.run = current

    def test_command_environment_uses_allowlist_and_strips_credentials(self) -> None:
        original_env = dict(linux_verification.os.environ)
        try:
            linux_verification.os.environ.clear()
            linux_verification.os.environ.update(
                {
                    "PATH": "/usr/bin",
                    "HOME": "/home/runner",
                    "GITHUB_TOKEN": "secret-token",
                    "ACTIONS_RUNTIME_TOKEN": "runtime-token",
                    "GH_TOKEN": "gh-token",
                    "SSH_AUTH_SOCK": "/tmp/agent.sock",
                    "UNRELATED": "drop-me",
                }
            )
            env = linux_verification.command_environment()
            self.assertEqual("/usr/bin", env["PATH"])
            self.assertEqual("/home/runner", env["HOME"])
            self.assertIn("PYTHONPATH", env)
            self.assertEqual("1", env["PYTHONDONTWRITEBYTECODE"])
            for forbidden in (
                "GITHUB_TOKEN",
                "ACTIONS_RUNTIME_TOKEN",
                "GH_TOKEN",
                "SSH_AUTH_SOCK",
                "UNRELATED",
            ):
                self.assertNotIn(forbidden, env)
        finally:
            linux_verification.os.environ.clear()
            linux_verification.os.environ.update(original_env)

    def test_run_command_records_timeout(self) -> None:
        current = linux_verification.subprocess.run

        def fake_timeout(*args, **kwargs):
            raise subprocess.TimeoutExpired(args[0], timeout=1)

        try:
            linux_verification.subprocess.run = fake_timeout
            with tempfile.TemporaryDirectory() as tmp:
                result = linux_verification.run_command(
                    ["python3", "-m", "unittest", "unit_tests"],
                    output_dir=Path(tmp),
                    log_name="timeout.log",
                )
                self.assertEqual(124, result.returncode)
                self.assertTrue(result.timed_out)
                self.assertIn("command timed out", result.output)
        finally:
            linux_verification.subprocess.run = current

    def test_run_command_caps_output_from_log(self) -> None:
        current_run = linux_verification.subprocess.run
        current_policy = linux_verification.parse_sandbox_policy

        def fake_policy(path):
            del path
            return {
                "limits": {
                    "command_timeout_seconds": 120,
                    "stdout_max_bytes": 5,
                    "stderr_max_bytes": 0,
                },
                "allowed_environment": ("PATH", "PYTHONPATH"),
            }

        def fake_run(*args, **kwargs):
            kwargs["stdout"].write(b"abcdef")
            return subprocess.CompletedProcess(args=args[0], returncode=0)

        try:
            linux_verification.parse_sandbox_policy = fake_policy
            linux_verification.subprocess.run = fake_run
            with tempfile.TemporaryDirectory() as tmp:
                result = linux_verification.run_command(
                    ["python3", "-m", "unittest", "unit_tests"],
                    output_dir=Path(tmp),
                    log_name="large.log",
                )
                self.assertTrue(result.output_truncated)
                self.assertTrue(result.output.startswith("abcde"))
        finally:
            linux_verification.subprocess.run = current_run
            linux_verification.parse_sandbox_policy = current_policy

    def test_support_module_hashes_use_control_root_with_split_roots(self) -> None:
        original_target = linux_verification.REPO_ROOT
        original_control = linux_verification.CONTROL_ROOT
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                target = root / "target"
                control = root / "control"
                support = control / "scripts" / "sandbox_test_support"
                (target / "tests").mkdir(parents=True)
                support.mkdir(parents=True)
                (support / "unit_tests.py").write_text("# unit\n", encoding="utf-8")
                (support / "support_paths.py").write_text(
                    "# support\n",
                    encoding="utf-8",
                )

                linux_verification.configure_roots(
                    target_root=target,
                    control_root=control,
                )
                hashes = linux_verification.support_module_hashes(
                    {"unit": ("python3", "-m", "unittest", "unit_tests")}
                )

                self.assertEqual(
                    "scripts/sandbox_test_support/unit_tests.py",
                    hashes["unit_tests"]["path"],
                )
                self.assertEqual(
                    "scripts/sandbox_test_support/support_paths.py",
                    hashes["support_paths"]["path"],
                )
        finally:
            linux_verification.configure_roots(
                target_root=original_target,
                control_root=original_control,
            )

    def test_policy_execution_plan_marks_missing_canary_alias_not_applicable(self) -> None:
        original_target = linux_verification.REPO_ROOT
        original_control = linux_verification.CONTROL_ROOT
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                target = root / "target"
                control = root / "control"
                target.mkdir()
                control.mkdir()
                linux_verification.configure_roots(
                    target_root=target,
                    control_root=control,
                )
                plan = linux_verification.policy_execution_plan()
                self.assertIn("stage2c-b1-clamp", plan["not_applicable_policy_test_ids"])
                self.assertNotIn("stage2c_b1_clamp_tests", plan["targeted_modules"])
        finally:
            linux_verification.configure_roots(
                target_root=original_target,
                control_root=original_control,
            )

    def test_policy_execution_plan_runs_canary_alias_when_target_exists(self) -> None:
        original_target = linux_verification.REPO_ROOT
        original_control = linux_verification.CONTROL_ROOT
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                target = root / "target"
                control = root / "control"
                (target / "canary").mkdir(parents=True)
                (target / "canary" / "stage2c_b1_clamp.py").write_text(
                    "def clamp(value, minimum, maximum):\n"
                    "    return max(minimum, min(value, maximum))\n",
                    encoding="utf-8",
                )
                control.mkdir()
                linux_verification.configure_roots(
                    target_root=target,
                    control_root=control,
                )
                plan = linux_verification.policy_execution_plan()
                self.assertIn("stage2c-b1-clamp", plan["executed_policy_test_ids"])
                self.assertIn("stage2c_b1_clamp_tests", plan["targeted_modules"])
        finally:
            linux_verification.configure_roots(
                target_root=original_target,
                control_root=original_control,
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
            / "sandbox-test-linux-verification.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("contents: read", workflow)
        self.assertNotIn(": write", workflow)

    def test_workflow_uses_default_branch_control_plane(self) -> None:
        workflow = (
            REPO_ROOT
            / ".github"
            / "workflows"
            / "sandbox-test-linux-verification.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", workflow)
        self.assertNotIn("workflow_run:", workflow)
        self.assertNotIn("pull_request:", workflow)
        self.assertIn(
            "github.ref == format('refs/heads/{0}', github.event.repository.default_branch)",
            workflow,
        )
        self.assertIn("TRIGGER_HEAD_SHA", workflow)
        self.assertNotIn("PR_HEAD_SHA", workflow)
        self.assertIn("VERIFICATION_SCOPE: default-branch-control-plane", workflow)
        self.assertIn("ref: ${{ github.sha }}", workflow)
        self.assertIn("path: verification-control", workflow)
        self.assertNotIn("path: verification-target", workflow)
        self.assertNotIn("ref: ${{ github.event.workflow_run.head_sha }}", workflow)
        self.assertIn(
            "python3 verification-control/scripts/linux_sandbox_test_verification.py",
            workflow,
        )
        self.assertIn("--control-root verification-control", workflow)
        self.assertIn("--target-root verification-control", workflow)

    def test_script_uses_trusted_support_test_modules(self) -> None:
        script = SCRIPT_PATH.read_text(encoding="utf-8")
        self.assertIn('"unit_tests"', script)
        self.assertIn('"stage2c_targeted_tests"', script)
        self.assertIn('"workflow_checker_tests"', script)
        self.assertIn('"compileall_checks"', script)
        self.assertNotIn('"discover"', script)
        self.assertNotIn('"test_*.py"', script)

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
