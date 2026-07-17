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
