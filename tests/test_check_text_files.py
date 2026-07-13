import contextlib
import importlib.util
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "check_text_files.py"
SPEC = importlib.util.spec_from_file_location("check_text_files", SCRIPT_PATH)
check_text_files = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = check_text_files
SPEC.loader.exec_module(check_text_files)


@contextlib.contextmanager
def chdir(path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


class TextFileCheckTests(unittest.TestCase):
    def errors_for(self, label, text):
        data = text.encode("utf-8") if isinstance(text, str) else text
        return check_text_files.check_bytes(label, data)

    def test_501_character_normal_line_fails_default_limit(self):
        errors = self.errors_for("long.txt", ("x" * 501) + "\n")
        self.assertTrue(any("line length 501 exceeds 500" in error for error in errors))

    def test_501_character_normal_line_passes_1000_limit(self):
        errors = check_text_files.check_bytes(
            "long.txt",
            (("x" * 501) + "\n").encode("utf-8"),
            max_line_length=1000,
        )
        self.assertEqual([], errors)

    def test_observed_max_length_does_not_override_allowed_limit(self):
        text_file = check_text_files.TextFile(
            path="long.txt",
            data=(("x" * 501) + "\n").encode("utf-8"),
        )
        with contextlib.redirect_stdout(io.StringIO()):
            errors = check_text_files.check_files(
                [text_file],
                check_text_files.DEFAULT_MAX_LINE_LENGTH,
            )
        self.assertTrue(any("line length 501 exceeds 500" in error for error in errors))

    def test_compressed_real_size_python_fails(self):
        compressed = "".join(f"def f{i}(): return {i}; " for i in range(40)) + "\n"
        self.assertGreater(len(compressed), 300)
        errors = self.errors_for("compressed.py", compressed)
        self.assertTrue(
            any("Python file has only 1 physical lines" in error for error in errors)
        )

    def test_hundred_line_equivalent_python_collapsed_to_one_line_fails(self):
        normal_lines = [f"def function_{index}():\n    return {index}\n" for index in range(50)]
        collapsed = " ".join(line.replace("\n", " ") for line in normal_lines) + "\n"
        errors = self.errors_for("runtime/rogue/collapsed.py", collapsed)
        self.assertTrue(
            any("Python file has only 1 physical lines" in error for error in errors)
        )

    def test_four_line_large_python_fails_density_check(self):
        collapsed_lines = [
            " ".join(f"def f{index}_{part}(): return {part};" for part in range(20))
            for index in range(4)
        ]
        errors = self.errors_for("runtime/rogue/collapsed4.py", "\n".join(collapsed_lines))
        self.assertTrue(
            any("bytes per physical line" in error for error in errors)
        )

    def test_concatenated_python_imports_are_detected(self):
        bad_source = (
            "import os "
            "import sys\n"
        )
        errors = self.errors_for("bad.py", bad_source)
        self.assertTrue(
            any("multiple Python import statements" in error for error in errors)
        )

    def test_normal_python_passes(self):
        text = "import os\n\n\ndef main():\n    return os.name\n"
        self.assertEqual([], self.errors_for("good.py", text))

    def test_runtime_rogue_and_tests_paths_are_text_targets(self):
        self.assertTrue(check_text_files.target_text_path("runtime/rogue/adapter.py"))
        self.assertTrue(check_text_files.target_text_path("tests/test_rogue_domain_adapter.py"))
        self.assertIsNone(check_text_files.allowlist_reason("runtime/rogue/adapter.py"))
        self.assertIsNone(
            check_text_files.allowlist_reason("tests/test_rogue_domain_adapter.py")
        )

    def test_long_url_is_not_overflagged(self):
        url = "https://example.com/" + ("a" * 600) + "\n"
        self.assertEqual([], self.errors_for("links.md", url))

    def test_bidi_character_is_detected(self):
        errors = self.errors_for("bad.md", "safe\u202etext\n")
        self.assertTrue(any("Unicode bidi control character" in error for error in errors))

    def test_crlf_is_detected(self):
        errors = self.errors_for("bad.py", b"import os\r\n")
        self.assertTrue(any("CRLF line endings" in error for error in errors))

    @unittest.skipIf(shutil.which("git") is None, "git is not available")
    def test_worktree_and_git_blob_modes_apply_same_line_limit(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            with chdir(repo):
                subprocess.run(["git", "init"], check=True, stdout=subprocess.PIPE)
                subprocess.run(
                    ["git", "config", "core.autocrlf", "false"],
                    check=True,
                    stdout=subprocess.PIPE,
                )
                Path("long.txt").write_text(
                    ("x" * 501) + "\n",
                    encoding="utf-8",
                    newline="\n",
                )
                subprocess.run(["git", "add", "long.txt"], check=True)
                subprocess.run(
                    [
                        "git",
                        "-c",
                        "user.email=test@example.com",
                        "-c",
                        "user.name=Test",
                        "commit",
                        "-m",
                        "fixture",
                    ],
                    check=True,
                    stdout=subprocess.PIPE,
                )
                with contextlib.redirect_stdout(io.StringIO()):
                    worktree_errors = check_text_files.check_files(
                        check_text_files.worktree_text_files(),
                        check_text_files.DEFAULT_MAX_LINE_LENGTH,
                    )
                    git_blob_errors = check_text_files.check_files(
                        check_text_files.git_ref_text_files("HEAD"),
                        check_text_files.DEFAULT_MAX_LINE_LENGTH,
                    )
        self.assertTrue(
            any("line length 501 exceeds 500" in error for error in worktree_errors)
        )
        self.assertTrue(
            any("line length 501 exceeds 500" in error for error in git_blob_errors)
        )

    @unittest.skipIf(shutil.which("git") is None, "git is not available")
    def test_git_blob_mode_detects_concatenated_python_in_runtime_rogue(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            with chdir(repo):
                subprocess.run(["git", "init"], check=True, stdout=subprocess.PIPE)
                subprocess.run(
                    ["git", "config", "core.autocrlf", "false"],
                    check=True,
                    stdout=subprocess.PIPE,
                )
                Path("runtime/rogue").mkdir(parents=True)
                bad_source = " ".join(
                    f"def collapsed_{index}(): return {index};"
                    for index in range(50)
                )
                Path("runtime/rogue/collapsed.py").write_text(
                    bad_source + "\n",
                    encoding="utf-8",
                    newline="\n",
                )
                subprocess.run(["git", "add", "runtime/rogue/collapsed.py"], check=True)
                subprocess.run(
                    [
                        "git",
                        "-c",
                        "user.email=test@example.com",
                        "-c",
                        "user.name=Test",
                        "commit",
                        "-m",
                        "fixture",
                    ],
                    check=True,
                    stdout=subprocess.PIPE,
                )
                with contextlib.redirect_stdout(io.StringIO()):
                    files = check_text_files.git_ref_text_files("HEAD")
                    errors = check_text_files.check_files(
                        files,
                        check_text_files.DEFAULT_MAX_LINE_LENGTH,
                    )
        self.assertTrue(
            any("Python file has only 1 physical lines" in error for error in errors)
        )

    @unittest.skipIf(shutil.which("git") is None, "git is not available")
    def test_git_blob_mode_detects_concatenated_python_in_tests_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            with chdir(repo):
                subprocess.run(["git", "init"], check=True, stdout=subprocess.PIPE)
                subprocess.run(
                    ["git", "config", "core.autocrlf", "false"],
                    check=True,
                    stdout=subprocess.PIPE,
                )
                Path("tests").mkdir()
                bad_source = " ".join(
                    f"def collapsed_test_{index}(): return {index};"
                    for index in range(50)
                )
                Path("tests/test_collapsed.py").write_text(
                    bad_source + "\n",
                    encoding="utf-8",
                    newline="\n",
                )
                subprocess.run(["git", "add", "tests/test_collapsed.py"], check=True)
                subprocess.run(
                    [
                        "git",
                        "-c",
                        "user.email=test@example.com",
                        "-c",
                        "user.name=Test",
                        "commit",
                        "-m",
                        "fixture",
                    ],
                    check=True,
                    stdout=subprocess.PIPE,
                )
                with contextlib.redirect_stdout(io.StringIO()):
                    files = check_text_files.git_ref_text_files("HEAD")
                    errors = check_text_files.check_files(
                        files,
                        check_text_files.DEFAULT_MAX_LINE_LENGTH,
                    )
        self.assertTrue(
            any("Python file has only 1 physical lines" in error for error in errors)
        )


if __name__ == "__main__":
    unittest.main()
