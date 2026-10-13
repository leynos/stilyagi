"""End-to-end subprocess coverage for the `stilyagi check` command."""

import subprocess  # ruff: ignore[suspicious-subprocess-import] - tests invoke a trusted local interpreter.
import sys
import typing as typ

import pytest
from stilyagi import cli_fix

from tests.support.assertions import assert_with_context
from tests.support.malformed_corpus import materialize_malformed_corpus
from tests.support.subprocess_env import python_module_environment

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    import pathlib


def _clean_markdown_tree(root: pathlib.Path) -> None:
    """Write two tiny well-formed files under ``root``."""
    _write_markdown(root / "docs" / "alpha.md", "Alpha")
    _write_markdown(root / "docs" / "beta.md", "Beta")


def _malformed_markdown_tree(root: pathlib.Path) -> None:
    """Materialize the shared malformed corpus under ``root``."""
    materialize_malformed_corpus(root / "docs")


@pytest.mark.parametrize(
    "materialize",
    [_clean_markdown_tree, _malformed_markdown_tree],
    ids=["clean", "malformed"],
)
def test_python_module_entrypoint_exits_zero_for_a_recoverable_tree(
    tmp_path: pathlib.Path,
    materialize: cabc.Callable[[pathlib.Path], None],
) -> None:
    """A tree this slice recovers from should succeed through the module boundary.

    The clean and malformed cases are one behaviour, not two: this slice's rule
    engine reports nothing, so a malformed file is the honest way to prove the
    boundary survives real Markdown it cannot yet fix. They are kept as separate
    cases rather than one case with a merged tree because the clean tree is the
    shape a user actually hits, and a regression confined to either one should
    name the tree that broke.
    """
    materialize(tmp_path)

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


def test_python_module_entrypoint_rejects_fix_with_diff(
    tmp_path: pathlib.Path,
) -> None:
    """A mutating flag combined with a preview flag fails before doing work.

    D-06: silent precedence is the surprise the CLI contract exists to prevent,
    so the pair is rejected rather than given an implicit winner. This is
    asserted across a real process boundary because the in-process tests inject
    a reporter, and the default reporter is what decides where a user sees the
    message.

    The message appears exactly once. The command logger's own handler renders
    it and suppresses propagation, so no second copy can arrive from a root
    handler -- the assertion counts occurrences rather than testing for
    presence, because a second printing would mean a duplicate call site or a
    handler that propagates crept back in. That is the shape this test was
    written to catch, and it is also why the count is load-bearing: this path
    reaches the reporter before `_configure_logging` has run, so it is the one
    that proves the handler is installed early enough to carry it.
    """
    _write_markdown(tmp_path / "docs" / "notes.md", "Notes")

    completed = _run_check(tmp_path, "--fix", "--diff")

    assert completed.returncode == 2, "expected a rejected flag pair to exit two"
    assert not completed.stdout, "expected the usage error on standard error"
    assert_with_context(
        completed.stderr.count("--fix and --diff cannot be combined") == 1,
        "expected exactly one reporter emission and no duplicate",
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
        completed.stdout.startswith("checked "),
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
        completed.stderr.startswith("checked "),
        "expected the summary to move to standard error under --diff",
    )


def test_python_module_entrypoint_writes_a_stream_document_byte_for_byte(
    tmp_path: pathlib.Path,
) -> None:
    r"""A piped document survives a hostile stdout without losing a byte.

    This is the one test that exercises the *production* output boundary. Every
    other fix-output test injects a `StringIO`, which cannot fail the way a real
    stream does: `StringIO` neither translates newlines nor chooses an encoding,
    so it would pass even if the command wrote through `print` to a locale-coded
    text stream.

    The child is given `PYTHONIOENCODING=latin-1`, which is the load-bearing
    part of this test rather than decoration. Under a UTF-8 stream a text write
    of this document produces the same bytes as a binary one, so the assertion
    below would hold either way and prove nothing -- verified by running it
    against a deliberately lossy writer, which passed until the encoding was
    forced. Latin-1 can encode `é` (as one byte, `0xe9`) where UTF-8 needs two,
    so the two writers disagree on the wire and the assertion can tell them
    apart. The bytes are still expected to be UTF-8: `write_artefact` reaches
    the binary buffer, which no text-stream setting can influence.

    `--fix` is what makes the command produce a document at all: a stream input
    is never written to disk, so without the flag this is a plain check and
    standard output carries the summary instead. With the flag and nothing to
    fix, the planner reports an unchanged plan and the command emits the source,
    which is precisely the path this test is about.
    """
    source = "Café text.\r\nSecond line."
    completed = _run_check_bytes(
        tmp_path,
        source.encode("utf-8"),
        "--fix",
        env_overrides={"PYTHONIOENCODING": "latin-1"},
    )

    assert_with_context(
        completed.stdout == source.encode("utf-8"),
        f"expected the document back byte for byte, got {completed.stdout!r}",
    )
    assert_with_context(
        b"files fixed, " in completed.stderr,
        f"expected the report on standard error, got {completed.stderr!r}",
    )


def _run_check_bytes(
    cwd: pathlib.Path,
    stdin_bytes: bytes,
    *flags: str,
    env_overrides: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    """Run `check -` over a byte stream and capture its streams as bytes.

    `_run_check` captures text, which is the right choice for asserting a
    rendered report and the wrong one here: decoding the child's output at the
    test boundary would repair exactly the corruption the caller wants to
    observe. This helper keeps both sides in bytes so the comparison is a
    comparison of what was actually written.

    Parameters
    ----------
    cwd:
        The directory to run in, which is also the discovered target.
    stdin_bytes:
        The exact bytes to pipe into the command.
    *flags:
        Extra command-line flags, inserted after the subcommand.
    env_overrides:
        Environment values to set for the child, on top of the importable
        `PYTHONPATH`. Used to hand the child a stream configuration that would
        expose a non-byte-faithful writer.

    Returns
    -------
    subprocess.CompletedProcess
        The finished process, with its streams captured as bytes.
    """
    env = python_module_environment()
    env.update(env_overrides or {})
    return subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] - trusted interpreter, fixed flags, no shell.
        [sys.executable, "-m", "stilyagi", "check", *flags, "-"],
        cwd=cwd,
        env=env,
        input=stdin_bytes,
        capture_output=True,
        check=False,
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
