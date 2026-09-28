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
import pathlib
import sys
import typing as typ

from stilyagi import cli, cli_fix, cli_io, config, diagnostics, model
from stilyagi.fixes import Applicability, Fix, TextEdit

from tests.support.assertions import assert_with_context
from tests.support.check_pipeline_fixtures import (
    patch_read_bytes_failure,
    planned_file,
    recording_reporter,
    rewrite_heading_marker,
    rewrite_paragraph,
    silent_runner,
)

if typ.TYPE_CHECKING:
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
                output=stream, rule_runner=rewrite_paragraph
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
                output=stream, rule_runner=rewrite_heading_marker
            ),
        )

        assert exit_code == 1, "expected an unfixed diagnostic to exit one"
        assert not stream.getvalue(), "expected a refused edit to emit no patch"
        assert_with_context(
            target.read_text(encoding="utf-8") == "# Notes\n",
            "expected a refused edit to leave the source unchanged",
        )


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


class TestWriteFailuresAreReported:
    """A filesystem that refuses a write is reported, not raised.

    `write_source` documents `OSError` in its own `Raises` section, so the
    executor has always had a failure mode it did not handle: catching only
    `SourceChangedOnDiskError` let a full or read-only filesystem escape as a
    traceback, abandoning every file after it and reporting nothing about the
    files already written or why the run stopped.
    """

    def test_a_permission_failure_is_reported_and_exits_two(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A rejected write becomes a refusal and an operational-error status.

        `Path.replace` is what actually moves the staged bytes onto the target,
        so making it raise is the narrowest way to stand in for a read-only
        filesystem: the plan is well-formed, the target has not moved, and only
        the filesystem says no.
        """
        target = tmp_path / "notes.md"
        target.write_text("Paragraph text.\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        stream = io.StringIO()

        def refuse_replace(
            _self: object, _target: object, *_args: object, **_kwargs: object
        ) -> None:
            """Refuse the swap the way a read-only filesystem would."""
            message = "Read-only file system"
            raise PermissionError(message)

        monkeypatch.setattr(pathlib.Path, "replace", refuse_replace)

        exit_code = cli.run_check(
            cli.CheckOptions(targets=(target.name,), fix=True),
            collaborators=cli.CheckCollaborators(
                output=stream, rule_runner=rewrite_paragraph
            ),
        )

        assert_with_context(
            exit_code == 2,
            "expected a filesystem refusal to exit two",
        )
        assert_with_context(
            target.read_text(encoding="utf-8") == "Paragraph text.\n",
            "expected a refused write to leave the source unchanged",
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
    handling, which the class below covers separately.
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


def _planned_refusal(identifier: str, rule_codes: tuple[str, ...]) -> PlannedFile:
    """Return a plan carrying one refusal with the given codes.

    Returns
    -------
    PlannedFile
        `planned_file`'s plan with its refusal channel replaced, so a test can
        state the exact refusal a renderer will see.
    """
    return dc.replace(
        planned_file("notes.md", "# Notes\n"),
        fix_errors=(
            diagnostics.FixError(
                path="notes.md",
                identifier=identifier,
                rule_codes=rule_codes,
                message="the file was left alone",
            ),
        ),
    )


def _render_refusals(*plans: PlannedFile) -> str:
    """Render the refusals those plans carry through the text renderer."""
    return cli.engine.RendererRegistry().render(
        [],
        "text",
        fix_errors=[fix_error for plan in plans for fix_error in plan.fix_errors],
    )


class TestRefusalRendering:
    """A refusal names its origin, and omits what it does not have."""

    def test_a_refusal_with_no_rule_codes_omits_the_empty_segment(self) -> None:
        """No code is rendered as nothing, not as a dangling separator.

        `changed-on-disk` and `standard-input` are raised by the executor and
        the phase-one wrapper rather than by a rule's proposed edit, so they
        carry no rule codes by construction. Joining an empty tuple yields the
        empty string, which used to render as `path: : message`.
        """
        rendered = _render_refusals(_planned_refusal("fix-error/changed-on-disk", ()))

        assert_with_context(
            "fix-error/changed-on-disk: notes.md: the file was left alone" in rendered,
            "expected the refusal line to name the path then the message",
        )
        assert_with_context(
            ": :" not in rendered,
            "expected no empty rule-code segment in the rendered refusal",
        )

    def test_a_refusal_with_rule_codes_still_names_them(self) -> None:
        """The codes are what tells a user which rule could not be applied.

        Paired with the case above, this pins that the fix narrowed one
        rendering rather than removing the segment outright: a conflict still
        has to name every rule that contributed to it.
        """
        rendered = _render_refusals(
            _planned_refusal("fix-error/overlapping-edits", ("PUN201", "PUN202"))
        )

        assert_with_context(
            "fix-error/overlapping-edits: notes.md: PUN201, PUN202: "
            "the file was left alone" in rendered,
            "expected the refusal to name both contributing rules",
        )
