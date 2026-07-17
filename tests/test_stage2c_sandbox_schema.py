from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = (
    REPO_ROOT
    / ".github"
    / "codex"
    / "schemas"
    / "sandbox-validation-result.schema.json"
)


class Stage2CSandboxSchemaTests(unittest.TestCase):
    def schema(self):
        with SCHEMA_PATH.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def valid_result(self):
        check_pass = {
            "status": "PASS",
            "message": "ok",
        }
        artifact = {
            "artifact_id": 123,
            "artifact_name": "artifact",
            "workflow_run_id": 456,
            "workflow_name": "Workflow",
            "repository": "Vectology-cloud-team/namma-rogue-agent",
            "pull_request_number": 25,
            "head_sha": "b" * 40,
        }
        return {
            "schema_version": "sandbox-validation-result-v1",
            "validation_id": "1" * 32,
            "repository": "Vectology-cloud-team/namma-rogue-agent",
            "pull_request_number": 25,
            "base_sha": "a" * 40,
            "head_sha": "b" * 40,
            "proposal_id": "2" * 32,
            "proposal_hash": "3" * 64,
            "approval_id": "4" * 32,
            "approval_record_hash": "5" * 64,
            "approved_by": "maintainer",
            "approved_by_repository_permission": "maintain",
            "approved_by_repository_role": "maintain",
            "proposal_artifact": dict(artifact),
            "approval_artifact": dict(artifact),
            "schema_versions": {
                "proposal": "fix-proposal-v1",
                "approval": "approval-record-v1",
                "validation_result": "sandbox-validation-result-v1",
            },
            "policy_hash": "6" * 64,
            "test_plan_hash": "7" * 64,
            "started_at": "2026-07-17T00:00:00Z",
            "completed_at": "2026-07-17T00:00:01Z",
            "status": "SUCCESS",
            "failure_class": None,
            "failure_code": None,
            "patch_check": dict(check_pass),
            "patch_apply": dict(check_pass),
            "expected_files": ["canary/example.py"],
            "actual_changed_files": ["canary/example.py"],
            "protected_path_check": dict(check_pass),
            "blob_sha_check": dict(check_pass),
            "tests_requested": ["unit"],
            "tests_executed": ["unit"],
            "requested_tests_executed": True,
            "test_results": [
                {
                    "test_id": "unit",
                    "status": "PASS",
                    "exit_code": 0,
                    "duration_ms": 100,
                    "log_excerpt": "ok",
                }
            ],
            "changed_files_match_expected": True,
            "persistent_repository_modified": False,
            "sandbox_worktree_modified": True,
            "commit_created": False,
            "push_performed": False,
            "merge_performed": False,
            "sandbox_destroyed": True,
        }

    def success_condition(self):
        schema = self.schema()
        for condition in schema.get("allOf", []):
            status = (
                condition.get("if", {})
                .get("properties", {})
                .get("status", {})
                .get("const")
            )
            if status == "SUCCESS":
                return condition["then"]["properties"]
        self.fail("sandbox validation result schema lacks SUCCESS condition")

    def condition_for(self, wanted_status):
        schema = self.schema()
        for condition in schema.get("allOf", []):
            status = (
                condition.get("if", {})
                .get("properties", {})
                .get("status", {})
                .get("const")
            )
            if status == wanted_status:
                return condition["then"]["properties"]
        self.fail(f"schema lacks {wanted_status} condition")

    def contract_errors(self, result):
        errors = []
        if result["status"] == "SUCCESS":
            for check_name in (
                "patch_check",
                "patch_apply",
                "protected_path_check",
                "blob_sha_check",
            ):
                if result[check_name]["status"] != "PASS":
                    errors.append(f"{check_name} is not PASS")
            if result["failure_class"] is not None:
                errors.append("success has failure_class")
            if result["failure_code"] is not None:
                errors.append("success has failure_code")
            if not result["requested_tests_executed"]:
                errors.append("requested tests were not executed")
            if any(test["status"] != "PASS" for test in result["test_results"]):
                errors.append("test result is not PASS")
            if not result["changed_files_match_expected"]:
                errors.append("changed files differ")
            if result["sandbox_destroyed"] is not True:
                errors.append("sandbox was not destroyed")
        else:
            if result["failure_class"] != result["status"]:
                errors.append("failure_class does not match status")
            if not result["failure_code"]:
                errors.append("failure_code is missing")
        for artifact_name in ("proposal_artifact", "approval_artifact"):
            if "pull_request_number" not in result[artifact_name]:
                errors.append(f"{artifact_name} lacks pull request binding")
        return errors

    def test_schema_file_is_valid_json(self):
        schema = self.schema()
        self.assertEqual(
            "NaMMA AI Sandbox Validation Result",
            schema["title"],
        )
        self.assertEqual(
            "sandbox-validation-result-v1",
            schema["properties"]["schema_version"]["const"],
        )

    def test_success_requires_cleanup_and_no_persistent_write(self):
        success_properties = self.success_condition()
        self.assertEqual(
            True,
            success_properties["sandbox_destroyed"]["const"],
        )
        self.assertEqual(
            False,
            success_properties["persistent_repository_modified"]["const"],
        )
        self.assertEqual(False, success_properties["commit_created"]["const"])
        self.assertEqual(False, success_properties["push_performed"]["const"])
        self.assertEqual(False, success_properties["merge_performed"]["const"])

    def test_success_requires_patch_and_policy_checks_to_pass(self):
        success_properties = self.success_condition()
        for check_name in (
            "patch_check",
            "patch_apply",
            "protected_path_check",
            "blob_sha_check",
        ):
            with self.subTest(check_name=check_name):
                self.assertEqual(
                    "PASS",
                    success_properties[check_name]["properties"]["status"]["const"],
                )

    def test_success_requires_no_failure_code(self):
        success_properties = self.success_condition()
        self.assertIsNone(success_properties["failure_class"]["const"])
        self.assertIsNone(success_properties["failure_code"]["const"])

    def test_success_requires_tests_and_changed_files_to_match(self):
        success_properties = self.success_condition()
        self.assertEqual(
            True,
            success_properties["requested_tests_executed"]["const"],
        )
        self.assertEqual(
            "PASS",
            success_properties["test_results"]["items"]["properties"]["status"][
                "const"
            ],
        )
        self.assertEqual(
            True,
            success_properties["changed_files_match_expected"]["const"],
        )

    def test_non_success_status_requires_matching_failure_class(self):
        for status in (
            "PATCH_REJECTED",
            "TEST_FAILED",
            "STALE",
            "FATAL",
            "INFRA_ERROR",
        ):
            with self.subTest(status=status):
                condition = self.condition_for(status)
                self.assertEqual(status, condition["failure_class"]["const"])
                self.assertEqual(
                    "string",
                    condition["failure_code"]["type"],
                )
                self.assertEqual(1, condition["failure_code"]["minLength"])

    def test_contract_rejects_invalid_success_results(self):
        invalid_cases = [
            ("failed test", lambda result: result["test_results"][0].update(
                {"status": "FAIL"}
            )),
            ("missing requested tests", lambda result: result.update(
                {"requested_tests_executed": False}
            )),
            ("changed files mismatch", lambda result: result.update(
                {"changed_files_match_expected": False}
            )),
            ("sandbox not destroyed", lambda result: result.update(
                {"sandbox_destroyed": False}
            )),
        ]
        for _name, mutate in invalid_cases:
            result = self.valid_result()
            mutate(result)
            self.assertTrue(self.contract_errors(result))

    def test_contract_rejects_mismatched_failure_classes(self):
        result = self.valid_result()
        result["status"] = "FATAL"
        result["failure_class"] = "STALE"
        result["failure_code"] = "POLICY_HASH_MISMATCH"
        self.assertIn(
            "failure_class does not match status",
            self.contract_errors(result),
        )

    def test_artifact_provenance_records_pull_request_binding(self):
        provenance = self.schema()["$defs"]["artifact_provenance"]
        self.assertIn("pull_request_number", provenance["required"])
        self.assertEqual(
            1,
            provenance["properties"]["pull_request_number"]["minimum"],
        )

    def test_contract_rejects_artifact_without_pull_request_binding(self):
        result = self.valid_result()
        del result["proposal_artifact"]["pull_request_number"]
        self.assertIn(
            "proposal_artifact lacks pull request binding",
            self.contract_errors(result),
        )

    def test_test_id_schema_rejects_free_form_shell(self):
        pattern = self.schema()["$defs"]["test_id"]["pattern"]
        compiled = re.compile(pattern)
        self.assertRegex("unit", compiled)
        self.assertRegex("approval-targeted", compiled)
        self.assertIsNone(compiled.fullmatch("python -m unittest discover"))
        self.assertIsNone(compiled.fullmatch("unit && curl example.com"))
        self.assertIsNone(compiled.fullmatch("bash -c test"))

    def test_requested_and_executed_tests_use_test_id_schema(self):
        schema = self.schema()
        properties = schema["properties"]
        self.assertEqual(
            "#/$defs/test_id",
            properties["tests_requested"]["items"]["$ref"],
        )
        self.assertEqual(
            "#/$defs/test_id",
            properties["tests_executed"]["items"]["$ref"],
        )


if __name__ == "__main__":
    unittest.main()
