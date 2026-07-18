"""Trusted lightweight workflow safety checks for sandbox test runs."""

from __future__ import annotations

import unittest

from support_paths import worktree_root


FORBIDDEN_WORKFLOW_TEXT = (
    "contents: write",
    "actions: write",
    "checks: write",
    "deployments: write",
    "id-token: write",
    "packages: write",
    "security-events: write",
    "statuses: write",
    "git push",
    "git merge",
    "gh pr merge",
    "pull_request_target",
)


class WorkflowCheckerTests(unittest.TestCase):
    def test_workflows_keep_persistent_write_operations_out(self) -> None:
        root = worktree_root()
        workflow_dir = root / ".github" / "workflows"
        workflow_files = sorted(workflow_dir.glob("*.yml")) + sorted(
            workflow_dir.glob("*.yaml")
        )
        failures: list[str] = []
        for path in workflow_files:
            text = path.read_text(encoding="utf-8").lower()
            for forbidden in FORBIDDEN_WORKFLOW_TEXT:
                if forbidden in text:
                    failures.append(
                        f"{path.relative_to(root).as_posix()}: {forbidden}"
                    )
        self.assertEqual([], failures)
