from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts import check_source_completeness
from scripts import compare_source_tree
from scripts import hash_tree


class HashTreeTests(unittest.TestCase):
    def test_same_tree_has_same_tree_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.txt").write_text("alpha\n", encoding="utf-8")
            (root / "sub").mkdir()
            (root / "sub" / "b.txt").write_text("beta\n", encoding="utf-8")

            first = hash_tree.hash_tree(root, hash_tree.DEFAULT_IGNORE_DIRS)
            second = hash_tree.hash_tree(root, hash_tree.DEFAULT_IGNORE_DIRS)

        self.assertEqual(first["tree_sha256"], second["tree_sha256"])

    def test_file_content_change_changes_tree_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "a.txt"
            target.write_text("alpha\n", encoding="utf-8")
            before = hash_tree.hash_tree(root, hash_tree.DEFAULT_IGNORE_DIRS)
            target.write_text("changed\n", encoding="utf-8")
            after = hash_tree.hash_tree(root, hash_tree.DEFAULT_IGNORE_DIRS)

        self.assertNotEqual(before["tree_sha256"], after["tree_sha256"])


class SourceCompletenessTests(unittest.TestCase):
    def test_parse_makefile_multiline_variable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            makefile = Path(tmp) / "Makefile.in"
            makefile.write_text(
                "CFILES = main.c \\\n"
                "         io.c \\\n"
                "         new_level.c\n"
                "HDRS = rogue.h\n",
                encoding="utf-8",
            )

            parsed = check_source_completeness.parse_makefile(
                makefile,
                {"CFILES", "HDRS"},
            )

        self.assertEqual(parsed["CFILES"], ["main.c", "io.c", "new_level.c"])
        self.assertEqual(parsed["HDRS"], ["rogue.h"])

    def test_missing_makefile_file_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Makefile.in").write_text(
                "CFILES = main.c missing.c\n",
                encoding="utf-8",
            )
            (root / "main.c").write_text("int main(void) { return 0; }\n", encoding="utf-8")

            report = check_source_completeness.check_tree(
                root,
                Path("Makefile.in"),
                {"CFILES"},
                [],
            )

        self.assertEqual(report["missing_from_makefile"], ["missing.c"])

    def test_required_file_missing_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Makefile.in").write_text("CFILES = main.c\n", encoding="utf-8")
            (root / "main.c").write_text("int main(void) { return 0; }\n", encoding="utf-8")

            report = check_source_completeness.check_tree(
                root,
                Path("Makefile.in"),
                {"CFILES"},
                ["LICENSE.TXT"],
            )

        self.assertEqual(report["required_missing"], ["LICENSE.TXT"])


class CompareSourceTreeTests(unittest.TestCase):
    def test_added_deleted_and_changed_files_are_classified(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "base"
            local = Path(tmp) / "local"
            base.mkdir()
            local.mkdir()
            (base / "same.txt").write_text("same\n", encoding="utf-8")
            (local / "same.txt").write_text("same\n", encoding="utf-8")
            (base / "changed.txt").write_text("base\n", encoding="utf-8")
            (local / "changed.txt").write_text("local\n", encoding="utf-8")
            (base / "only-left.txt").write_text("left\n", encoding="utf-8")
            (local / "only-right.txt").write_text("right\n", encoding="utf-8")

            report = compare_source_tree.compare(
                base,
                local,
                compare_source_tree.DEFAULT_IGNORE_DIRS,
                compare_source_tree.DEFAULT_IGNORE_NAMES,
                compare_source_tree.DEFAULT_IGNORE_SUFFIXES,
            )

        self.assertEqual(report["same"], ["same.txt"])
        self.assertEqual([item["path"] for item in report["changed"]], ["changed.txt"])
        self.assertEqual(report["only_left"], ["only-left.txt"])
        self.assertEqual(report["only_right"], ["only-right.txt"])

    def test_crlf_and_lf_only_difference_is_normalized_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            left = Path(tmp) / "left"
            right = Path(tmp) / "right"
            left.mkdir()
            right.mkdir()
            (left / "text.txt").write_bytes(b"line1\nline2\n")
            (right / "text.txt").write_bytes(b"line1\r\nline2\r\n")

            report = compare_source_tree.compare(
                left,
                right,
                compare_source_tree.DEFAULT_IGNORE_DIRS,
                compare_source_tree.DEFAULT_IGNORE_NAMES,
                compare_source_tree.DEFAULT_IGNORE_SUFFIXES,
            )

        self.assertEqual(report["same_normalized_text"], ["text.txt"])
        self.assertEqual(report["changed"], [])

    def test_binary_files_are_not_text_normalized(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            left = Path(tmp) / "left"
            right = Path(tmp) / "right"
            left.mkdir()
            right.mkdir()
            (left / "data.bin").write_bytes(b"\x00left\n")
            (right / "data.bin").write_bytes(b"\x00right\r\n")

            report = compare_source_tree.compare(
                left,
                right,
                compare_source_tree.DEFAULT_IGNORE_DIRS,
                compare_source_tree.DEFAULT_IGNORE_NAMES,
                compare_source_tree.DEFAULT_IGNORE_SUFFIXES,
            )

        self.assertEqual(report["same_normalized_text"], [])
        self.assertEqual([item["path"] for item in report["changed"]], ["data.bin"])


if __name__ == "__main__":
    unittest.main()
