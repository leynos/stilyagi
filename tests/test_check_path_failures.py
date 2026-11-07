"""Resolution failures at the per-file check boundary.

The glob anchor for a checked file is resolved from the working directory or
the governing config file, and either can fail for an environmental reason.
These tests pin that such a failure is reported against the file being checked
rather than escaping as an unexplained rules-phase error, and that it does not
abandon the files that follow it.
"""

import pathlib
import typing as typ

import pytest
from stilyagi import (
    check_execution,
    check_metrics,
    cli,
    cli_run,
    config,
    diagnostics,
)

from tests.support.check_pipeline_fixtures import (
    forbidden_runner,
    input_for,
    recording_reporter,
    run_for,
)

if typ.TYPE_CHECKING:
    from stilyagi.rules.registry import RuleRunRequest

_OPERATIONAL_FAILURES = "stilyagi_check_operational_failures_total"


class _MissingWorkingDirectoryError(FileNotFoundError):
    """A working directory that no longer exists."""

    def __init__(self) -> None:
        """Build the failure with its message inside the class."""
        super().__init__("working directory disappeared")


class _UnresolvedHomeDirectoryError(RuntimeError):
    """The error ``Path.expanduser`` raises when it cannot find a home.

    Deliberately not a :class:`config.PathResolutionError`: the expansion sites
    are supposed to convert this into one, and a stub that already raised the
    named type would let a regression that dropped the conversion pass.
    """

    def __init__(self) -> None:
        """Build the failure with the message pathlib itself raises."""
        super().__init__("Could not determine home directory.")


class _PathFailureError(config.PathResolutionError):
    """The named failure, raised where ``expand_user`` is bypassed."""

    def __init__(self) -> None:
        """Build the failure with its message inside the class."""
        super().__init__("Could not determine home directory.")


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


def test_an_unresolved_home_directory_is_reported_in_the_config_phase(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unresolved home directory while expanding the target is per-file.

    ``Path.expanduser`` raises ``RuntimeError`` when it cannot determine the
    home directory, which is the genuine failure the config phase must absorb.
    The expansion site converts it to ``PathResolutionError``, so the executor
    can absorb that named failure without also absorbing a programming error.
    The config file expands first, so the replacement fails only for the
    target. That keeps the test honest: it would fail if target expansion were
    removed, because the config file alone would then succeed.
    """
    target = tmp_path / "notes.md"
    target.write_text("# Notes\n", encoding="utf-8")
    _stub_config_resolution(monkeypatch, config_file=tmp_path / "stilyagi.toml")
    rule_runs: list[object] = []

    def unresolvable_home(
        self: pathlib.Path, *_args: object, **_kwargs: object
    ) -> pathlib.Path:
        """Fail the target's expansion and let every other path expand."""
        if self == target:
            raise _UnresolvedHomeDirectoryError
        return self

    check_metrics.reset_check_metrics()
    failures, report = recording_reporter()
    with monkeypatch.context() as patch:
        patch.setattr(pathlib.Path, "expanduser", unresolvable_home)
        result = check_execution.check_one_file(
            input_for(target),
            run_for(forbidden_runner(rule_runs), report),
        )

    assert result.had_error, "expected the failed resolution to flag the result"
    assert failures[0][0] == pathlib.Path("notes.md"), (
        "expected the failure to name the file being checked"
    )
    assert isinstance(failures[0][1], config.PathResolutionError), (
        "expected the expansion failure to arrive as the named path error"
    )
    assert _operational_failures()["config"] == 1, (
        "expected the failure to be counted against the config phase"
    )
    assert _operational_failures()["rules"] == 0, (
        "expected no rules-phase failure to be recorded"
    )
    assert not rule_runs, "expected no rule to run after a config failure"


def test_an_unexpected_runtime_error_is_not_absorbed_as_a_file_failure(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A programming error must propagate, not be reported as a file failure.

    Only the named path failure is an environmental condition the config phase
    absorbs. A bare ``RuntimeError`` from anywhere else is a defect, and
    reporting it as an ordinary per-file failure would hide it behind a
    plausible message and a non-zero exit code.
    """

    class _UnexpectedRuntimeError(RuntimeError):
        """A defect that happens to be a runtime error."""

        def __init__(self) -> None:
            """Build the defect with its message inside the class."""
            super().__init__("a defect, not an environment")

    target = tmp_path / "notes.md"
    target.write_text("# Notes\n", encoding="utf-8")
    _stub_config_resolution(monkeypatch, config_file=None)

    def broken_anchor(_target: pathlib.Path, _config_file: pathlib.Path | None) -> str:
        """Fail with a defect rather than an environmental condition."""
        raise _UnexpectedRuntimeError

    check_metrics.reset_check_metrics()
    failures, report = recording_reporter()
    monkeypatch.setattr(check_execution, "config_relative_path_for", broken_anchor)

    with pytest.raises(_UnexpectedRuntimeError):
        check_execution.check_one_file(
            input_for(target),
            run_for(forbidden_runner([]), report),
        )

    assert not failures, "expected the defect not to be reported as a file failure"
    assert _operational_failures()["config"] == 0, (
        "expected the defect not to be counted against the config phase"
    )


def test_a_later_file_is_still_checked_after_an_earlier_resolution_failure(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One file's failed anchor does not abandon the files that follow it."""
    first = tmp_path / "first.md"
    second = tmp_path / "second.md"
    first.write_text("# First\n", encoding="utf-8")
    second.write_text("# Second\n", encoding="utf-8")
    _stub_config_resolution(monkeypatch, config_file=tmp_path / "stilyagi.toml")

    def unresolvable_home(
        self: pathlib.Path, *_args: object, **_kwargs: object
    ) -> pathlib.Path:
        """Fail only the first file's expansion."""
        if self == first:
            raise _UnresolvedHomeDirectoryError
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
        patch.setattr(pathlib.Path, "expanduser", unresolvable_home)
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


def test_the_command_still_checks_a_later_file_after_a_resolution_failure(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The command's own loop must not abandon the files after a failure.

    The helper-level cases above drive `collect_checked_files` directly. This
    one goes through `cli.main` so the command boundary is covered too: the
    command delegates its per-file loop to that helper, and a regression that
    reintroduced a second loop which stopped early would otherwise stay
    invisible.
    """
    first = tmp_path / "first.md"
    second = tmp_path / "second.md"
    first.write_text("# First\n", encoding="utf-8")
    second.write_text("# Second\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    resolve_normally = check_execution.config_relative_path_for

    def failing_first(target: pathlib.Path, config_file: pathlib.Path | None) -> str:
        """Fail the first file's anchor and resolve every other file normally."""
        if target.name == first.name:
            raise _PathFailureError
        return resolve_normally(target, config_file)

    def reporting_runner(request: RuleRunRequest) -> list[diagnostics.Diagnostic]:
        """Return one diagnostic naming the file the rules phase saw."""
        return [
            diagnostics.Diagnostic(
                path=request.reported_path, code="PUN201", message="x"
            )
        ]

    monkeypatch.setattr(check_execution, "config_relative_path_for", failing_first)
    monkeypatch.setattr("stilyagi.rules.registry.run_rules", reporting_runner)
    check_metrics.reset_check_metrics()

    exit_code = cli.main(["check", "."])

    captured = capsys.readouterr()
    assert exit_code == 2, "expected the failed file to make the run an error"
    assert "second.md" in captured.out, "expected the later file to keep its diagnostic"
    assert "first.md" in captured.err, (
        "expected the failure to name the file being checked"
    )
