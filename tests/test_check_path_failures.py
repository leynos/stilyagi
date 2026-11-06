"""Resolution failures at the per-file check boundary.

The glob anchor for a checked file is resolved from the working directory or
the governing config file, and either can fail for an environmental reason.
These tests pin that such a failure is reported against the file being checked
rather than escaping as an unexplained rules-phase error, and that it does not
abandon the files that follow it.
"""

import pathlib
import typing as typ

from stilyagi import check_execution, check_metrics, cli_run, config, diagnostics

from tests.support.check_pipeline_fixtures import (
    forbidden_runner,
    input_for,
    recording_reporter,
    run_for,
)

if typ.TYPE_CHECKING:
    import pytest
    from stilyagi.rules.registry import RuleRunRequest

_OPERATIONAL_FAILURES = "stilyagi_check_operational_failures_total"


class _MissingWorkingDirectoryError(FileNotFoundError):
    """A working directory that no longer exists."""

    def __init__(self) -> None:
        """Build the failure with its message inside the class."""
        super().__init__("working directory disappeared")


class _UnresolvableTargetError(RuntimeError):
    """A path whose resolution never terminates."""

    def __init__(self) -> None:
        """Build the failure with its message inside the class."""
        super().__init__("Symlink loop from 'notes.md'")


def _stub_config_resolution(
    monkeypatch: pytest.MonkeyPatch,
    *,
    config_file: pathlib.Path | None,
) -> None:
    """Fix the resolved configuration so only path resolution can fail."""
    resolved = config.ResolvedTargetConfig(config.StilyagiConfig(), config_file)

    def fake_resolve_target_config(
        _target: pathlib.Path,
        _options: object,
        _resolver: config.ConfigResolver,
    ) -> config.ResolvedTargetConfig:
        """Return the fixed resolution without consulting any resolver."""
        return resolved

    monkeypatch.setattr(
        check_execution, "resolve_target_config", fake_resolve_target_config
    )


def _operational_failures() -> dict[str, int]:
    """Return the recorded per-phase operational failure counts."""
    snapshot = check_metrics.check_metrics_snapshot()
    return typ.cast("dict[str, int]", snapshot[_OPERATIONAL_FAILURES])


def test_a_missing_working_directory_is_reported_in_the_config_phase(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A deleted working directory fails this file, not the whole run.

    With no governing config file the glob anchor is the working directory, so
    resolving it can fail for an environmental reason. That failure belongs to
    the file being checked: the remaining files are still checkable, and the
    user is told which one was not.
    """
    target = tmp_path / "notes.md"
    target.write_text("# Notes\n", encoding="utf-8")
    _stub_config_resolution(monkeypatch, config_file=None)
    rule_runs: list[object] = []

    def missing_cwd() -> pathlib.Path:
        """Stand in for a working directory that no longer exists."""
        raise _MissingWorkingDirectoryError

    check_metrics.reset_check_metrics()
    failures, report = recording_reporter()
    with monkeypatch.context() as patch:
        patch.setattr(pathlib.Path, "cwd", missing_cwd)
        result = check_execution.check_one_file(
            input_for(target),
            run_for(forbidden_runner(rule_runs), report),
        )

    assert result.had_error, "expected the failed anchor to flag the result"
    assert failures[0][0] == pathlib.Path("notes.md"), (
        "expected the failure to name the file being checked"
    )
    assert isinstance(failures[0][1], FileNotFoundError), (
        "expected the working-directory failure to reach the reporter"
    )
    assert _operational_failures()["config"] == 1, (
        "expected the failure to be counted against the config phase"
    )
    assert _operational_failures()["rules"] == 0, (
        "expected no rules-phase failure to be recorded"
    )
    assert not rule_runs, "expected no rule to run after a config failure"


def test_an_unresolvable_target_is_reported_in_the_config_phase(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A symlink loop while resolving the target is a per-file failure.

    The config file resolves first, so the replacement fails only for the
    target. That keeps the test honest: it would fail if target resolution were
    removed, because the config file alone would then succeed.
    """
    target = tmp_path / "notes.md"
    target.write_text("# Notes\n", encoding="utf-8")
    _stub_config_resolution(monkeypatch, config_file=tmp_path / "stilyagi.toml")
    rule_runs: list[object] = []

    def looping_resolve(
        self: pathlib.Path, *_args: object, **_kwargs: object
    ) -> pathlib.Path:
        """Fail the target's resolution and let every other path resolve."""
        if self == target:
            raise _UnresolvableTargetError
        return self

    check_metrics.reset_check_metrics()
    failures, report = recording_reporter()
    with monkeypatch.context() as patch:
        patch.setattr(pathlib.Path, "resolve", looping_resolve)
        result = check_execution.check_one_file(
            input_for(target),
            run_for(forbidden_runner(rule_runs), report),
        )

    assert result.had_error, "expected the failed resolution to flag the result"
    assert failures[0][0] == pathlib.Path("notes.md"), (
        "expected the failure to name the file being checked"
    )
    assert isinstance(failures[0][1], RuntimeError), (
        "expected the resolution failure to reach the reporter"
    )
    assert _operational_failures()["config"] == 1, (
        "expected the failure to be counted against the config phase"
    )
    assert _operational_failures()["rules"] == 0, (
        "expected no rules-phase failure to be recorded"
    )
    assert not rule_runs, "expected no rule to run after a config failure"


def test_a_later_file_is_still_checked_after_an_earlier_resolution_failure(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One file's failed anchor does not abandon the files that follow it."""
    first = tmp_path / "first.md"
    second = tmp_path / "second.md"
    first.write_text("# First\n", encoding="utf-8")
    second.write_text("# Second\n", encoding="utf-8")
    _stub_config_resolution(monkeypatch, config_file=tmp_path / "stilyagi.toml")

    def looping_resolve(
        self: pathlib.Path, *_args: object, **_kwargs: object
    ) -> pathlib.Path:
        """Fail only the first file's resolution."""
        if self == first:
            raise _UnresolvableTargetError
        return self

    def reporting_runner(request: RuleRunRequest) -> list[diagnostics.Diagnostic]:
        """Return one diagnostic naming the file the rules phase saw."""
        return [
            diagnostics.Diagnostic(
                path=request.reported_path, code="PUN201", message="x"
            )
        ]

    failures, report = recording_reporter()
    with monkeypatch.context() as patch:
        patch.setattr(pathlib.Path, "resolve", looping_resolve)
        checked = cli_run.collect_checked_files(
            [input_for(first), input_for(second)],
            run_for(reporting_runner, report),
        )

    assert checked[0].result.had_error, "expected the first file to fail"
    assert not checked[0].result.diagnostics, (
        "expected the failed file to contribute no diagnostics"
    )
    assert [item.path for item in checked[1].result.diagnostics] == ["second.md"], (
        "expected the later file to keep its diagnostic"
    )
    assert not checked[1].result.had_error, "expected the later file to succeed"
    assert [path for path, _ in failures] == [pathlib.Path("first.md")], (
        "expected only the first file to be reported"
    )
