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
        test_pass = {
            "test_id": "unit",
            "requested": True,
            "executed": True,
            "status": "PASS",
            "exit_code": 0,
            "duration_ms": 100,
            "log_excerpt": "ok",
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
            "phase": "SANDBOX",
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
            "validation_request_actor": "validator",
            "validation_request_actor_repository_permission": "admin",
            "validation_request_actor_repository_role": "admin",
            "live_labels": [
                "ai-fix-proposal",
                "ai-fix-approved",
                "ai-fix-validate",
            ],
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
            "target_blob_checks": [
                {
                    "path": "canary/example.py",
                    "expected_blob_sha": "8" * 40,
                    "actual_blob_sha": "8" * 40,
                    "file_type": "blob",
                    "mode": "100644",
                    "size": 120,
                    "status": "PASS",
                }
            ],
            "patch_metadata_check": {
                "status": "PASS",
                "message": "metadata ok",
                "patch_bytes": 100,
            },
            "tests_requested": [dict(test_pass)],
            "tests_executed": [dict(test_pass)],
            "test_results": [dict(test_pass)],
            "changed_files_match_expected": True,
            "persistent_repository_modified": False,
            "sandbox_worktree_modified": True,
            "sandbox_checkout_performed": True,
            "patch_check_performed": True,
            "patch_applied": True,
            "test_execution_performed": True,
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

    def precheck_condition(self):
        schema = self.schema()
        for condition in schema.get("allOf", []):
            status = (
                condition.get("if", {})
                .get("properties", {})
                .get("status", {})
                .get("const")
            )
            if status == "PRECHECK_PASSED":
                return condition["then"]["properties"]
        self.fail("sandbox validation result schema lacks PRECHECK_PASSED condition")

    def valid_precheck_result(self):
        result = self.valid_result()
        skipped_test = {
            "test_id": "unit",
            "requested": True,
            "executed": False,
            "status": "SKIPPED",
            "exit_code": None,
            "duration_ms": 0,
            "log_excerpt": "not executed during preflight",
        }
        result.update(
            {
                "phase": "PREFLIGHT",
                "status": "PRECHECK_PASSED",
                "patch_check": {
                    "status": "SKIPPED",
                    "message": "not performed in preflight",
                },
                "patch_apply": {
                    "status": "SKIPPED",
                    "message": "not performed in preflight",
                },
                "tests_requested": [skipped_test],
                "tests_executed": [],
                "test_results": [],
                "sandbox_worktree_modified": False,
                "sandbox_checkout_performed": False,
                "patch_check_performed": False,
                "patch_applied": False,
                "test_execution_performed": False,
            }
        )
        return result

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
            for field_name in (
                "tests_requested",
                "tests_executed",
                "test_results",
            ):
                for test in result[field_name]:
                    if not test["requested"]:
                        errors.append(f"{field_name} includes unrequested test")
                    if not test["executed"]:
                        errors.append(f"{field_name} includes unexecuted test")
                    if test["status"] != "PASS":
                        errors.append(f"{field_name} includes non-PASS result")
            if not result["changed_files_match_expected"]:
                errors.append("changed files differ")
            if result["sandbox_destroyed"] is not True:
                errors.append("sandbox was not destroyed")
        elif result["status"] == "PRECHECK_PASSED":
            if result["phase"] != "PREFLIGHT":
                errors.append("precheck phase mismatch")
            if result["failure_class"] is not None:
                errors.append("precheck has failure_class")
            if result["failure_code"] is not None:
                errors.append("precheck has failure_code")
            if result["patch_check"]["status"] != "SKIPPED":
                errors.append("precheck performed patch check")
            if result["patch_apply"]["status"] != "SKIPPED":
                errors.append("precheck applied patch")
            if result["sandbox_checkout_performed"]:
                errors.append("precheck performed sandbox checkout")
            if result["patch_check_performed"]:
                errors.append("precheck performed patch check flag")
            if result["patch_applied"]:
                errors.append("precheck patch_applied flag")
            if result["test_execution_performed"]:
                errors.append("precheck executed tests")
            if result["tests_executed"]:
                errors.append("precheck has executed tests")
            if result["test_results"]:
                errors.append("precheck has test results")
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
        for field_name in ("tests_requested", "tests_executed", "test_results"):
            with self.subTest(field_name=field_name):
                item_properties = success_properties[field_name]["items"][
                    "properties"
                ]
                self.assertEqual(True, item_properties["requested"]["const"])
                self.assertEqual(True, item_properties["executed"]["const"])
                self.assertEqual("PASS", item_properties["status"]["const"])
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

    def test_precheck_requires_no_sandbox_or_patch_execution(self):
        properties = self.precheck_condition()
        self.assertEqual("PREFLIGHT", properties["phase"]["const"])
        self.assertEqual("SKIPPED", properties["patch_check"]["properties"]["status"]["const"])
        self.assertEqual("SKIPPED", properties["patch_apply"]["properties"]["status"]["const"])
        self.assertEqual(False, properties["sandbox_worktree_modified"]["const"])
        self.assertEqual(False, properties["sandbox_checkout_performed"]["const"])
        self.assertEqual(False, properties["patch_check_performed"]["const"])
        self.assertEqual(False, properties["patch_applied"]["const"])
        self.assertEqual(False, properties["test_execution_performed"]["const"])
        self.assertEqual(0, properties["tests_executed"]["maxItems"])
        self.assertEqual(0, properties["test_results"]["maxItems"])

    def test_contract_rejects_invalid_success_results(self):
        invalid_cases = [
            (
                "failed requested test",
                lambda result: result["tests_requested"][0].update(
                    {"status": "FAIL"}
                ),
            ),
            (
                "requested test not executed",
                lambda result: result["tests_requested"][0].update(
                    {"executed": False}
                ),
            ),
            (
                "executed test lacks result evidence",
                lambda result: result["test_results"][0].update(
                    {"executed": False}
                ),
            ),
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

    def test_precheck_contract_accepts_skipped_patch_and_tests(self):
        result = self.valid_precheck_result()
        self.assertEqual([], self.contract_errors(result))

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
            "#/$defs/test_evidence",
            properties["tests_requested"]["items"]["allOf"][0]["$ref"],
        )
        self.assertEqual(
            "#/$defs/test_evidence",
            properties["tests_executed"]["items"]["allOf"][0]["$ref"],
        )
        self.assertEqual(
            "#/$defs/test_evidence",
            properties["test_results"]["items"]["$ref"],
        )

    def test_path_schema_rejects_control_and_bidi_characters(self):
        pattern = self.schema()["$defs"]["repo_path"]["pattern"]
        compiled = re.compile(pattern)
        self.assertRegex("canary/stage2c_file.py", compiled)
        for path in (
            "canary/line\nbreak.py",
            "canary/carriage\rreturn.py",
            "canary/tab\tfile.py",
            "canary/bidi\u202efile.py",
            "canary/isolated\u2066file.py",
            ".git/config",
            "../escape.py",
        ):
            with self.subTest(path=path.encode("unicode_escape").decode()):
                self.assertIsNone(compiled.fullmatch(path))


if __name__ == "__main__":
    unittest.main()
