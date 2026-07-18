from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
SCRIPT_PATH = SCRIPTS_DIR / "sandbox_test.py"
SPEC = importlib.util.spec_from_file_location("sandbox_test", SCRIPT_PATH)
sandbox_test = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = sandbox_test
SPEC.loader.exec_module(sandbox_test)


BASE_SHA = "a" * 40
HEAD_SHA = "b" * 40
PROPOSAL_HASH = "c" * 64
APPROVAL_HASH = "d" * 64
PREFLIGHT_HASH = "e" * 64
APPLY_HASH = "f" * 64
POLICY_HASH = "1" * 64
TEST_POLICY_HASH = "2" * 64
PATCH_HASH = "3" * 64


def python3_works() -> bool:
    if not shutil.which("python3"):
        return False
    completed = subprocess.run(
        ["python3", "-c", "import sys"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return completed.returncode == 0


class SandboxTestTests(unittest.TestCase):
    def policy(self):
        return sandbox_test.fix.load_fix_proposal_policy(
            REPO_ROOT / ".github" / "codex" / "fix-policy.yml"
        )

    def sandbox_test_policy(self):
        return sandbox_test.load_sandbox_test_policy(
            REPO_ROOT / ".github" / "codex" / "sandbox-test-policy.yml"
        )

    def manifest(
        self,
        *,
        labels=None,
        head_sha=HEAD_SHA,
        request_stage="SANDBOX_TEST_REQUEST",
        event_action="labeled",
        event_label="ai-fix-test-sandbox",
        head_repository=None,
    ):
        return {
            "schema_version": "sandbox-test-request-v1",
            "request_stage": request_stage,
            "repository": sandbox_test.EXPECTED_REPOSITORY,
            "pull_request_number": 32,
            "base_sha": BASE_SHA,
            "head_sha": head_sha,
            "actor": "tester",
            "author_association": "MEMBER",
            "draft": False,
            "base_repository": sandbox_test.EXPECTED_REPOSITORY,
            "head_repository": head_repository or sandbox_test.EXPECTED_REPOSITORY,
            "labels": labels
            if labels is not None
            else [
                "ai-fix-proposal",
                "ai-fix-approved",
                "ai-fix-validate",
                "ai-fix-apply-sandbox",
                "ai-fix-test-sandbox",
            ],
            "event_action": event_action,
            "event_name": "pull_request",
            "event_label": event_label,
            "collector_workflow_name": sandbox_test.COLLECTOR_WORKFLOW_NAME,
            "collector_workflow_run_id": 123,
            "requested_at": "2026-07-18T00:00:00Z",
        }

    def live_pull(self, *, head_sha=HEAD_SHA, state="open", head_repo=None):
        return {
            "number": 32,
            "state": state,
            "draft": False,
            "head": {
                "sha": head_sha,
                "repo": {"full_name": head_repo or sandbox_test.EXPECTED_REPOSITORY},
            },
            "base": {
                "sha": BASE_SHA,
                "repo": {"full_name": sandbox_test.EXPECTED_REPOSITORY},
            },
            "user": {"type": "User"},
        }

    def live_issue(self, labels=None):
        return {
            "labels": [
                {"name": label}
                for label in (
                    labels
                    if labels is not None
                    else [
                        "ai-fix-proposal",
                        "ai-fix-approved",
                        "ai-fix-validate",
                        "ai-fix-apply-sandbox",
                        "ai-fix-test-sandbox",
                    ]
                )
            ]
        }

    def test_valid_test_manifest_and_live_gate(self):
        labels = sandbox_test.validate_live_test_gate(
            manifest=self.manifest(),
            live_pull=self.live_pull(),
            live_issue=self.live_issue(),
            policy=self.policy(),
            test_policy=self.sandbox_test_policy(),
            test_actor="tester",
            test_actor_permission="admin",
        )
        self.assertIn("ai-fix-test-sandbox", labels)

    def test_wrong_label_is_rejected(self):
        with self.assertRaises(sandbox_test.fix.FixProposalFailure):
            sandbox_test.validate_request_manifest_shape(
                self.manifest(event_label="ai-fix-apply-sandbox")
            )

    def test_missing_prior_live_label_is_rejected(self):
        with self.assertRaises(sandbox_test.fix.FixProposalFailure):
            sandbox_test.validate_live_test_gate(
                manifest=self.manifest(labels=["ai-fix-test-sandbox"]),
                live_pull=self.live_pull(),
                live_issue=self.live_issue(labels=["ai-fix-test-sandbox"]),
                policy=self.policy(),
                test_policy=self.sandbox_test_policy(),
                test_actor="tester",
                test_actor_permission="admin",
            )

    def test_fork_pr_is_rejected(self):
        with self.assertRaises(sandbox_test.fix.FixProposalFailure):
            sandbox_test.validate_live_test_gate(
                manifest=self.manifest(head_repository="fork/repo"),
                live_pull=self.live_pull(head_repo="fork/repo"),
                live_issue=self.live_issue(),
                policy=self.policy(),
                test_policy=self.sandbox_test_policy(),
                test_actor="tester",
                test_actor_permission="admin",
            )

    def test_write_permission_is_rejected(self):
        with self.assertRaises(sandbox_test.fix.FixProposalFailure):
            sandbox_test.validate_live_test_gate(
                manifest=self.manifest(),
                live_pull=self.live_pull(),
                live_issue=self.live_issue(),
                policy=self.policy(),
                test_policy=self.sandbox_test_policy(),
                test_actor="tester",
                test_actor_permission="write",
            )

    def test_stale_head_is_rejected(self):
        with self.assertRaises(sandbox_test.SandboxTestStatus):
            sandbox_test.validate_live_test_gate(
                manifest=self.manifest(),
                live_pull=self.live_pull(head_sha="d" * 40),
                live_issue=self.live_issue(),
                policy=self.policy(),
                test_policy=self.sandbox_test_policy(),
                test_actor="tester",
                test_actor_permission="maintain",
            )

    def test_trusted_test_id_resolves_to_fixed_command(self):
        recommendations = ["stage2c-b1-clamp"]
        commands = sandbox_test.resolve_requested_test_commands(
            recommendations,
            self.sandbox_test_policy(),
        )
        self.assertEqual(1, len(commands))
        self.assertEqual("stage2c-b1-clamp", commands[0].test_id)
        self.assertEqual(
            ("python3", "-m", "unittest", "stage2c_b1_clamp_tests"),
            commands[0].argv,
        )

    def test_all_fix_policy_test_ids_resolve_to_trusted_commands(self):
        recommendations = list(
            sandbox_test.preflight.load_sandbox_test_ids(
                REPO_ROOT / ".github" / "codex" / "fix-policy.yml"
            )
        )
        commands = sandbox_test.resolve_requested_test_commands(
            recommendations,
            self.sandbox_test_policy(),
        )
        self.assertEqual(recommendations, [command.test_id for command in commands])
        for command in commands:
            with self.subTest(test_id=command.test_id):
                self.assertEqual(("python3", "-m", "unittest"), command.argv[:3])
                self.assertNotIn(" ", command.test_id)

    def test_empty_tests_are_rejected(self):
        with self.assertRaises(sandbox_test.SandboxTestStatus):
            sandbox_test.resolve_requested_test_commands([], self.sandbox_test_policy())

    def test_unknown_or_natural_language_recommendation_is_rejected(self):
        cases = [
            ["python -m unittest discover"],
            [
                "Run the targeted clamp checks for clamp(5, 1, 3), clamp(0, 1, 3), and clamp(2, 1, 3).",
            ],
        ]
        for recommendations in cases:
            with self.subTest(recommendations=recommendations):
                with self.assertRaises(sandbox_test.SandboxTestStatus):
                    sandbox_test.resolve_requested_test_commands(
                        recommendations,
                        self.sandbox_test_policy(),
                    )

    def assert_bad_argv(self, argv):
        with self.assertRaises(sandbox_test.SandboxTestStatus):
            sandbox_test.validate_argv("bad", tuple(argv))

    def test_command_rejects_shell_and_unapproved_runners(self):
        self.assert_bad_argv(["bash", "-c", "echo bad"])
        self.assert_bad_argv(["sh", "-c", "echo bad"])
        self.assert_bad_argv(["git", "status"])
        self.assert_bad_argv(["pip", "install", "x"])
        self.assert_bad_argv(["curl", "https://example.test"])

    def test_command_rejects_inline_code_and_unsafe_args(self):
        self.assert_bad_argv(["python3", "-c", "print(1)"])
        self.assert_bad_argv(["python3", "-m", "os"])
        self.assert_bad_argv(["python3", "-m", "unittest", "../bad"])
        self.assert_bad_argv(["python3", "-m", "unittest", "/tmp/bad"])
        self.assert_bad_argv(["python3", "-m", "unittest", "bad\nname"])
        self.assert_bad_argv(["python3", "-m", "unittest", "bad\x00name"])
        self.assert_bad_argv(["python3", "-m", "unittest", "tests.*"])

    def test_python_runner_is_allowed_only_as_executable(self):
        sandbox_test.validate_argv(
            "ok",
            ("python", "-m", "unittest", "stage2c_b1_clamp_tests"),
        )

    def test_sandbox_test_id_is_deterministic(self):
        kwargs = {
            "repository": sandbox_test.EXPECTED_REPOSITORY,
            "pull_request_number": 32,
            "head_sha": HEAD_SHA,
            "proposal_id": "a" * 32,
            "proposal_hash": PROPOSAL_HASH,
            "approval_id": "b" * 32,
            "approval_record_hash": APPROVAL_HASH,
            "preflight_validation_id": "c" * 32,
            "preflight_result_hash": PREFLIGHT_HASH,
            "sandbox_apply_id": "d" * 32,
            "sandbox_apply_result_hash": APPLY_HASH,
            "test_request_actor": "tester",
            "policy_hash": POLICY_HASH,
            "sandbox_test_policy_hash": TEST_POLICY_HASH,
            "test_plan_hash": "4" * 64,
            "patch_hash": PATCH_HASH,
        }
        first = sandbox_test.sandbox_test_id_for(**kwargs)
        second = sandbox_test.sandbox_test_id_for(**kwargs)
        self.assertEqual(first, second)
        self.assertEqual(32, len(first))

    def test_secret_environment_is_not_propagated(self):
        old = os.environ.get("GITHUB_TOKEN")
        os.environ["GITHUB_TOKEN"] = "secret"
        try:
            env = sandbox_test.test_environment(
                allowed_environment=("PATH", "PYTHONPATH"),
                support_dir=REPO_ROOT / "scripts" / "sandbox_test_support",
            )
        finally:
            if old is None:
                os.environ.pop("GITHUB_TOKEN", None)
            else:
                os.environ["GITHUB_TOKEN"] = old
        self.assertNotIn("GITHUB_TOKEN", env)
        self.assertIn("PYTHONPATH", env)

    def test_test_runner_step_does_not_export_github_token(self):
        workflow = (
            REPO_ROOT / ".github" / "workflows" / "fix-sandbox-test.yml"
        ).read_text(encoding="utf-8")
        marker = "      - name: Run approved tests in ephemeral sandbox"
        start = workflow.index(marker)
        end = workflow.find("\n      - name:", start + len(marker))
        step = workflow[start:] if end == -1 else workflow[start:end]
        self.assertNotIn("GITHUB_TOKEN", step)

    def test_total_timeout_limits_effective_command_timeout(self):
        current = sandbox_test.time.monotonic
        try:
            sandbox_test.time.monotonic = lambda: 105.0
            timeout = sandbox_test.effective_command_timeout(
                start_time=100.0,
                total_timeout_seconds=30,
                command_timeout_seconds=120,
            )
            self.assertEqual(25, timeout)
        finally:
            sandbox_test.time.monotonic = current

    def test_total_timeout_expiry_is_rejected(self):
        current = sandbox_test.time.monotonic
        try:
            sandbox_test.time.monotonic = lambda: 131.0
            with self.assertRaises(sandbox_test.SandboxTestStatus):
                sandbox_test.effective_command_timeout(
                    start_time=100.0,
                    total_timeout_seconds=30,
                    command_timeout_seconds=120,
                )
        finally:
            sandbox_test.time.monotonic = current

    def test_output_truncation_records_flag(self):
        truncated, flag = sandbox_test.redacted_output(b"abcdef", 3)
        self.assertEqual(b"abc", truncated)
        self.assertTrue(flag)

    @unittest.skipUnless(python3_works(), "python3 is unavailable locally")
    def test_approved_unittest_command_passes_against_trusted_support(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "canary").mkdir()
            (root / "canary" / "__init__.py").write_text("", encoding="utf-8")
            (root / "canary" / "stage2c_b1_clamp.py").write_text(
                "\n".join(
                    [
                        "def clamp(value: int, minimum: int, maximum: int) -> int:",
                        "    return min(max(value, minimum), maximum)",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            env = sandbox_test.test_environment(
                allowed_environment=("PATH", "PYTHONPATH"),
                support_dir=REPO_ROOT / "scripts" / "sandbox_test_support",
                worktree=root,
            )
            command = self.sandbox_test_policy().commands["stage2c-b1-clamp"]
            record, _, _ = sandbox_test.run_one_test(
                command=command,
                worktree=root,
                support_dir=REPO_ROOT / "scripts" / "sandbox_test_support",
                env=env,
                stdout_limit=100000,
                stderr_limit=100000,
            )
            self.assertEqual("PASS", record["status"])
            self.assertEqual(0, record["exit_code"])

    @unittest.skipUnless(python3_works(), "python3 is unavailable locally")
    def test_approved_unittest_command_reports_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "canary").mkdir()
            (root / "canary" / "__init__.py").write_text("", encoding="utf-8")
            (root / "canary" / "stage2c_b1_clamp.py").write_text(
                "\n".join(
                    [
                        "def clamp(value: int, minimum: int, maximum: int) -> int:",
                        "    return min(minimum, max(value, maximum))",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            env = sandbox_test.test_environment(
                allowed_environment=("PATH", "PYTHONPATH"),
                support_dir=REPO_ROOT / "scripts" / "sandbox_test_support",
                worktree=root,
            )
            command = self.sandbox_test_policy().commands["stage2c-b1-clamp"]
            record, _, _ = sandbox_test.run_one_test(
                command=command,
                worktree=root,
                support_dir=REPO_ROOT / "scripts" / "sandbox_test_support",
                env=env,
                stdout_limit=100000,
                stderr_limit=100000,
            )
            self.assertEqual("FAIL", record["status"])

    @unittest.skipUnless(python3_works(), "python3 is unavailable locally")
    def test_worktree_cannot_shadow_trusted_support_test_module(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "canary").mkdir()
            (root / "canary" / "__init__.py").write_text("", encoding="utf-8")
            (root / "canary" / "stage2c_b1_clamp.py").write_text(
                "\n".join(
                    [
                        "def clamp(value: int, minimum: int, maximum: int) -> int:",
                        "    return value",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (root / "stage2c_b1_clamp_tests.py").write_text(
                "\n".join(
                    [
                        "import unittest",
                        "",
                        "class ShadowedTests(unittest.TestCase):",
                        "    def test_shadow_would_pass(self):",
                        "        self.assertTrue(True)",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            support_dir = REPO_ROOT / "scripts" / "sandbox_test_support"
            env = sandbox_test.test_environment(
                allowed_environment=("PATH", "PYTHONPATH"),
                support_dir=support_dir,
                worktree=root,
            )
            command = self.sandbox_test_policy().commands["stage2c-b1-clamp"]
            record, _, _ = sandbox_test.run_one_test(
                command=command,
                worktree=root,
                support_dir=support_dir,
                env=env,
                stdout_limit=100000,
                stderr_limit=100000,
            )
            self.assertEqual("FAIL", record["status"])
            self.assertNotEqual(0, record["exit_code"])


if __name__ == "__main__":
    unittest.main()
