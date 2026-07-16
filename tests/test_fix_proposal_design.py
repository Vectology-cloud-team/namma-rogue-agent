from __future__ import annotations

import copy
import importlib.util
import sys
import unittest
from dataclasses import replace
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "check_fix_proposal_design.py"
)
SPEC = importlib.util.spec_from_file_location(
    "check_fix_proposal_design",
    SCRIPT_PATH,
)
check_fix_proposal_design = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = check_fix_proposal_design
SPEC.loader.exec_module(check_fix_proposal_design)


FULL_SHA_A = "a" * 40
FULL_SHA_B = "b" * 40
FULL_SHA_C = "c" * 40


class FixProposalDesignTests(unittest.TestCase):
    def setUp(self):
        self.policy = check_fix_proposal_design.load_fix_policy()

    def valid_patch(self, path="src/example.py"):
        return (
            f"diff --git a/{path} b/{path}\n"
            f"--- a/{path}\n"
            f"+++ b/{path}\n"
            "@@ -1 +1 @@\n"
            "-old\n"
            "+new\n"
        )

    def valid_change(self, path="src/example.py"):
        return {
            "path": path,
            "operation": "modify",
            "original_blob_sha": FULL_SHA_C,
            "patch": self.valid_patch(path),
            "rationale": "Address the reviewed finding.",
        }

    def valid_proposal(self):
        return {
            "schema_version": "1.0",
            "proposal_id": "proposal-123",
            "repository": "Vectology-cloud-team/namma-rogue-agent",
            "pull_request_number": 15,
            "base_sha": FULL_SHA_A,
            "head_sha": FULL_SHA_B,
            "review_comment_id": 123456,
            "reviewed_at": "2026-07-16T00:00:00Z",
            "generator": {
                "model": "gpt-5.5",
                "reasoning_effort": "medium",
                "policy_version": "policy-hash",
            },
            "summary": "Fix the reviewed issue.",
            "findings_addressed": [
                {
                    "finding_id": "finding-1",
                    "severity": "high",
                    "category": "correctness",
                }
            ],
            "changes": [self.valid_change()],
            "tests_recommended": ["python -m unittest discover"],
            "risks": ["behavior change"],
            "human_approval_required": True,
        }

    def assert_rejects(self, proposal, code, **kwargs):
        with self.assertRaises(check_fix_proposal_design.ProposalValidationError) as raised:
            check_fix_proposal_design.validate_fix_proposal(
                proposal,
                self.policy,
                **kwargs,
            )
        self.assertEqual(code, raised.exception.code)

    def test_policy_file_parses_required_labels_limits_and_paths(self):
        self.assertEqual("ai-fix-proposal", self.policy.proposal_label)
        self.assertEqual("ai-fix-approved", self.policy.approval_label)
        self.assertNotEqual(self.policy.proposal_label, self.policy.approval_label)
        self.assertEqual(("modify",), self.policy.allowed_operations)
        self.assertIn(".github/workflows/**", self.policy.protected_paths)
        self.assertIn(".github/codex/prompts/**", self.policy.protected_paths)
        self.assertIn(".github/codex/fix-policy.yml", self.policy.protected_paths)
        self.assertIn(".github/codex/schemas/**", self.policy.protected_paths)
        self.assertIn("*.pem", self.policy.protected_paths)
        self.assertIn("**/*.pem", self.policy.protected_paths)
        self.assertIn("*.key", self.policy.protected_paths)
        self.assertIn("**/*.key", self.policy.protected_paths)
        self.assertIn("*credential*", self.policy.protected_paths)
        self.assertIn("**/*credential*", self.policy.protected_paths)

    def test_policy_validation_requires_self_schema_and_credential_paths(self):
        required_paths = [
            ".github/codex/fix-policy.yml",
            ".github/codex/schemas/**",
            "*.pem",
            "**/*.pem",
            "*.key",
            "**/*.key",
            "*credential*",
            "**/*credential*",
        ]
        for protected_path in required_paths:
            with self.subTest(protected_path=protected_path):
                policy = replace(
                    self.policy,
                    protected_paths=tuple(
                        path
                        for path in self.policy.protected_paths
                        if path != protected_path
                    ),
                )
                with self.assertRaises(
                    check_fix_proposal_design.ProposalValidationError
                ) as raised:
                    check_fix_proposal_design.validate_fix_policy(policy)
                self.assertEqual("INVALID_POLICY", raised.exception.code)

    def test_schema_file_has_required_contract(self):
        schema = check_fix_proposal_design.validate_schema_file()
        self.assertEqual("NaMMA AI Fix Proposal", schema["title"])
        self.assertFalse(schema["additionalProperties"])
        self.assertIn("head_sha", schema["required"])
        self.assertIn("human_approval_required", schema["required"])
        change_schema = schema["properties"]["changes"]["items"]
        finding_schema = schema["properties"]["findings_addressed"]["items"]
        self.assertFalse(change_schema["additionalProperties"])
        self.assertFalse(finding_schema["additionalProperties"])
        self.assertIn("rationale", change_schema["required"])
        self.assertIn("finding_id", finding_schema["required"])
        self.assertEqual("modify", change_schema["properties"]["operation"]["const"])
        self.assertEqual(
            ["critical", "high", "medium", "low"],
            finding_schema["properties"]["severity"]["enum"],
        )

    def test_valid_proposal_passes(self):
        check_fix_proposal_design.validate_fix_proposal(
            self.valid_proposal(),
            self.policy,
            current_head_sha=FULL_SHA_B,
        )

    def test_head_sha_missing_or_short_is_rejected(self):
        proposal = self.valid_proposal()
        proposal["head_sha"] = "abc123"
        self.assert_rejects(proposal, "INVALID_SHA")

    def test_stale_sha_is_rejected(self):
        self.assert_rejects(
            self.valid_proposal(),
            "STALE_HEAD_SHA",
            current_head_sha="d" * 40,
        )

    def test_protected_path_is_rejected(self):
        proposal = self.valid_proposal()
        proposal["changes"] = [self.valid_change(".github/codex/review-policy.yml")]
        self.assert_rejects(proposal, "PROTECTED_PATH")

    def test_fix_policy_and_schema_paths_are_rejected(self):
        for path in (
            ".github/codex/fix-policy.yml",
            ".github/codex/schemas/fix-proposal.schema.json",
        ):
            with self.subTest(path=path):
                proposal = self.valid_proposal()
                proposal["changes"] = [self.valid_change(path)]
                self.assert_rejects(proposal, "PROTECTED_PATH")

    def test_root_and_nested_key_certificate_paths_are_rejected(self):
        for path in (
            "deploy.key",
            "cert.pem",
            "config/deploy.key",
            "config/cert.pem",
        ):
            with self.subTest(path=path):
                proposal = self.valid_proposal()
                proposal["changes"] = [self.valid_change(path)]
                self.assert_rejects(proposal, "PROTECTED_PATH")

    def test_root_and_nested_credential_keywords_are_rejected(self):
        for path in (
            "secret.txt",
            "credential-store.txt",
            "api-token.txt",
            "config/secret.txt",
            "config/credential-store.txt",
            "config/api-token.txt",
        ):
            with self.subTest(path=path):
                proposal = self.valid_proposal()
                proposal["changes"] = [self.valid_change(path)]
                self.assert_rejects(proposal, "PROTECTED_PATH")

    def test_path_traversal_is_rejected(self):
        proposal = self.valid_proposal()
        proposal["changes"] = [self.valid_change("docs/../secret.txt")]
        self.assert_rejects(proposal, "PATH_TRAVERSAL")

    def test_backslash_path_traversal_is_rejected(self):
        proposal = self.valid_proposal()
        proposal["changes"] = [self.valid_change(r"docs\..\secret.txt")]
        self.assert_rejects(proposal, "PATH_TRAVERSAL")

    def test_workflow_change_is_rejected(self):
        proposal = self.valid_proposal()
        proposal["changes"] = [self.valid_change(".github/workflows/architect-review.yml")]
        self.assert_rejects(proposal, "PROTECTED_PATH")

    def test_prompt_change_is_rejected(self):
        proposal = self.valid_proposal()
        proposal["changes"] = [
            self.valid_change(".github/codex/prompts/architect-review.md")
        ]
        self.assert_rejects(proposal, "PROTECTED_PATH")

    def test_binary_patch_is_rejected(self):
        proposal = self.valid_proposal()
        change = self.valid_change()
        change["patch"] = "GIT binary patch\nliteral 0\n"
        proposal["changes"] = [change]
        self.assert_rejects(proposal, "FORBIDDEN_PATCH_KIND")

    def test_create_delete_and_rename_are_rejected(self):
        markers = [
            "new file mode 100644\n",
            "deleted file mode 100644\n",
            "rename from old.py\nrename to new.py\n",
        ]
        for marker in markers:
            with self.subTest(marker=marker.strip()):
                proposal = self.valid_proposal()
                change = self.valid_change()
                change["patch"] = self.valid_patch() + marker
                proposal["changes"] = [change]
                self.assert_rejects(proposal, "FORBIDDEN_PATCH_KIND")

    def test_operation_create_is_rejected(self):
        proposal = self.valid_proposal()
        change = self.valid_change()
        change["operation"] = "create"
        proposal["changes"] = [change]
        self.assert_rejects(proposal, "FORBIDDEN_OPERATION")

    def test_patch_bytes_limit_is_rejected(self):
        small_policy = replace(
            self.policy,
            max_patch_bytes=10,
            max_file_patch_bytes=10,
        )
        with self.assertRaises(check_fix_proposal_design.ProposalValidationError) as raised:
            check_fix_proposal_design.validate_fix_proposal(
                self.valid_proposal(),
                small_policy,
            )
        self.assertEqual("PATCH_TOO_LARGE", raised.exception.code)

    def test_changed_files_limit_is_rejected(self):
        proposal = self.valid_proposal()
        proposal["changes"] = [
            self.valid_change("src/one.py"),
            self.valid_change("src/two.py"),
        ]
        small_policy = replace(self.policy, max_changed_files=1)
        with self.assertRaises(check_fix_proposal_design.ProposalValidationError) as raised:
            check_fix_proposal_design.validate_fix_proposal(proposal, small_policy)
        self.assertEqual("TOO_MANY_FILES", raised.exception.code)

    def test_duplicate_path_is_rejected(self):
        proposal = self.valid_proposal()
        proposal["changes"] = [
            self.valid_change("src/example.py"),
            self.valid_change("src/example.py"),
        ]
        self.assert_rejects(proposal, "DUPLICATE_PATH")

    def test_normalized_duplicate_path_is_rejected(self):
        proposal = self.valid_proposal()
        first = self.valid_change("src/example.py")
        second = self.valid_change(r"src\example.py")
        second["patch"] = self.valid_patch("src/example.py")
        proposal["changes"] = [first, second]
        self.assert_rejects(proposal, "DUPLICATE_PATH")

    def test_original_blob_sha_is_required(self):
        proposal = self.valid_proposal()
        del proposal["changes"][0]["original_blob_sha"]
        self.assert_rejects(proposal, "INVALID_PROPOSAL")

    def test_change_rationale_is_required(self):
        proposal = self.valid_proposal()
        del proposal["changes"][0]["rationale"]
        self.assert_rejects(proposal, "INVALID_PROPOSAL")

    def test_unexpected_top_level_property_is_rejected(self):
        proposal = self.valid_proposal()
        proposal["extra"] = "not allowed"
        self.assert_rejects(proposal, "INVALID_PROPOSAL")

    def test_unexpected_change_property_is_rejected(self):
        proposal = self.valid_proposal()
        proposal["changes"][0]["mode"] = "100644"
        self.assert_rejects(proposal, "INVALID_PROPOSAL")

    def test_invalid_finding_severity_is_rejected(self):
        proposal = self.valid_proposal()
        proposal["findings_addressed"][0]["severity"] = "urgent"
        self.assert_rejects(proposal, "INVALID_PROPOSAL")

    def test_patch_path_mismatch_is_rejected(self):
        proposal = self.valid_proposal()
        change = self.valid_change("src/example.py")
        change["patch"] = self.valid_patch("src/other.py")
        proposal["changes"] = [change]
        self.assert_rejects(proposal, "PATCH_PATH_MISMATCH")

    def test_human_approval_is_required(self):
        proposal = self.valid_proposal()
        proposal["human_approval_required"] = False
        self.assert_rejects(proposal, "HUMAN_APPROVAL_REQUIRED")

    def test_proposal_id_or_content_hash_is_required(self):
        proposal = self.valid_proposal()
        proposal["proposal_id"] = ""
        self.assert_rejects(proposal, "INVALID_PROPOSAL")
        proposal = self.valid_proposal()
        digest = check_fix_proposal_design.proposal_content_hash(proposal)
        self.assertEqual(64, len(digest))

    def test_approval_label_and_proposal_label_are_different(self):
        self.assertNotEqual(self.policy.proposal_label, self.policy.approval_label)

    def test_head_sha_change_invalidates_approval(self):
        proposal = self.valid_proposal()
        proposal_hash = check_fix_proposal_design.proposal_content_hash(proposal)
        with self.assertRaises(check_fix_proposal_design.ProposalValidationError) as raised:
            check_fix_proposal_design.validate_approval_gate(
                proposal,
                self.policy,
                labels={self.policy.proposal_label, self.policy.approval_label},
                approver_association="OWNER",
                current_head_sha="d" * 40,
                approved_head_sha=FULL_SHA_B,
                approved_proposal_id=proposal["proposal_id"],
                approved_proposal_hash=proposal_hash,
            )
        self.assertEqual("STALE_APPROVAL", raised.exception.code)

    def test_trusted_approval_binding_record_is_required(self):
        proposal = self.valid_proposal()
        proposal_hash = check_fix_proposal_design.proposal_content_hash(proposal)
        cases = [
            ("", FULL_SHA_B, proposal_hash),
            (proposal["proposal_id"], "", proposal_hash),
            (proposal["proposal_id"], FULL_SHA_B, ""),
        ]
        for approved_proposal_id, approved_head_sha, approved_hash in cases:
            with self.subTest(
                approved_proposal_id=approved_proposal_id,
                approved_head_sha=approved_head_sha,
                approved_hash=approved_hash,
            ):
                with self.assertRaises(
                    check_fix_proposal_design.ProposalValidationError
                ) as raised:
                    check_fix_proposal_design.validate_approval_gate(
                        proposal,
                        self.policy,
                        labels={self.policy.proposal_label, self.policy.approval_label},
                        approver_association="OWNER",
                        current_head_sha=FULL_SHA_B,
                        approved_head_sha=approved_head_sha,
                        approved_proposal_id=approved_proposal_id,
                        approved_proposal_hash=approved_hash,
                    )
                self.assertEqual("APPROVAL_BINDING_MISSING", raised.exception.code)

    def test_approval_requires_owner_or_member_and_matching_hash(self):
        proposal = self.valid_proposal()
        proposal_hash = check_fix_proposal_design.proposal_content_hash(proposal)
        check_fix_proposal_design.validate_approval_gate(
            proposal,
            self.policy,
            labels={self.policy.proposal_label, self.policy.approval_label},
            approver_association="MEMBER",
            current_head_sha=FULL_SHA_B,
            approved_head_sha=FULL_SHA_B,
            approved_proposal_id=proposal["proposal_id"],
            approved_proposal_hash=proposal_hash,
        )
        with self.assertRaises(check_fix_proposal_design.ProposalValidationError) as raised:
            check_fix_proposal_design.validate_approval_gate(
                proposal,
                self.policy,
                labels={self.policy.proposal_label, self.policy.approval_label},
                approver_association="COLLABORATOR",
                current_head_sha=FULL_SHA_B,
                approved_head_sha=FULL_SHA_B,
                approved_proposal_id=proposal["proposal_id"],
                approved_proposal_hash=proposal_hash,
            )
        self.assertEqual("APPROVER_NOT_ALLOWED", raised.exception.code)

    def test_proposal_mutation_invalidates_approval_hash(self):
        proposal = self.valid_proposal()
        proposal_hash = check_fix_proposal_design.proposal_content_hash(proposal)
        mutated = copy.deepcopy(proposal)
        mutated["summary"] = "Changed after approval."
        with self.assertRaises(check_fix_proposal_design.ProposalValidationError) as raised:
            check_fix_proposal_design.validate_approval_gate(
                mutated,
                self.policy,
                labels={self.policy.proposal_label, self.policy.approval_label},
                approver_association="OWNER",
                current_head_sha=FULL_SHA_B,
                approved_head_sha=FULL_SHA_B,
                approved_proposal_id=mutated["proposal_id"],
                approved_proposal_hash=proposal_hash,
            )
        self.assertEqual("PROPOSAL_HASH_MISMATCH", raised.exception.code)

    def test_static_design_checks_pass(self):
        results = check_fix_proposal_design.run_checks()
        failed = [result for result in results if not result.passed]
        self.assertEqual([], failed)

    def test_stage2_design_has_no_runtime_workflow_wiring(self):
        workflow_text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted(check_fix_proposal_design.WORKFLOW_DIR.glob("*.yml"))
        )
        self.assertNotIn("ai-fix-proposal", workflow_text)
        self.assertNotIn("ai-fix-approved", workflow_text)
        self.assertNotIn("namma-ai-fix-proposal", workflow_text)

    def test_stage2_design_adds_no_secret_reference(self):
        new_files = [
            check_fix_proposal_design.DESIGN_DOC_PATH,
            check_fix_proposal_design.FIX_POLICY_PATH,
            check_fix_proposal_design.FIX_SCHEMA_PATH,
        ]
        text = "\n".join(path.read_text(encoding="utf-8") for path in new_files)
        self.assertNotIn("secrets.", text)
        self.assertNotIn("OPENAI_API_KEY", text)

    def test_checker_has_no_shell_or_network_apply_surface(self):
        script = SCRIPT_PATH.read_text(encoding="utf-8")
        self.assertNotIn("subprocess", script)
        self.assertNotIn("urllib", script)
        self.assertNotIn("requests", script)
        self.assertNotIn("git push", script)
        self.assertNotIn("git merge", script)


if __name__ == "__main__":
    unittest.main()
