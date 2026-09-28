"""End-to-end subprocess coverage for the `stilyagi check` command."""

import subprocess  # ruff: ignore[suspicious-subprocess-import] - tests invoke a trusted local interpreter.
import sys
import typing as typ

from stilyagi import cli_fix

from tests.support.assertions import assert_with_context
from tests.support.malformed_corpus import materialize_malformed_corpus
from tests.support.subprocess_env import python_module_environment

if typ.TYPE_CHECKING:
    import pathlib


def test_python_module_entrypoint_exits_zero_for_a_clean_markdown_tree(
    tmp_path: pathlib.Path,
) -> None:
    """A clean Markdown tree should succeed through the module boundary."""
    _write_markdown(tmp_path / "docs" / "alpha.md", "Alpha")
    _write_markdown(tmp_path / "docs" / "beta.md", "Beta")

    completed = _run_check(tmp_path)

    assert completed.returncode == 0, "expected completed.returncode == 0"
    assert_with_context(
        completed.stdout == "0 diagnostics found (0 safe fixes, 0 unsafe fixes)\n",
        "expected completed.stdout to include fix counts",
    )
    assert not completed.stderr, "expected not completed.stderr"


def test_python_module_entrypoint_exits_zero_for_a_malformed_markdown_tree(
    tmp_path: pathlib.Path,
) -> None:
    """A malformed Markdown tree should still recover cleanly in this slice."""
    materialize_malformed_corpus(tmp_path / "docs")

    completed = _run_check(tmp_path)

    assert completed.returncode == 0, "expected completed.returncode == 0"
    assert_with_context(
        completed.stdout == "0 diagnostics found (0 safe fixes, 0 unsafe fixes)\n",
        "expected completed.stdout to include fix counts",
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


def test_python_module_entrypoint_rejects_fix_with_diff(
    tmp_path: pathlib.Path,
) -> None:
    """A mutating flag combined with a preview flag fails before doing work.

    D-06: silent precedence is the surprise the CLI contract exists to prevent,
    so the pair is rejected rather than given an implicit winner. This is
    asserted across a real process boundary because the in-process tests inject
    a reporter, and the default reporter is what decides where a user sees the
    message.

    The message appears twice on purpose, and that is the reporter's documented
    contract rather than a defect: `report_check_error` logs every expected
    failure at warning level and echoes it to standard error, so one line
    survives a logging configuration that swallows the other. The assertion
    counts occurrences rather than testing for presence, because a third
    printing would mean a duplicate call site crept back in -- the shape this
    test was written to catch.
    """
    _write_markdown(tmp_path / "docs" / "notes.md", "Notes")

    completed = _run_check(tmp_path, "--fix", "--diff")

    assert completed.returncode == 2, "expected a rejected flag pair to exit two"
    assert not completed.stdout, "expected the usage error on standard error"
    assert_with_context(
        completed.stderr.count("--fix and --diff cannot be combined") == 2,
        "expected the reporter's log line and echo, and nothing further",
    )


def test_python_module_entrypoint_leaves_a_clean_tree_untouched_under_fix(
    tmp_path: pathlib.Path,
) -> None:
    """`--fix` over a tree with nothing to fix must not claim a mutation.

    This is the defect Revision 36 repaired, pinned where it actually appeared.
    The planner used to offer the source as its own replacement when no edit
    survived, so the run counted a written file and printed the re-run note
    while `write_source` skipped the write -- a run that left the tree
    untouched reported that it had changed it.

    The tree is deliberately malformed: this slice's rule engine reports
    nothing, so a malformed file is the honest way to be sure the run has no
    fixable diagnostic and still has real Markdown to read and extract. The
    byte comparison is the load-bearing assertion -- the absence of the note is
    what the defect violated, but a run that rewrote the file identically would
    also print nothing, so the file's own bytes are checked as well.
    """
    materialize_malformed_corpus(tmp_path / "docs")
    before = _tree_bytes(tmp_path)

    completed = _run_check(tmp_path, "--fix")

    assert completed.returncode == 0, "expected a clean tree to exit zero"
    assert_with_context(
        cli_fix.RERUN_HINT not in completed.stderr,
        "expected no re-run note for a run that wrote nothing",
    )
    assert_with_context(
        before == _tree_bytes(tmp_path),
        "expected --fix to leave a tree with no fixable diagnostic untouched",
    )


def test_python_module_entrypoint_treats_unsafe_fixes_without_fix_as_a_no_op(
    tmp_path: pathlib.Path,
) -> None:
    """`--unsafe-fixes` alone is accepted and changes nothing.

    Reported as a no-op rather than a usage error because that is what the
    shipped flag help promises ("Requires --fix to take effect"), and the
    assertion is on the observable outcome: the exit status matches a plain
    check, the report is the ordinary one, and the tree is byte-identical.
    """
    _write_markdown(tmp_path / "docs" / "notes.md", "Notes")
    before = _tree_bytes(tmp_path)

    completed = _run_check(tmp_path, "--unsafe-fixes")

    assert completed.returncode == 0, "expected --unsafe-fixes alone to exit zero"
    assert_with_context(
        completed.stdout == "0 diagnostics found (0 safe fixes, 0 unsafe fixes)\n",
        "expected the ordinary report when --unsafe-fixes has no --fix to modify",
    )
    assert_with_context(
        before == _tree_bytes(tmp_path),
        "expected --unsafe-fixes alone to leave the tree untouched",
    )


def test_python_module_entrypoint_keeps_standard_output_clean_for_a_diff(
    tmp_path: pathlib.Path,
) -> None:
    """`--diff` reserves standard output for the patch alone.

    The machine artefact owns that stream so `stilyagi check --diff | git apply`
    stays usable, which means the ordinary summary has to move to standard
    error. A clean tree produces no patch at all, so the contract here is an
    empty standard output alongside the summary -- not an empty stream in both.

    The exit status is zero because nothing would be produced and no diagnostic
    remains. That is asserted rather than inferred: a preview that exits one on
    an empty patch would make the flag unusable in a pipeline that checks for
    the success status.
    """
    _write_markdown(tmp_path / "docs" / "notes.md", "Notes")

    completed = _run_check(tmp_path, "--diff")

    assert completed.returncode == 0, "expected an empty preview to exit zero"
    assert_with_context(
        not completed.stdout,
        "expected standard output to hold only the patch, which is empty here",
    )
    assert_with_context(
        completed.stderr == "0 diagnostics found (0 safe fixes, 0 unsafe fixes)\n",
        "expected the summary to move to standard error under --diff",
    )


def _tree_bytes(root: pathlib.Path) -> dict[str, bytes]:
    """Return every file under ``root`` mapped to its bytes.

    Returns
    -------
    dict[str, bytes]
        Relative POSIX path to contents, for comparing a tree before and after
        a run without assuming which files the run might have touched.
    """
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _run_check(cwd: pathlib.Path, *flags: str) -> subprocess.CompletedProcess[str]:
    """Run `python -m stilyagi check .` with the local package importable.

    Parameters
    ----------
    cwd:
        The directory to run in, which is also the discovered target.
    *flags:
        Extra command-line flags, inserted after the subcommand so a caller can
        exercise a mutating or preview mode without a second helper.

    Returns
    -------
    subprocess.CompletedProcess
        The finished process, with its streams captured as text.
    """
    return subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] - trusted interpreter, fixed flags, no shell.
        [sys.executable, "-m", "stilyagi", "check", *flags, "."],
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
