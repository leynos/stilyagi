"""Command-boundary coverage for the injectable check collaborators.

These tests drive the same pipeline through `cli.run_check`, so they pin the
behaviour that only exists at the command boundary: an injected `output` stream
receiving the rendered report, an injected `reporter` taking expected failures
off the real standard error, both outcomes of a `--diff` preview, and the
stream a mutating run reports on. The per-file workflow and the aggregation
pass, which are covered by driving `cli_pipeline` directly, live in
`tests/test_check_pipeline_units.py`.

Run them with:

    make test

or, for this module alone:

    .venv/bin/python -m pytest tests/test_check_boundaries.py
"""

import dataclasses as dc
import io
import sys
import typing as typ

from stilyagi import cli, cli_fix, cli_io, config, diagnostics, model
from stilyagi.fixes import Applicability, Fix, TextEdit

from tests.support.assertions import assert_with_context
from tests.support.check_pipeline_fixtures import (
    patch_read_bytes_failure,
    planned_file,
    recording_reporter,
    silent_runner,
)

if typ.TYPE_CHECKING:
    import pathlib

    import pytest
    from stilyagi.engine.fix_pipeline import PlannedFile


class TestInjectedStreamsAndReporters:
    """The command boundary honours injected streams and reporters."""

    def test_an_injected_output_stream_receives_the_rendered_diagnostics(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Substituting `output` redirects the rendered report."""
        stream = io.StringIO()
        (tmp_path / "notes.md").write_text("# Notes\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)

        exit_code = cli.run_check(
            cli.CheckOptions(targets=("notes.md",)),
            collaborators=cli.CheckCollaborators(
                output=stream, rule_runner=silent_runner
            ),
        )

        assert exit_code == 0, "expected a clean check to exit zero"
        assert_with_context(
            stream.getvalue() == "0 diagnostics found (0 safe fixes, 0 unsafe fixes)\n",
            "expected the rendered report on the injected stream",
        )

    def test_an_injected_reporter_receives_read_failures_instead_of_stderr(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Substituting `reporter` keeps expected failures off the real stderr.

        The target has to survive discovery and fail at the read, because
        discovery ignores a target that was never there; a file that vanishes
        mid-run is the realistic shape of a read failure.
        """
        target = tmp_path / "notes.md"
        target.write_text("# Notes\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        patch_read_bytes_failure(monkeypatch, target)
        failures, report = recording_reporter()

        exit_code = cli.run_check(
            cli.CheckOptions(targets=(target.name,)),
            collaborators=cli.CheckCollaborators(
                reporter=report, rule_runner=silent_runner
            ),
        )

        assert exit_code == 2, "expected a read failure to exit two"
        assert len(failures) == 1, "expected the injected reporter to be used"
        assert isinstance(failures[0][1], cli_io.SourceReadError), (
            "expected the typed read error to reach the injected reporter"
        )

    def test_an_injected_reporter_receives_discovery_failures(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Discovery failures reach the reporter with no path to blame."""
        (tmp_path / "stilyagi.toml").write_text("[lint\n", encoding="utf-8")
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "notes.md").write_text("# Notes\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        failures, report = recording_reporter()

        exit_code = cli.run_check(
            cli.CheckOptions(targets=("docs",)),
            collaborators=cli.CheckCollaborators(reporter=report),
        )

        assert exit_code == 2, "expected invalid config to exit two"
        assert len(failures) == 1, "expected exactly one reported failure"
        path, _error = failures[0]
        assert path is None, (
            "expected discovery failures to reach the reporter without a path"
        )


class TestDiffPreviews:
    """Both diff outcomes are covered at the command boundary."""

    def test_an_accepted_preview_patches_output_without_touching_the_file(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An accepted safe fix prints a patch and leaves the source alone."""
        target = tmp_path / "notes.md"
        original = "Paragraph text.\n"
        target.write_text(original, encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        stream = io.StringIO()

        exit_code = cli.run_check(
            cli.CheckOptions(targets=(target.name,), diff=True),
            collaborators=cli.CheckCollaborators(
                output=stream, rule_runner=_rewrite_paragraph
            ),
        )

        # An accepted preview still exits one: the diagnostic was found and the
        # source is deliberately left for the user to apply.
        assert exit_code == 1, "expected an accepted preview to still exit one"
        assert_with_context(
            target.read_text(encoding="utf-8") == original,
            "expected the preview to leave the source unchanged",
        )
        assert_with_context(
            stream.getvalue().startswith("--- a/notes.md"),
            "expected a unified diff on the injected output stream",
        )
        assert_with_context(
            "Section text." in stream.getvalue(),
            "expected the preview to show the planned replacement",
        )

    def test_a_refused_preview_reports_the_refusal_and_emits_no_patch(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A refused edit produces no patch and still exits one."""
        target = tmp_path / "notes.md"
        target.write_text("# Notes\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        stream = io.StringIO()

        exit_code = cli.run_check(
            cli.CheckOptions(targets=(target.name,), diff=True),
            collaborators=cli.CheckCollaborators(
                output=stream, rule_runner=_rewrite_heading_marker
            ),
        )

        assert exit_code == 1, "expected an unfixed diagnostic to exit one"
        assert not stream.getvalue(), "expected a refused edit to emit no patch"
        assert_with_context(
            target.read_text(encoding="utf-8") == "# Notes\n",
            "expected a refused edit to leave the source unchanged",
        )


def _rewrite_paragraph(
    document: model.Document,
    _config: config.StilyagiConfig,
) -> list[diagnostics.Diagnostic]:
    """Offer one safe replacement against a source-backed paragraph span."""
    from tests.support.fix_fixtures import find_source_span

    span = find_source_span(document, "Paragraph")
    return [
        diagnostics.Diagnostic(
            path="notes.md",
            code="PUN201",
            message="Use the preferred paragraph term.",
            severity=diagnostics.Severity.WARNING,
            fix=Fix(
                "Rewrite paragraph",
                Applicability.SAFE,
                (TextEdit.replace(span, "Section"),),
            ),
        )
    ]


def _rewrite_heading_marker(
    _document: model.Document,
    _config: config.StilyagiConfig,
) -> list[diagnostics.Diagnostic]:
    """Offer a deliberately unsafe synthetic-span edit for stream testing."""
    return [
        diagnostics.Diagnostic(
            path="notes.md",
            code="PUN201",
            message="Do not change the heading marker automatically.",
            severity=diagnostics.Severity.WARNING,
            fix=Fix(
                "Remove heading marker",
                Applicability.SAFE,
                (TextEdit(0, 1, ""),),
            ),
        )
    ]


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
                output=stream, rule_runner=_rewrite_paragraph
            ),
        )

        assert exit_code == 1, "expected an unwritten stream input to still exit one"
        assert_with_context(
            stream.getvalue() == "Section text.\n",
            "expected the fixed document alone on the injected stream",
        )


class TestFixedDocumentEmission:
    """`emit_fixed_document` prints a piped file's replacement and nothing else."""

    def test_a_stream_input_prints_its_replacement_verbatim(self) -> None:
        """The piped document is emitted with no decoration added.

        `print` adds a newline nobody asked for, so `end=""` is load-bearing:
        the bytes a user piped in are theirs to capture, and a trailing newline
        here would be a byte the fixed document never contained. A source
        already ending in one would look correct either way, so this one does
        not end in one.

        `emit_fixed_document` is called directly rather than through the command
        because the command-level test above drives a `#`-headed document, whose
        fixed text carries a newline and so cannot distinguish the two.
        """
        stream = io.StringIO()
        plan = _piped_plan("Paragraph text.", "Section text.")

        cli_fix.emit_fixed_document([plan], stream)

        assert_with_context(
            stream.getvalue() == "Section text.",
            "expected the replacement bytes alone, with no appended newline",
        )

    def test_a_file_input_prints_nothing(self) -> None:
        """A file's replacement is written to disk, never to standard output.

        Emitting here as well would print the whole repaired document on a run
        that also wrote it, so the `from_stdin` guard is the whole behaviour
        under test. The plan is otherwise identical to the stream case above,
        which is what makes the flag the only thing the assertion can observe.
        """
        stream = io.StringIO()
        plan = dc.replace(
            _piped_plan("Paragraph text.", "Section text."), from_stdin=False
        )

        cli_fix.emit_fixed_document([plan], stream)

        assert_with_context(
            not stream.getvalue(),
            "expected a file input's replacement to stay off standard output",
        )

    def test_a_conflicted_stream_input_prints_nothing(self) -> None:
        """A plan with no replacement has no document to emit.

        A stream input whose every edit was refused has `fixed_bytes` of
        ``None``, and there is nothing honest to print: emitting the unchanged
        source would tell a user their document was fixed. The guard folds "no
        replacement" and "not from a stream" into one decision, so this case and
        the file case are asserted separately -- they differ in why nothing is
        printed, and a regression could collapse either reason.
        """
        stream = io.StringIO()
        plan = _piped_plan("Paragraph text.", "Paragraph text.")

        cli_fix.emit_fixed_document([plan], stream)

        assert_with_context(
            not stream.getvalue(),
            "expected a refused stream input to emit no document",
        )


def _piped_plan(source_text: str, fixed_text: str) -> PlannedFile:
    """Return a plan for one file whose bytes came from standard input.

    Returns
    -------
    PlannedFile
        The plan `planned_file` builds, flagged as a stream input. The flag is
        set here rather than passed through the shared fixture because that
        helper already sits at the project's four-argument ceiling.
    """
    return dc.replace(
        planned_file("notes.md", fixed_text, source_text=source_text),
        from_stdin=True,
    )
