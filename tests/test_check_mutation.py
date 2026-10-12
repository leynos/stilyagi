"""Command-boundary coverage for a mutating `--fix` run.

These tests drive the mutating path through `cli.run_check`, so they pin the
behaviour that only exists once a run is allowed to write: which stream a
mutating run reports on, and the exit status when some files were written and
some were not.

A write the run *refused* to make, and the exit status that refusal implies,
live in `tests/test_check_refusals.py`. The non-mutating command boundaries --
injected streams and reporters, and both `--diff` outcomes -- live in
`tests/test_check_boundaries.py`. The emitter's own unit boundary lives in
`tests/test_cli_fix.py`.

Run them with:

    make test

or, for this module alone:

    .venv/bin/python -m pytest tests/test_check_mutation.py
"""

import io
import sys
import typing as typ

from stilyagi import cli, cli_fix, config, diagnostics, model
from stilyagi.fixes import Applicability, Fix, TextEdit

from tests.support.assertions import assert_with_context
from tests.support.check_pipeline_fixtures import (
    rewrite_paragraph,
    silent_runner,
)

if typ.TYPE_CHECKING:
    import pathlib

    import pytest


class TestMutationStreams:
    """A mutating run reports on the stream its input leaves free."""

    def test_a_clean_tree_is_never_reported_as_having_been_fixed(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A run with nothing to fix reports like a plain check and writes nothing.

        Nothing was fixable, so no file was written and the re-run note would
        be a false report of a mutation. The diagnostics stream is the normal
        one, because standard output is free for a file input.
        """
        target = tmp_path / "notes.md"
        original = "# Notes\n"
        target.write_text(original, encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        stream = io.StringIO()

        exit_code = cli.run_check(
            cli.CheckOptions(targets=(target.name,), fix=True),
            collaborators=cli.CheckCollaborators(
                output=stream, rule_runner=silent_runner
            ),
        )

        assert exit_code == 0, "expected a clean tree to exit zero"
        assert_with_context(
            cli_fix.RERUN_HINT not in stream.getvalue(),
            "expected no re-run note for a run that wrote nothing",
        )
        assert_with_context(
            target.read_text(encoding="utf-8") == original,
            "expected the tree to be left exactly as it was found",
        )

    def test_a_fixed_document_owns_standard_output_for_a_stream_input(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A stream input's report goes elsewhere, so the fixed text stays clean.

        D-05: the bytes a user piped in are theirs to capture, so appending a
        rendered report to them would corrupt the one thing the command
        produces. Only the report's destination is asserted here -- that a
        stream input is never written to disk is covered end to end.

        The exit status is one, not zero, and that follows from D-13 rather
        than contradicting the repair: the status comes from re-linting the
        files this run *wrote*, and a stream input is never written. Its
        planning diagnostic therefore still stands, and nothing claims a
        mutation happened. Only the report's destination is this test's
        subject.
        """
        (tmp_path / "notes.md").write_text("Paragraph text.\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(sys, "stdin", io.StringIO("Paragraph text.\n"))
        stream = io.StringIO()

        exit_code = cli.run_check(
            cli.CheckOptions(targets=("-",), stdin_filename="notes.md", fix=True),
            collaborators=cli.CheckCollaborators(
                output=stream, rule_runner=rewrite_paragraph
            ),
        )

        assert exit_code == 1, "expected an unwritten stream input to still exit one"
        assert_with_context(
            stream.getvalue() == "Section text.\n",
            "expected the fixed document alone on the injected stream",
        )


class TestExitStatusAcrossMixedOutcomes:
    """A mutating run exits on every diagnostic still standing when it ends.

    The exit status is the one claim `--fix` makes that a user acts on, and it
    is the claim a partially-applied run can most easily get wrong: some files
    are re-read after being written and some are not, so a status derived from
    only one of those groups is a status about half the run.
    """

    def test_an_unwritten_siblings_diagnostic_still_forces_a_nonzero_exit(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """One fixed file must not mask another file's surviving diagnostic.

        This is the defect the re-lint-only status had. `relint_written_files`
        re-checks exactly the files that were written, so a run that fixed
        `a.md` and left `b.md`'s unfixable diagnostic standing produced a
        re-lint holding only `a.md`. The status was read from that alone, so the
        run exited `0` while `b.md`'s diagnostic was still there.

        `a.md` is the file that gets written, so it is the one the re-lint can
        speak for -- and its re-lint is deliberately silent, so it cannot be the
        source of the exit status under test. `b.md` is left unwritten, which is
        the only condition under which the re-lint is blind to a file's
        diagnostics. The status can therefore only come from the overlay.
        """
        (tmp_path / "a.md").write_text("Paragraph text.\n", encoding="utf-8")
        (tmp_path / "b.md").write_text("# Notes\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        stream = io.StringIO()

        exit_code = cli.run_check(
            cli.CheckOptions(targets=("a.md", "b.md"), fix=True),
            collaborators=cli.CheckCollaborators(
                output=stream, rule_runner=_fix_one_and_leave_the_other_standing
            ),
        )

        assert_with_context(
            (tmp_path / "a.md").read_text(encoding="utf-8") == "Section text.\n",
            "expected the fixable file to have been rewritten",
        )
        assert_with_context(
            (tmp_path / "b.md").read_text(encoding="utf-8") == "# Notes\n",
            "expected the file with nothing to fix to be left untouched",
        )
        assert_with_context(
            exit_code == 1,
            "expected a surviving diagnostic in an unwritten file to exit one",
        )


def _fix_one_and_leave_the_other_standing(
    document: model.Document,
    _config: config.StilyagiConfig,
) -> list[diagnostics.Diagnostic]:
    """Report a fixable edit for one file and an unfixable finding for the other.

    One runner produces both halves of a mixed run, which is what makes the exit
    status the only variable under test. The files are told apart by their own
    stable content, because a runner sees a document and not a path:

    * `a.md` contains "Paragraph", so the planning pass is offered a source-backed
      edit rewriting it to "Section", and the file is written;
    * `b.md` contains "Notes" and gets a plain diagnostic carrying no fix at all,
      so there is nothing to plan for it and it is never written;
    * the re-lint of `a.md` now reads "Section text." and matches neither, so it
      reports nothing -- which is the point.

    The third branch is what makes this test discriminate. Without it the
    rewritten file would keep matching the first branch and report a diagnostic
    of its own, so a run that read its status from the re-lint alone would still
    exit `1` and the defect would go unnoticed.

    `b.md`'s diagnostic deliberately carries no fix. The file only has to be
    left *unwritten* for the re-lint to be unable to speak for it, and a finding
    with no fix keeps the test about the exit status rather than about refusal
    handling, which the refusal-rendering class covers separately.

    Returns
    -------
    list[diagnostics.Diagnostic]
        A fixable edit for `a.md`, no fix for `b.md`, and nothing once the
        re-lint reads the rewritten text.
    """
    from tests.support.fix_fixtures import find_source_span

    prose = "".join(region.text for region in document.regions)
    if "Notes" in prose:
        return [
            diagnostics.Diagnostic(
                path="notes.md",
                code="STY900",
                message="This finding is never fixable.",
                severity=diagnostics.Severity.WARNING,
            )
        ]
    if "Paragraph" in prose:
        return [
            diagnostics.Diagnostic(
                path="notes.md",
                code="PUN201",
                message="Use the preferred paragraph term.",
                severity=diagnostics.Severity.WARNING,
                fix=Fix(
                    "Rewrite paragraph",
                    Applicability.SAFE,
                    (
                        TextEdit.replace(
                            find_source_span(document, "Paragraph"), "Section"
                        ),
                    ),
                ),
            )
        ]
    return []
