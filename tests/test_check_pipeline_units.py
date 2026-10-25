"""Unit coverage for the per-file check workflow and its aggregation.

These tests drive `check_execution` and `cli_run` directly, so they pin the
boundaries the refactor introduced: the named per-file result and the typed
read error in `check_execution`, and the single aggregation pass in `cli_run`.
The command-boundary behaviour that exercises the same code through
`cli.run_check` -- injected streams, injected reporters, and the two diff
outcomes -- lives in `tests/test_check_boundaries.py`.

Run them with:

    make test

or, for this module alone:

    .venv/bin/python -m pytest tests/test_check_pipeline_units.py
"""

import typing as typ

import pytest
from stilyagi import check_execution, check_inputs, cli_io, cli_run, config, engine

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
    import collections.abc as cabc
    import pathlib


def _make_directory(root: pathlib.Path) -> pathlib.Path:
    """Return a directory path, which cannot be read as a file."""
    target = root / "docs"
    target.mkdir()
    return target


def _make_undecodable(root: pathlib.Path) -> pathlib.Path:
    """Return a file holding bytes that are not valid UTF-8."""
    target = root / "broken.md"
    target.write_bytes(b"\xff")
    return target


class TestCheckOneFile:
    """The per-file workflow returns a named result and reports failures."""

    def test_a_readable_file_yields_a_named_result_carrying_its_diagnostics(
        self, tmp_path: pathlib.Path
    ) -> None:
        """A readable file produces diagnostics and no failure flag."""
        target = tmp_path / "notes.md"
        target.write_text("# Notes\n", encoding="utf-8")
        failures, report = recording_reporter()

        result = check_execution.check_one_file(
            input_for(target),
            run_for(one_diagnostic_runner, report),
        )

        assert isinstance(result, check_inputs.FileCheckResult), (
            "expected a named FileCheckResult rather than an anonymous tuple"
        )
        assert_with_context(
            [item.code for item in result.diagnostics] == ["PUN201"],
            "expected the injected rule runner's diagnostic to be collected",
        )
        assert not result.had_error, "expected a readable file not to fail"
        assert result.planned is None, "expected no plan without --fix or --diff"
        assert not failures, "expected no reported failure for a readable file"

    def test_a_missing_file_reports_a_typed_read_error_and_flags_the_result(
        self, tmp_path: pathlib.Path
    ) -> None:
        """A vanished file yields a SourceReadError through the reporter."""
        target = tmp_path / "gone.md"
        failures, report = recording_reporter()

        result = check_execution.check_one_file(
            input_for(target),
            run_for(silent_runner, report),
        )

        assert result.had_error, "expected a missing file to flag the result"
        assert not result.diagnostics, "expected no diagnostics from a failure"
        assert len(failures) == 1, "expected exactly one reported failure"
        path, error = failures[0]
        # The two paths are deliberately different values. The reporter is
        # handed the *reported* path, which is the command-line-relative
        # identity the run summary and every diagnostic use; the typed error
        # still carries the resolved path the read actually attempted, so a
        # caller that needs to name the file on disk has it. Asserting both
        # keeps a future edit from collapsing them back into one.
        assert path is not None, (
            "expected the failure to name a path rather than nothing"
        )
        assert path.as_posix() == target.name, (
            "expected the failure to name the reported path"
        )
        assert isinstance(error, cli_io.SourceReadError), (
            "expected the typed read error rather than the bare OS error"
        )
        assert error.path == target, (
            "expected the typed error to retain the resolved path"
        )
        assert isinstance(error.error, OSError), (
            "expected the typed error to retain the underlying OS error"
        )

    @pytest.mark.parametrize(
        ("corrupt", "expected"),
        [
            pytest.param(_make_directory, IsADirectoryError, id="directory"),
            pytest.param(_make_undecodable, UnicodeDecodeError, id="undecodable"),
        ],
    )
    def test_an_unreadable_target_reports_its_underlying_oserror(
        self,
        tmp_path: pathlib.Path,
        corrupt: cabc.Callable[[pathlib.Path], pathlib.Path],
        expected: type[OSError],
    ) -> None:
        """Every read failure is wrapped in the typed error, keeping its cause.

        A directory and undecodable bytes fail for different reasons, but the
        contract the boundary owes a caller is the same for both: one
        `SourceReadError` naming the path, retaining the underlying `OSError`
        subclass so a caller can tell a directory from a decode failure. The
        two cases are held here together so that contract is stated once, while
        the parametrized id keeps a regression naming the target that broke.
        """
        target = corrupt(tmp_path)
        failures, report = recording_reporter()

        result = check_execution.check_one_file(
            input_for(target),
            run_for(silent_runner, report),
        )

        assert result.had_error, "expected an unreadable target to flag the result"
        error = failures[0][1]
        assert isinstance(error, cli_io.SourceReadError), (
            "expected the read failure to be wrapped in the typed error"
        )
        assert isinstance(error.error, expected), (
            f"expected the underlying failure to be {expected.__name__}"
        )

    def test_a_bridge_extraction_failure_is_reported_rather_than_raised(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A bridge refusal is expected and becomes a reported failure."""
        target = tmp_path / "notes.md"
        target.write_text("# Notes\n", encoding="utf-8")
        failures, report = recording_reporter()
        monkeypatch.setattr(engine, "extract_document", _raise_bridge_error)

        result = check_execution.check_one_file(
            input_for(target),
            run_for(silent_runner, report),
        )

        assert result.had_error, "expected a bridge refusal to flag the result"
        assert not result.diagnostics, "expected no diagnostics on refusal"
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
            check_execution.check_one_file(
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

        result = check_execution.check_one_file(
            input_for(target),
            run_for(silent_runner, report),
        )

        assert result.had_error, "expected invalid config to flag the result"
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

        totals = cli_run.aggregate_checked_files(results)

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
            cli_run.CheckedFile(
                "b.md",
                check_inputs.FileCheckResult([], had_error=True, was_unreadable=False),
            ),
            checked_file("c.md", ["c1"]),
        ]

        totals = cli_run.aggregate_checked_files(results)

        assert totals.error, "expected a failed file to raise the run's error flag"
        assert_with_context(
            [item.message for item in totals.diagnostics_list] == ["a1", "c1"],
            "expected a failed file neither to stop the pass nor add diagnostics",
        )

    def test_an_empty_run_aggregates_to_an_empty_success(self) -> None:
        """The empty case is the identity: no diagnostics, no patches, no error."""
        totals = cli_run.aggregate_checked_files([])

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


def _raise_bridge_error(
    _source: str,
    _syntax: object,
    **_kwargs: object,
) -> None:
    """Raise the deterministic extractor failure used by these tests."""
    message = "bridge exploded"
    raise engine.BridgeExtractionError(message)


def _raise_adapter_error(
    _source: str,
    _syntax: object,
    **_kwargs: object,
) -> None:
    """Raise an unexpected adapter failure used by these tests."""
    message = "adapter exploded"
    raise TypeError(message)
