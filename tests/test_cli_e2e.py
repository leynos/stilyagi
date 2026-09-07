"""End-to-end subprocess coverage for the `stilyagi check` command."""

import subprocess  # ruff: ignore[suspicious-subprocess-import] - tests invoke a trusted local interpreter.
import sys
import typing as typ

import pytest

from tests.support.assertions import assert_with_context
from tests.support.malformed_corpus import materialize_malformed_corpus
from tests.support.subprocess_env import python_module_environment

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    import pathlib


def test_python_module_entrypoint_exits_zero_for_a_malformed_markdown_tree(
    tmp_path: pathlib.Path,
) -> None:
    """A malformed Markdown tree should still recover cleanly in this slice."""
    materialize_malformed_corpus(tmp_path / "docs")

    completed = _run_check(tmp_path)

    assert completed.returncode == 0, "expected completed.returncode == 0"
    assert_with_context(
        completed.stdout.startswith("checked "),
        "expected completed.stdout to begin with the run summary",
    )
    assert not completed.stderr, "expected not completed.stderr"


def test_python_module_entrypoint_exits_two_for_invalid_configuration(
    tmp_path: pathlib.Path,
) -> None:
    """A malformed discovered config should fail at the subprocess boundary."""
    (tmp_path / "stilyagi.toml").write_text("[lint\n", encoding="utf-8")
    _write_markdown(tmp_path / "docs" / "notes.md", "Notes")

    completed = _run_check(tmp_path)

    assert completed.returncode == 2, "expected completed.returncode == 2"
    assert not completed.stdout, "expected not completed.stdout"
    assert_with_context(
        "stilyagi check:" in completed.stderr,
        "expected 'stilyagi check:' in completed.stderr",
    )
    assert_with_context(
        "toml" in completed.stderr.lower(),
        "expected 'toml' in completed.stderr.lower()",
    )


def _run_check(cwd: pathlib.Path) -> subprocess.CompletedProcess[str]:
    """Run `python -m stilyagi check .` with the local package importable."""
    return subprocess.run(
        [sys.executable, "-m", "stilyagi", "check", "."],
        cwd=cwd,
        env=python_module_environment(),
        capture_output=True,
        check=False,
        text=True,
    )


def _write_markdown(path: pathlib.Path, title: str) -> None:
    """Write one tiny Markdown file for the subprocess tree."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {title}\n", encoding="utf-8")


def _write_source(path: pathlib.Path, source: str) -> None:
    """Write source text for a mixed-source subprocess tree."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


def _populate_clean_markdown_tree(root: pathlib.Path) -> None:
    """Populate a clean tree containing two Markdown documents."""
    _write_markdown(root / "docs" / "alpha.md", "Alpha")
    _write_markdown(root / "docs" / "beta.md", "Beta")


def _populate_clean_mixed_source_tree(root: pathlib.Path) -> None:
    """Populate a clean tree containing supported Markdown and source files."""
    _write_markdown(root / "docs" / "guide.md", "Guide")
    _write_source(root / "src" / "app.py", '"""Module docs."""\n')
    _write_source(root / "src" / "lib.rs", "//! Crate docs.\n")


@pytest.mark.parametrize(
    ("populate_tree", "expected_checked_files"),
    [
        pytest.param(_populate_clean_markdown_tree, 2, id="markdown"),
        pytest.param(_populate_clean_mixed_source_tree, 3, id="mixed-source"),
    ],
)
def test_python_module_entrypoint_exits_zero_for_a_clean_tree(
    tmp_path: pathlib.Path,
    populate_tree: cabc.Callable[[pathlib.Path], None],
    expected_checked_files: int,
) -> None:
    """A clean supported-source tree should succeed through the module boundary."""
    populate_tree(tmp_path)

    completed = _run_check(tmp_path)

    assert completed.returncode == 0, "expected completed.returncode == 0"
    assert_with_context(
        completed.stdout
        == (
            f"checked {expected_checked_files} files (0 skipped, 0 unreadable); "
            "0 errors, 0 warnings\n"
        ),
        "expected completed.stdout to carry the clean-run summary",
    )
    assert not completed.stderr, "expected not completed.stderr"
