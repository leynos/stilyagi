"""Unit coverage for the per-file check workflow and its aggregation.

These tests drive `cli_pipeline` directly, so they pin the boundary the
refactor introduced: the named per-file result, the single aggregation pass,
and the typed read error. The command-boundary behaviour that exercises the
same code through `cli.run_check` -- injected streams, injected reporters, and
the two diff outcomes -- lives in `tests/test_check_boundaries.py`.

Run them with:

    make test

or, for this module alone:

    .venv/bin/python -m pytest tests/test_check_pipeline_units.py
"""

import typing as typ

import pytest
from stilyagi import cli_io, cli_pipeline, config, engine

from tests.support.assertions import assert_with_context
from tests.support.check_pipeline_fixtures import (
    checked_file,
    input_for,
    one_diagnostic_runner,
    planned_file,
    recording_reporter,
    run_for,
    silent_runner,
)

if typ.TYPE_CHECKING:
    import pathlib


class TestCheckOneFile:
    """The per-file workflow returns a named result and reports failures."""

    def test_a_readable_file_yields_a_named_result_carrying_its_diagnostics(
        self, tmp_path: pathlib.Path
    ) -> None:
        """A readable file produces diagnostics and no failure flag."""
        target = tmp_path / "notes.md"
        target.write_text("# Notes\n", encoding="utf-8")
        failures, report = recording_reporter()

        result = cli_pipeline.check_one_file(
            input_for(target),
            run_for(one_diagnostic_runner, report),
        )

        assert isinstance(result, cli_pipeline.FileCheck), (
            "expected a named FileCheck rather than an anonymous tuple"
        )
        assert_with_context(
            [item.code for item in result.diagnostics_list] == ["PUN201"],
            "expected the injected rule runner's diagnostic to be collected",
        )
        assert not result.failed, "expected a readable file not to fail"
        assert result.planned is None, "expected no plan without --fix or --diff"
        assert not failures, "expected no reported failure for a readable file"

    def test_a_missing_file_reports_a_typed_read_error_and_flags_the_result(
        self, tmp_path: pathlib.Path
    ) -> None:
        """A vanished file yields a SourceReadError through the reporter."""
        target = tmp_path / "gone.md"
        failures, report = recording_reporter()

        result = cli_pipeline.check_one_file(
            input_for(target),
            run_for(silent_runner, report),
        )

        assert result.failed, "expected a missing file to flag the result"
        assert not result.diagnostics_list, "expected no diagnostics from a failure"
        assert len(failures) == 1, "expected exactly one reported failure"
        path, error = failures[0]
        assert path == target, "expected the failure to name the target path"
        assert isinstance(error, cli_io.SourceReadError), (
            "expected the typed read error rather than the bare OS error"
        )
        assert isinstance(error.error, OSError), (
            "expected the typed error to retain the underlying OS error"
        )

    def test_a_directory_read_reports_the_whole_oserror_family(
        self, tmp_path: pathlib.Path
    ) -> None:
        """A directory raising IsADirectoryError is caught by the OSError branch."""
        target = tmp_path / "docs"
        target.mkdir()
        failures, report = recording_reporter()

        result = cli_pipeline.check_one_file(
            input_for(target),
            run_for(silent_runner, report),
        )

        assert result.failed, "expected a directory read to flag the result"
        error = failures[0][1]
        assert isinstance(error, cli_io.SourceReadError), (
            "expected the read failure to be wrapped in the typed error"
        )
        assert isinstance(error.error, IsADirectoryError), (
            "expected the OSError branch to catch IsADirectoryError"
        )

    def test_an_undecodable_file_reports_a_read_error(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Bytes that are not UTF-8 are reported as a read failure."""
        target = tmp_path / "broken.md"
        target.write_bytes(b"\xff")
        failures, report = recording_reporter()

        result = cli_pipeline.check_one_file(
            input_for(target),
            run_for(silent_runner, report),
        )

        assert result.failed, "expected undecodable bytes to flag the result"
        error = failures[0][1]
        assert isinstance(error, cli_io.SourceReadError), (
            "expected the decoding failure to be wrapped in the typed error"
        )
        assert isinstance(error.error, UnicodeDecodeError), (
            "expected the decoding failure to be retained"
        )

    def test_a_bridge_extraction_failure_is_reported_rather_than_raised(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A bridge refusal is expected and becomes a reported failure."""
        target = tmp_path / "notes.md"
        target.write_text("# Notes\n", encoding="utf-8")
        failures, report = recording_reporter()
        monkeypatch.setattr(engine, "extract_document", _raise_bridge_error)

        result = cli_pipeline.check_one_file(
            input_for(target),
            run_for(silent_runner, report),
        )

        assert result.failed, "expected a bridge refusal to flag the result"
        assert not result.diagnostics_list, "expected no diagnostics on refusal"
        assert isinstance(failures[0][1], engine.BridgeExtractionError), (
            "expected the bridge error to reach the reporter"
        )

    def test_an_unexpected_extraction_failure_still_propagates(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An adapter defect is re-raised rather than turned into an exit code."""
        target = tmp_path / "notes.md"
        target.write_text("# Notes\n", encoding="utf-8")
        _failures, report = recording_reporter()
        monkeypatch.setattr(engine, "extract_document", _raise_adapter_error)

        with pytest.raises(TypeError, match="adapter exploded"):
            cli_pipeline.check_one_file(
                input_for(target),
                run_for(silent_runner, report),
            )

    def test_an_invalid_configuration_is_reported_rather_than_raised(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A config that cannot be resolved is an expected per-file failure."""
        target = tmp_path / "notes.md"
        target.write_text("# Notes\n", encoding="utf-8")
        (tmp_path / "stilyagi.toml").write_text("[lint\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        failures, report = recording_reporter()

        result = cli_pipeline.check_one_file(
            input_for(target),
            run_for(silent_runner, report),
        )

        assert result.failed, "expected invalid config to flag the result"
        assert isinstance(
            failures[0][1], (config.InvalidCacheDirError, config.InvalidConfigError)
        ), "expected the configuration error to reach the reporter"


class TestAggregateCheckedFiles:
    """One pass over the per-file results preserves order and the error rule."""

    def test_the_pass_preserves_file_diagnostic_and_patch_order(self) -> None:
        """Diagnostics and patches keep discovery order across several files."""
        results = [
            checked_file(
                "b.md",
                ["b1", "b2"],
                planned=planned_file("b.md", "# Notes B\n", identifiers=["b-refusal"]),
            ),
            checked_file("a.md", ["a1"], planned=planned_file("a.md", "# Notes A\n")),
            checked_file("c.md", []),
        ]

        totals = cli_pipeline.aggregate_checked_files(results)

        assert_with_context(
            [item.message for item in totals.diagnostics_list] == ["b1", "b2", "a1"],
            "expected diagnostics in file then diagnostic order",
        )
        assert_with_context(
            [patch.splitlines()[0] for patch in totals.patches]
            == ["--- a/b.md", "--- a/a.md"],
            "expected one patch per file that produced a plan, in file order",
        )
        assert_with_context(
            [item.identifier for item in totals.fix_errors] == ["b-refusal"],
            "expected fix errors only from files whose plan refused an edit",
        )
        assert not totals.error, "expected a run with no failures to be error-free"

    def test_any_failed_file_makes_the_whole_run_an_operational_error(self) -> None:
        """One failed file is enough to set the run's error flag."""
        results = [
            checked_file("a.md", ["a1"]),
            cli_pipeline.CheckedFile("b.md", cli_pipeline.FileCheck([], failed=True)),
            checked_file("c.md", ["c1"]),
        ]

        totals = cli_pipeline.aggregate_checked_files(results)

        assert totals.error, "expected a failed file to raise the run's error flag"
        assert_with_context(
            [item.message for item in totals.diagnostics_list] == ["a1", "c1"],
            "expected a failed file neither to stop the pass nor add diagnostics",
        )

    def test_an_empty_run_aggregates_to_an_empty_success(self) -> None:
        """The empty case is the identity: no diagnostics, no patches, no error."""
        totals = cli_pipeline.aggregate_checked_files([])

        assert_with_context(
            (
                totals.diagnostics_list,
                totals.fix_errors,
                totals.patches,
                totals.error,
            )
            == ([], [], [], False),
            "expected an empty aggregate",
        )


def _raise_bridge_error(_source: str, _syntax: object) -> None:
    """Raise the deterministic extractor failure used by these tests."""
    message = "bridge exploded"
    raise engine.BridgeExtractionError(message)


def _raise_adapter_error(_source: str, _syntax: object) -> None:
    """Raise an unexpected adapter failure used by these tests."""
    message = "adapter exploded"
    raise TypeError(message)
