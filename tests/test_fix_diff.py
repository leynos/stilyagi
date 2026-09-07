"""Contracts for rendering byte-faithful safe-fix diffs."""

import pathlib
import shutil
import subprocess  # ruff: ignore[suspicious-subprocess-import] -- tests invoke a resolved Git executable.

import pytest
from stilyagi.engine.fix_planning.diff import unified_diff

from tests.support.assertions import assert_with_context

_CRLF_FIXTURES = (
    pathlib.Path(
        "tests/fixtures/corpus/markdown/valid/paragraph-soft-break-crlf.md.fixture"
    ),
    pathlib.Path("tests/fixtures/corpus/markdown/valid/list-crlf.md.fixture"),
    pathlib.Path("tests/fixtures/corpus/markdown/valid/blockquote-crlf.md.fixture"),
)


def test_unified_diff_is_empty_when_text_is_unchanged() -> None:
    """Avoid emitting an empty patch for equal before and after text."""
    assert_with_context(
        not unified_diff("Same\n", "Same\n", "docs/notes.md"),
        "expected equal text to produce no diff",
    )


def test_unified_diff_is_accepted_by_git_apply(
    tmp_path: pathlib.Path,
) -> None:
    """Produce a patch that Git accepts against the original file."""
    source_path = tmp_path / "notes.md"
    before = "Before\\n"
    after = "After\\n"
    source_path.write_text(before, encoding="utf-8", newline="")
    _run_git(tmp_path, "init")

    patch = unified_diff(before, after, "notes.md")
    completed = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] -- fixed Git subcommand and test-controlled patch.
        (_git_executable(), "apply", "--check"),
        cwd=tmp_path,
        input=patch,
        text=True,
        capture_output=True,
        check=False,
    )

    assert_with_context(
        completed.returncode == 0,
        f"expected git apply --check to accept patch: {completed.stderr}",
    )


@pytest.mark.parametrize("fixture_path", _CRLF_FIXTURES)
def test_unified_diff_preserves_crlf_fixture_line_endings(
    fixture_path: pathlib.Path,
) -> None:
    """Retain CRLF line endings in patches made from shipped fixtures."""
    before = fixture_path.read_bytes().decode("utf-8")
    after = before.replace(" ", "  ", 1)

    patch = unified_diff(before, after, fixture_path.name)

    assert_with_context("\r\n" in patch, "expected CRLF content in the patch")


def test_unified_diff_marks_a_missing_final_newline() -> None:
    """Preserve a file's lack of a trailing line ending in its patch."""
    patch = unified_diff("Before", "After", "notes.md")

    assert_with_context(
        "\\ No newline at end of file" in patch,
        "expected the patch to mark both missing final newlines",
    )


def _run_git(cwd: pathlib.Path, *arguments: str) -> None:
    """Run one fixed Git setup command in a temporary repository."""
    subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] -- fixed Git setup command in a temporary repository.
        (_git_executable(), *arguments),
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


def _git_executable() -> str:
    """Return the resolved Git executable or skip when Git is unavailable."""
    executable = shutil.which("git")
    if executable is None:
        pytest.skip("Git is required to validate unified patches.")
    return executable
