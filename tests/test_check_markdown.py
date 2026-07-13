import importlib.util
import contextlib
import io
from pathlib import Path
import unittest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "check_markdown.py"
SPEC = importlib.util.spec_from_file_location("check_markdown", SCRIPT_PATH)
check_markdown = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(check_markdown)


class MarkdownCheckTests(unittest.TestCase):
    def errors_for(self, text, limit=200):
        with contextlib.redirect_stdout(io.StringIO()):
            return check_markdown.check_bytes("fixture.md", text.encode("utf-8"), limit)

    def test_multiple_headings_on_one_line_are_detected(self):
        errors = self.errors_for("# One ## Two\n")
        self.assertTrue(any("multiple headings" in error for error in errors))

    def test_multiple_bullets_on_one_line_are_detected(self):
        errors = self.errors_for("- one - two\n")
        self.assertTrue(any("multiple bullet" in error for error in errors))

    def test_concatenated_mermaid_edges_are_detected(self):
        errors = self.errors_for("```mermaid\nA --> B B --> C\n```\n")
        self.assertTrue(any("multiple Mermaid edges" in error for error in errors))

    def test_concatenated_markdown_table_rows_are_detected(self):
        text = "| A | B |\n| --- | --- |\n| 1 | 2 | | 3 | 4 |\n"
        errors = self.errors_for(text)
        self.assertTrue(any("multiple Markdown table rows" in error for error in errors))

    def test_long_normal_document_line_is_detected(self):
        errors = self.errors_for(("x" * 501) + "\n", limit=1000)
        self.assertTrue(any("normal document line length" in error for error in errors))

    def test_normal_url_code_and_table_are_not_overflagged(self):
        text = (
            "https://example.com/" + ("a" * 220) + "\n\n"
            "```text\n# not a heading ## not another heading\n"
            "- not a list - not another list\n```\n\n"
            "| A | B | C | D |\n"
            "| --- | --- | --- | --- |\n"
            "| 1 | 2 | 3 | 4 |\n"
        )
        self.assertEqual([], self.errors_for(text))


if __name__ == "__main__":
    unittest.main()
