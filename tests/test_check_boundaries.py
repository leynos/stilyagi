"""Command-boundary coverage for the injectable check collaborators.

These tests drive the same pipeline through `cli.run_check`, so they pin the
behaviour that only exists at the command boundary: an injected `output` stream
receiving the rendered report, an injected `reporter` taking expected failures
off the real standard error, and both outcomes of a `--diff` preview. The
per-file workflow and the aggregation pass, which are covered by driving
`check_execution` and `cli_run` directly, live in
`tests/test_check_pipeline_units.py`. A mutating run's own streams and exit
statuses live in `tests/test_check_mutation.py`; the exit status of a write the
run refused to make lives in `tests/test_check_refusals.py`, and a run that
wrote some files and refused others lives in
`tests/test_check_partial_runs.py`.

Run them with:

    make test

or, for this module alone:

    .venv/bin/python -m pytest tests/test_check_boundaries.py
"""

import io
import typing as typ

from stilyagi import cli, cli_io

from tests.support.assertions import assert_with_context
from tests.support.check_pipeline_fixtures import (
    patch_read_bytes_failure,
    recording_reporter,
    rewrite_heading_marker,
    rewrite_paragraph,
    silent_runner,
)

if typ.TYPE_CHECKING:
    import pathlib

    import pytest


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
            stream.getvalue()
            == "checked 1 files (0 skipped, 0 unreadable); 0 errors, 0 warnings\n",
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
