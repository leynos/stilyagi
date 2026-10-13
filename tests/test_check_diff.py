"""Integration coverage for non-mutating safe-fix diff previews.

The three ways a `--diff` run renders no patch, and the counters that report
having rendered one, are pinned here. The `--diff` *switch* -- that the parser
accepts it and turns it into a check option -- is a parser concern and lives
with the other option pins in `tests/test_cli_args.py`.
"""

import logging
import typing as typ

from stilyagi import cli, config, diagnostics, model
from stilyagi.fixes import Applicability, Fix, TextEdit
from syrupy.extensions.json import JSONSnapshotExtension

from tests.support.assertions import assert_with_context
from tests.support.check_pipeline_fixtures import (
    rewrite_heading_marker,
    rewrite_paragraph,
    silent_runner,
)
from tests.support.fix_fixtures import SourceTextNotFoundError, find_source_span

if typ.TYPE_CHECKING:
    import pathlib

    import pytest
    from syrupy.assertion import SnapshotAssertion


def test_diff_prints_a_safe_preview_without_mutating_the_source(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    snapshot: SnapshotAssertion,
) -> None:
    """Reserve stdout for a safe patch and report diagnostics on stderr."""
    target = tmp_path / "notes.md"
    original = "Paragraph text.\n"
    target.write_text(original, encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    exit_code = cli.run_check(
        cli.CheckOptions(targets=(target.name,), diff=True),
        collaborators=cli.CheckCollaborators(rule_runner=rewrite_paragraph),
    )
    captured = capsys.readouterr()

    assert_with_context(
        target.read_text(encoding="utf-8") == original,
        "expected the diff preview to leave the source unchanged",
    )
    assert_with_context(
        {
            "exit_code": exit_code,
            "stdout": captured.out,
            "stderr": captured.err,
        }
        == snapshot(extension_class=JSONSnapshotExtension),
        "expected the diff preview stream contract to match its snapshot",
    )


def test_diff_reports_refused_edits_on_the_diagnostic_stream(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Keep a planner refusal out of the patch while making it auditable."""
    target = tmp_path / "notes.md"
    target.write_text("# Notes\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    exit_code = cli.run_check(
        cli.CheckOptions(targets=(target.name,), diff=True),
        collaborators=cli.CheckCollaborators(rule_runner=rewrite_heading_marker),
    )
    captured = capsys.readouterr()

    assert exit_code == 1, "expected an unfixed diagnostic to exit one"
    assert not captured.out, "expected a refused edit to emit no patch"
    assert_with_context(
        "fix-error/synthetic-span: notes.md: PUN201:" in captured.err,
        "expected the refusal to use the separate fix-error channel",
    )
    assert_with_context(
        "file was not modified" in captured.err,
        "expected the refusal to state the file remained untouched",
    )


def test_diff_routes_a_json_refusal_to_stderr_with_an_empty_stdout(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Keep the patch stream clean while carrying the refusal in JSON.

    The renderer's own test builds `FixError` values directly, which pins the
    serialisation and says nothing about where a real run puts them. Under
    `--diff` that routing is the contract: an editor consuming `--diff` reads
    standard output as a patch, so a JSON refusal written there would be
    parsed as part of the patch. The refusal has to reach standard error while
    the patch stream stays byte-empty, and both halves are asserted here
    because satisfying either alone is easy -- writing everything to stderr,
    or everything to stdout, would each pass a single-sided check.
    """
    target = tmp_path / "notes.md"
    target.write_text("# Notes\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    exit_code = cli.run_check(
        cli.CheckOptions(targets=(target.name,), diff=True, output_format="json"),
        collaborators=cli.CheckCollaborators(rule_runner=rewrite_heading_marker),
    )
    captured = capsys.readouterr()

    assert exit_code == 1, "expected an unfixed diagnostic to exit one"
    assert not captured.out, "expected the patch stream to carry no refusal"
    assert_with_context(
        '"identifier": "fix-error/synthetic-span"' in captured.err,
        f"expected the refusal on standard error, got {captured.err!r}",
    )
    assert_with_context(
        '"path": "notes.md"' in captured.err,
        "expected the JSON refusal to name the file it left alone",
    )


class TestEmptyPatchExitStatus:
    """Pin the three ways `--diff` renders no patch, and what each one exits.

    The users' guide states this as a three-case list, and the list is only
    correct while the code agrees with it. The cases are worth separating
    because the *output* is identical in all three -- an empty standard output
    -- so a reader cannot tell them apart from the stream, and the exit status
    plus the diagnostic stream are the only things that can. A regression that
    collapsed case two or three into case one would turn a run with an
    unaddressed finding into a silent success.
    """

    def test_nothing_reported_exits_zero(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A tree with nothing to report is the one clean empty patch."""
        target = tmp_path / "notes.md"
        target.write_text("# Notes\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)

        exit_code = cli.run_check(
            cli.CheckOptions(targets=(target.name,), diff=True),
            collaborators=cli.CheckCollaborators(rule_runner=silent_runner),
        )
        captured = capsys.readouterr()

        assert_with_context(
            exit_code == 0, "expected a run with nothing to report to exit zero"
        )
        assert not captured.out, "expected no patch for a clean tree"
        assert_with_context(
            "checked 1 files (0 skipped, 0 unreadable); 0 errors, 0 warnings"
            in captured.err,
            "expected the summary to still reach standard error",
        )

    def test_an_unsafe_only_diagnostic_exits_one_without_a_patch(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A finding that carries no safe fix is reported and never previewed.

        The diagnostic is present and the run is not clean, but the default
        preview selects safe fixes only, so nothing is eligible and no patch is
        rendered. Reporting the diagnostic is what keeps the exit status
        honest: a run that printed an empty patch and exited `0` would tell a
        user their file is fine.
        """
        target = tmp_path / "notes.md"
        target.write_text("Paragraph text.\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)

        exit_code = cli.run_check(
            cli.CheckOptions(targets=(target.name,), diff=True),
            collaborators=cli.CheckCollaborators(rule_runner=_unsafe_only_runner),
        )
        captured = capsys.readouterr()

        assert exit_code == 1, "expected an unsafe-only finding to exit one"
        assert not captured.out, "expected an unsafe fix to render no safe patch"
        assert_with_context(
            "PUN201" in captured.err,
            "expected the unsafe finding to be reported on the diagnostic stream",
        )


def _unsafe_only_runner(
    document: model.Document,
    _config: config.StilyagiConfig,
) -> list[diagnostics.Diagnostic]:
    """Offer one fix a rule marked unsafe and nothing else.

    The edit is well formed and spans source-backed text, so it is not a
    refusal: it is a candidate the *level* excludes. That distinction is what
    makes this case separate from the refused preview, whose edit the planner
    rejects on admissibility grounds.

    The needle is guarded rather than asserted because the same runner re-runs
    over the rewritten file when a mutating invocation writes it: the second
    read no longer contains "Paragraph", and a runner that raised there would
    turn a successful fix into a crash. This mirrors the mixed-outcome runner
    in `test_check_mutation`, which reads the document's own text for the same
    reason.

    Returns
    -------
    list[diagnostics.Diagnostic]
        The single finding, carrying an unsafe fix, or nothing once the text it
        targets is gone.
    """
    try:
        span = find_source_span(document, "Paragraph")
    except SourceTextNotFoundError:
        return []
    return [
        diagnostics.Diagnostic(
            path="notes.md",
            code="PUN201",
            message="Only an unsafe rewrite exists here.",
            severity=diagnostics.Severity.ERROR,
            fix=Fix(
                "Rewrite paragraph",
                Applicability.UNSAFE,
                (TextEdit.replace(span, "Section"),),
            ),
        )
    ]


class TestDiffRenderSignal:
    """A `--diff` run reports what it rendered, including rendering nothing.

    The signal exists because the failure mode is invisible in the output: a
    run that planned a file and emitted no patch writes an empty standard
    output, and so does a run that had nothing to plan at all. Only the pair of
    counters separates them, and only the log carries it.
    """

    @staticmethod
    def _render_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
        """Return the diff-rendering records captured during one run.

        Returns
        -------
        list[logging.LogRecord]
            Every record whose operation is ``render_diff``, in emission order.
        """
        return [
            record
            for record in caplog.records
            if getattr(record, "operation", None) == "render_diff"
        ]

    def test_a_planned_file_with_no_patch_is_reported_as_unpatched(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Name the gap between the files planned and the files patched.

        `rewrite_heading_marker` offers an edit the planner refuses, so the file
        is planned, the plan carries a refusal, and the rendered patch is empty.
        The two counters therefore disagree -- which is the whole signal. A
        record carrying only the patch's byte count would report zero and look
        identical to a run that never planned anything.
        """
        target = tmp_path / "notes.md"
        target.write_text("# Notes\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)

        with caplog.at_level(logging.INFO):
            exit_code = cli.run_check(
                cli.CheckOptions(targets=(target.name,), diff=True),
                collaborators=cli.CheckCollaborators(
                    rule_runner=rewrite_heading_marker
                ),
            )
        captured = capsys.readouterr()
        records = self._render_records(caplog)

        assert exit_code == 1, "expected an unfixed diagnostic to exit one"
        assert not captured.out, "expected a refused edit to emit no patch"
        assert_with_context(
            len(records) == 1,
            f"expected exactly one render record, got "
            f"{[record.getMessage() for record in records]!r}",
        )
        record = records[0]
        assert_with_context(
            (record.planned_files, record.patched_files, record.patch_byte_count)
            == (1, 0, 0),
            "expected the render record to separate a planned file from a patched one",
        )
        assert_with_context(
            isinstance(record.elapsed_ms, int) and record.elapsed_ms >= 0,
            f"expected a non-negative render duration, got {record.elapsed_ms!r}",
        )

    def test_a_rendered_patch_reports_its_measured_size(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Measure the patch that was actually written, not the replacement.

        The count is taken after the patch is assembled, so it is the size of
        the artefact on the wire. The planner's own `replacement_byte_count`
        measures a different quantity -- the whole replacement document -- and
        cannot be substituted for it: the unified diff carries a header, a
        hunk context and markers that the replacement does not.
        """
        target = tmp_path / "notes.md"
        target.write_text("Paragraph text.\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)

        with caplog.at_level(logging.INFO):
            exit_code = cli.run_check(
                cli.CheckOptions(targets=(target.name,), diff=True),
                collaborators=cli.CheckCollaborators(rule_runner=rewrite_paragraph),
            )
        captured = capsys.readouterr()
        record = self._render_records(caplog)[0]

        assert exit_code == 1, "expected a previewed diagnostic to exit one"
        assert_with_context(captured.out, "expected a planned edit to render a patch")
        assert_with_context(
            (record.planned_files, record.patched_files) == (1, 1),
            "expected one planned file to be counted as patched",
        )
        assert_with_context(
            record.patch_byte_count == len(captured.out.encode("utf-8")),
            f"expected the byte count to measure the written patch, got "
            f"{record.patch_byte_count} for {len(captured.out.encode('utf-8'))} bytes",
        )
