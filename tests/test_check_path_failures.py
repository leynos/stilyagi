"""Resolution failures at the per-file check boundary.

The glob anchor for a checked file is resolved from the working directory or
the governing config file, and either can fail for an environmental reason.
These tests pin that such a failure is reported against the file being checked
rather than escaping as an unexplained rules-phase error.
"""

import pathlib
import typing as typ

from stilyagi import check_execution, config

from tests.support.check_pipeline_fixtures import (
    forbidden_runner,
    input_for,
    recording_reporter,
    run_for,
)

if typ.TYPE_CHECKING:
    import pytest


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

    failures, report = recording_reporter()
    with monkeypatch.context() as patch:
        patch.setattr(pathlib.Path, "cwd", missing_cwd)
        result = check_execution.check_one_file(
            input_for(target),
            run_for(forbidden_runner(rule_runs), report),
        )

    assert result.had_error, "expected the failed anchor to flag the result"
    assert isinstance(failures[0][1], FileNotFoundError), (
        "expected the working-directory failure to reach the reporter"
    )
    assert not rule_runs, "expected no rule to run after a config failure"


def test_an_unresolvable_target_is_reported_in_the_config_phase(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A symlink loop while resolving the target is a per-file failure."""
    target = tmp_path / "notes.md"
    target.write_text("# Notes\n", encoding="utf-8")
    _stub_config_resolution(monkeypatch, config_file=tmp_path / "stilyagi.toml")
    rule_runs: list[object] = []

    def looping_resolve(
        _self: pathlib.Path, *_args: object, **_kwargs: object
    ) -> pathlib.Path:
        """Stand in for a path whose resolution never terminates."""
        raise _UnresolvableTargetError

    failures, report = recording_reporter()
    with monkeypatch.context() as patch:
        patch.setattr(pathlib.Path, "resolve", looping_resolve)
        result = check_execution.check_one_file(
            input_for(target),
            run_for(forbidden_runner(rule_runs), report),
        )

    assert result.had_error, "expected the failed resolution to flag the result"
    assert isinstance(failures[0][1], RuntimeError), (
        "expected the resolution failure to reach the reporter"
    )
    assert not rule_runs, "expected no rule to run after a config failure"
