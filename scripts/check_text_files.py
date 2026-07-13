#!/usr/bin/env python3
"""Check tracked text files for physical-line formatting hazards."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path


TARGET_EXTENSIONS = {
    ".c",
    ".cc",
    ".cpp",
    ".cxx",
    ".cfg",
    ".h",
    ".hh",
    ".hpp",
    ".hxx",
    ".ini",
    ".json",
    ".md",
    ".ps1",
    ".py",
    ".sh",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
DEFAULT_MAX_LINE_LENGTH = 500
PYTHON_SUSPICIOUS_LINE_COUNT = 4
PYTHON_SUSPICIOUS_MIN_BYTES = 300
PYTHON_SUSPICIOUS_BYTES_PER_LINE = 250
PYTHON_MIN_LINES_FOR_LARGE_FILE = 10
PYTHON_LARGE_FILE_BYTES = 1000
C_MIN_LINES_FOR_LARGE_FILE = 20
C_LARGE_FILE_BYTES = 1000
BIDI_CODEPOINTS = {
    0x061C,
    0x200E,
    0x200F,
    0x202A,
    0x202B,
    0x202C,
    0x202D,
    0x202E,
    0x2066,
    0x2067,
    0x2068,
    0x2069,
}
IMPORT_STATEMENT_RE = re.compile(
    r"(?<!\w)(?:import\s+[A-Za-z_][\w.]*|from\s+[A-Za-z_][\w.]*\s+import\s+\S+)"
)
FROM_IMPORT_STATEMENT_RE = re.compile(
    r"(?<!\w)from\s+[A-Za-z_][\w.]*\s+import\s+\S+"
)
CLASS_OR_DEF_RE = re.compile(r"(?<!\w)(?:class|def)\s+[A-Za-z_]\w*")
DOCSTRING_END_THEN_CODE_RE = re.compile(
    r"(?:\"\"\"|''')\s*(?:from\s+[A-Za-z_][\w.]*\s+import|import\s+[A-Za-z_][\w.]*|class\s+[A-Za-z_]\w*)"
)
C_PREPROCESSOR_RE = re.compile(r"#\s*(?:ifndef|define|include)\b")
C_DEFINE_RE = re.compile(r"#\s*define\b")
C_TYPEDEF_RE = re.compile(r"\btypedef\b")
C_FUNCTION_PROTOTYPE_RE = re.compile(
    r"\b[A-Za-z_][A-Za-z0-9_\s\*]*\s+[A-Za-z_][A-Za-z0-9_]*\s*\([^;{}]*\)\s*;"
)


@dataclass(frozen=True)
class TextFile:
    path: str
    data: bytes


def normalized_path(path: str | Path) -> str:
    return str(path).replace("\\", "/")


def target_text_path(path: str) -> bool:
    return Path(path).suffix.lower() in TARGET_EXTENSIONS


def allowlist_reason(path: str) -> str | None:
    normalized = normalized_path(path)
    if normalized.startswith("rogue/pristine/rogue5.4.4/"):
        return "pristine Rogue source"
    if normalized.startswith("patches/") and normalized.endswith(".patch"):
        return "patch source text"
    return None


def is_binary(data: bytes) -> bool:
    return b"\0" in data[:4096]


def is_url_only_line(text: str) -> bool:
    stripped = text.strip()
    return stripped.startswith(("http://", "https://")) and " " not in stripped


def line_length(line: bytes) -> int:
    return len(line.decode("utf-8", errors="replace"))


def format_characters(text: str) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for column, char in enumerate(text, start=1):
        if unicodedata.category(char) == "Cf":
            found.append((column, f"U+{ord(char):04X}"))
    return found


def bidi_characters(text: str) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for column, char in enumerate(text, start=1):
        if ord(char) in BIDI_CODEPOINTS:
            found.append((column, f"U+{ord(char):04X}"))
    return found


def check_python_line(label: str, line_number: int, text: str) -> list[str]:
    errors: list[str] = []
    if len(IMPORT_STATEMENT_RE.findall(text)) > 1:
        errors.append(f"{label}:{line_number}: multiple Python import statements on one line")
    if len(FROM_IMPORT_STATEMENT_RE.findall(text)) > 1:
        errors.append(f"{label}:{line_number}: multiple Python from-import statements on one line")
    if len(CLASS_OR_DEF_RE.findall(text)) > 1:
        errors.append(f"{label}:{line_number}: multiple Python class/def blocks on one line")
    if "cl" "ass " in text and "de" "f " in text:
        errors.append(
            f"{label}:{line_number}: Python class/function collision on one line"
        )
    if DOCSTRING_END_THEN_CODE_RE.search(text):
        errors.append(f"{label}:{line_number}: Python docstring closes before code on same line")
    return errors


def check_c_like_line(label: str, line_number: int, text: str) -> list[str]:
    errors: list[str] = []
    if len(C_DEFINE_RE.findall(text)) > 1:
        errors.append(f"{label}:{line_number}: multiple C #define directives on one line")
    if len(C_PREPROCESSOR_RE.findall(text)) > 1:
        errors.append(f"{label}:{line_number}: multiple C preprocessor directives on one line")
    if len(C_TYPEDEF_RE.findall(text)) > 1:
        errors.append(f"{label}:{line_number}: multiple C typedefs on one line")
    if len(C_FUNCTION_PROTOTYPE_RE.findall(text)) > 1:
        errors.append(f"{label}:{line_number}: multiple C function prototypes on one line")
    return errors


def check_bytes(
    label: str,
    data: bytes,
    *,
    max_line_length: int = DEFAULT_MAX_LINE_LENGTH,
) -> list[str]:
    errors: list[str] = []
    if is_binary(data):
        return errors

    try:
        text_data = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        return [f"{label}: invalid UTF-8 at byte {exc.start}"]

    if b"\r\n" in data:
        errors.append(f"{label}: CRLF line endings detected")

    raw_lines = data.splitlines()
    suffix = Path(label.split(":", 1)[-1]).suffix.lower()
    if suffix == ".py" and len(data) >= PYTHON_LARGE_FILE_BYTES and len(raw_lines) < PYTHON_MIN_LINES_FOR_LARGE_FILE:
        errors.append(
            f"{label}: Python file has only {len(raw_lines)} physical lines "
            f"for {len(data)} bytes"
        )
    if (
        suffix == ".py"
        and len(raw_lines) <= PYTHON_SUSPICIOUS_LINE_COUNT
        and len(data) >= PYTHON_SUSPICIOUS_MIN_BYTES
    ):
        errors.append(
            f"{label}: Python file has only {len(raw_lines)} physical lines "
            f"for {len(data)} bytes"
        )
    if (
        suffix == ".py"
        and len(raw_lines) > 0
        and len(data) >= PYTHON_SUSPICIOUS_MIN_BYTES
        and len(data) // len(raw_lines) >= PYTHON_SUSPICIOUS_BYTES_PER_LINE
    ):
        errors.append(
            f"{label}: Python file averages {len(data) // len(raw_lines)} "
            f"bytes per physical line across {len(raw_lines)} lines"
        )
    if (
        suffix in {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx"}
        and len(data) >= C_LARGE_FILE_BYTES
        and len(raw_lines) < C_MIN_LINES_FOR_LARGE_FILE
    ):
        errors.append(
            f"{label}: C-like file has only {len(raw_lines)} physical lines "
            f"for {len(data)} bytes"
        )

    for line_number, raw_line in enumerate(raw_lines, start=1):
        text = raw_line.decode("utf-8", errors="replace")
        length = line_length(raw_line)
        if length > max_line_length and not is_url_only_line(text):
            errors.append(
                f"{label}:{line_number}: line length {length} exceeds "
                f"{max_line_length}"
            )
        for column, codepoint in bidi_characters(text):
            errors.append(
                f"{label}:{line_number}:{column}: Unicode bidi control "
                f"character {codepoint} detected"
            )
        for column, codepoint in format_characters(text):
            errors.append(
                f"{label}:{line_number}:{column}: Unicode format character "
                f"{codepoint} detected"
            )
        if suffix == ".py":
            errors.extend(check_python_line(label, line_number, text))
        if suffix in {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx"}:
            errors.extend(check_c_like_line(label, line_number, text))

    if not text_data and data:
        errors.append(f"{label}: empty decoded text from non-empty data")
    return errors


def git_tracked_paths(ref: str | None = None) -> list[str]:
    if ref:
        command = ["git", "ls-tree", "-r", "--name-only", ref]
    else:
        command = ["git", "ls-files"]
    proc = subprocess.run(
        command,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return [
        normalized_path(line)
        for line in proc.stdout.decode("utf-8").splitlines()
        if target_text_path(line)
    ]


def read_git_blob(ref: str, path: str) -> bytes:
    proc = subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return proc.stdout


def worktree_text_files() -> list[TextFile]:
    files: list[TextFile] = []
    for path in git_tracked_paths():
        reason = allowlist_reason(path)
        if reason:
            print(f"SKIP {path}: {reason}")
            continue
        files.append(TextFile(path=path, data=Path(path).read_bytes()))
    return files


def git_ref_text_files(ref: str) -> list[TextFile]:
    files: list[TextFile] = []
    for path in git_tracked_paths(ref):
        reason = allowlist_reason(path)
        if reason:
            print(f"SKIP {ref}:{path}: {reason}")
            continue
        files.append(TextFile(path=f"{ref}:{path}", data=read_git_blob(ref, path)))
    return files


def check_files(files: list[TextFile], allowed_max_line_length: int) -> list[str]:
    errors: list[str] = []
    for text_file in files:
        raw_lines = text_file.data.splitlines()
        observed_max_length = max((line_length(line) for line in raw_lines), default=0)
        print(
            f"{text_file.path}: lines={len(raw_lines)} "
            f"max_line_length={observed_max_length}"
        )
        errors.extend(
            check_bytes(
                text_file.path,
                text_file.data,
                max_line_length=allowed_max_line_length,
            )
        )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--git-ref",
        help="check tracked text blobs from a git ref instead of the working tree",
    )
    parser.add_argument(
        "--max-line-length",
        type=int,
        default=DEFAULT_MAX_LINE_LENGTH,
        help=f"maximum allowed physical line length, default {DEFAULT_MAX_LINE_LENGTH}",
    )
    args = parser.parse_args()

    files = (
        git_ref_text_files(args.git_ref)
        if args.git_ref
        else worktree_text_files()
    )
    errors = check_files(files, args.max_line_length)
    for error in errors:
        print(error, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
