"""Logging behaviour tests for the structural performance probe."""

import logging
import pathlib
import subprocess  # ruff: ignore[suspicious-subprocess-import] -- justified: typing a simulated child process result and invoking the probe CLI under test
import sys
from unittest import mock

import pytest
from stilyagi import model

from tests.performance import structural_probe, structural_probe_execution

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[1]
MARKDOWN_FIXTURE = REPOSITORY_ROOT / (
    "tests/fixtures/corpus/markdown/valid/heading-table-link-suppression.md"
)
MARKDOWN_STRUCTURAL_FIXTURE = structural_probe.StructuralFixture(
    MARKDOWN_FIXTURE,
    model.Syntax.MARKDOWN,
)


def _messages(caplog: pytest.LogCaptureFixture) -> list[str]:
    """Return every captured log message in emission order."""
    return [record.getMessage() for record in caplog.records]


def _level_of(caplog: pytest.LogCaptureFixture, prefix: str) -> int | None:
    """Return the level of the first captured message with this prefix."""
    for record in caplog.records:
        if record.getMessage().startswith(prefix):
            return record.levelno
    return None


def _empty_report() -> structural_probe.ReportPayload:
    """Return a report with no measured runs for write-path tests."""
    return structural_probe.build_report(
        repository_root=REPOSITORY_ROOT,
        fixtures=(MARKDOWN_STRUCTURAL_FIXTURE,),
        runs=[],
    )


def test_discover_structural_fixtures_logs_each_resolved_path(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Record every resolved fixture path at DEBUG level."""
    caplog.set_level(logging.DEBUG, logger=structural_probe.__name__)

    fixtures = structural_probe.discover_structural_fixtures(REPOSITORY_ROOT)

    messages = _messages(caplog)
    for fixture in fixtures:
        assert f"fixture discovered: path={fixture.path}" in messages, (
            f"expected a discovery log for {fixture.path}; got {messages}"
        )
    assert _level_of(caplog, "fixture discovered: path=") == logging.DEBUG, (
        f"expected DEBUG level; got {_level_of(caplog, 'fixture discovered: path=')}"
    )


def test_missing_fixture_is_logged_before_raising(
    caplog: pytest.LogCaptureFixture,
    tmp_path: pathlib.Path,
) -> None:
    """Report the missing fixture path at ERROR level before failing."""
    caplog.set_level(logging.ERROR, logger=structural_probe.__name__)

    with pytest.raises(FileNotFoundError, match="structural fixture is missing"):
        structural_probe.discover_structural_fixtures(tmp_path)

    messages = _messages(caplog)
    assert any(
        message.startswith("structural fixture is missing: path=")
        for message in messages
    ), f"expected a missing-fixture error log; got {messages}"
    assert _level_of(caplog, "structural fixture is missing: path=") == logging.ERROR, (
        "expected the missing-fixture log at ERROR level"
    )


def test_write_report_logs_the_output_path(
    caplog: pytest.LogCaptureFixture,
    tmp_path: pathlib.Path,
) -> None:
    """Record the resolved output path at DEBUG level before writing."""
    caplog.set_level(logging.DEBUG, logger=structural_probe.__name__)
    output_path = tmp_path / "structural-baseline.json"

    structural_probe.write_report(_empty_report(), output_path)

    messages = _messages(caplog)
    assert f"writing report: path={output_path.resolve()}" in messages, (
        f"expected a report-write log for {output_path.resolve()}; got {messages}"
    )
    assert _level_of(caplog, "writing report: path=") == logging.DEBUG, (
        "expected the report-write log at DEBUG level"
    )


def test_write_report_logs_oserror_before_reraising(
    caplog: pytest.LogCaptureFixture,
    tmp_path: pathlib.Path,
) -> None:
    """Capture the output path when the report cannot be written."""
    caplog.set_level(logging.ERROR, logger=structural_probe.__name__)
    output_path = tmp_path / "directory-in-the-way"
    output_path.mkdir()

    # Opening a directory for writing raises PermissionError on Windows.
    with pytest.raises((IsADirectoryError, PermissionError)):
        structural_probe.write_report(_empty_report(), output_path)

    messages = _messages(caplog)
    assert any(
        message.startswith(f"report write failed: path={output_path.resolve()}")
        for message in messages
    ), f"expected a report-write error log; got {messages}"
    assert _level_of(caplog, "report write failed: path=") == logging.ERROR, (
        "expected the report-write failure log at ERROR level"
    )


def test_measure_run_logs_entry_and_exit_with_mode_and_iterations(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Record the mode and iteration count around a measurement run."""
    caplog.set_level(logging.DEBUG, logger=structural_probe_execution.__name__)
    source = MARKDOWN_FIXTURE.read_text(encoding="utf-8")

    run = structural_probe_execution._measure_run(
        "warm",
        2,
        source,
        MARKDOWN_STRUCTURAL_FIXTURE,
    )

    messages = _messages(caplog)
    assert "measurement run starting: mode=warm iterations=2" in messages, (
        f"expected a run-start log; got {messages}"
    )
    assert "measurement run finished: mode=warm iterations=2" in messages, (
        f"expected a run-finish log; got {messages}"
    )
    assert _level_of(caplog, "measurement run starting:") == logging.DEBUG, (
        "expected the run-start log at DEBUG level"
    )
    assert _level_of(caplog, "measurement run finished:") == logging.DEBUG, (
        "expected the run-finish log at DEBUG level"
    )
    assert len(run.durations_ns) == 2, f"expected two durations; got {run.durations_ns}"


def test_cold_iteration_logs_command_and_iteration_index(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Record the invocation command and iteration index before spawning."""
    caplog.set_level(logging.DEBUG, logger=structural_probe_execution.__name__)

    def fake_run(
        command: list[str],
        **_kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        """Return a canned child payload without spawning a process."""
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout='{"duration_ns": 42}',
            stderr="",
        )

    with mock.patch.object(structural_probe_execution.subprocess, "run", fake_run):
        duration_ns = structural_probe_execution._measure_cold_iteration(
            MARKDOWN_STRUCTURAL_FIXTURE,
            "cold",
            3,
        )

    assert duration_ns == 42, f"expected the canned duration; got {duration_ns}"
    messages = _messages(caplog)
    assert any(
        message.startswith("cold iteration subprocess: mode=cold iteration=3 command=")
        and "structural_probe" in message
        for message in messages
    ), f"expected a cold-subprocess debug log; got {messages}"
    assert _level_of(caplog, "cold iteration subprocess: mode=cold") == logging.DEBUG, (
        "expected the cold-subprocess log at DEBUG level"
    )


def test_cold_iteration_logs_child_stderr_before_reraising(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Capture child stderr at ERROR level when the subprocess fails."""
    caplog.set_level(logging.ERROR, logger=structural_probe_execution.__name__)

    def failing_run(
        command: list[str],
        **_kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        """Simulate a child process failure with captured stderr."""
        raise subprocess.CalledProcessError(
            returncode=1,
            cmd=command,
            output="",
            stderr="child exploded",
        )

    with (
        mock.patch.object(structural_probe_execution.subprocess, "run", failing_run),
        pytest.raises(subprocess.CalledProcessError),
    ):
        structural_probe_execution._measure_cold_iteration(
            MARKDOWN_STRUCTURAL_FIXTURE,
            "cold",
            4,
        )

    messages = _messages(caplog)
    assert any(
        message.startswith("cold iteration subprocess failed: mode=cold iteration=4")
        and "child exploded" in message
        for message in messages
    ), f"expected a cold-subprocess error log; got {messages}"
    assert (
        _level_of(caplog, "cold iteration subprocess failed: mode=cold")
        == logging.ERROR
    ), "expected the cold-subprocess failure log at ERROR level"


def test_write_report_logs_the_resolved_path_for_a_relative_output(
    caplog: pytest.LogCaptureFixture,
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Log the absolute path when the caller passes a relative output path."""
    caplog.set_level(logging.DEBUG, logger=structural_probe.__name__)
    monkeypatch.chdir(tmp_path)
    output_path = pathlib.Path("build/structural-baseline.json")

    structural_probe.write_report(_empty_report(), output_path)

    resolved_path = (tmp_path / "build/structural-baseline.json").resolve()
    messages = _messages(caplog)
    assert f"writing report: path={resolved_path}" in messages, (
        f"expected the resolved report path; got {messages}"
    )


def test_cli_debug_logging_reaches_stderr(tmp_path: pathlib.Path) -> None:
    """Expose probe diagnostics on stderr when the CLI enables DEBUG."""
    output_path = tmp_path / "structural-baseline.json"

    completed = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] -- justified: exercising the documented CLI entry point with a fixed argument list
        [
            sys.executable,
            "-m",
            "tests.performance.structural_probe",
            "--mode",
            "warm",
            "--iterations",
            "1",
            "--output",
            str(output_path),
            "--log-level",
            "DEBUG",
        ],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert output_path.is_file(), f"expected a report at {output_path}"
    assert "DEBUG" in completed.stderr, (
        f"expected DEBUG records on stderr; got {completed.stderr}"
    )
    assert "fixture discovered: path=" in completed.stderr, (
        f"expected fixture discovery logs on stderr; got {completed.stderr}"
    )
    assert f"writing report: path={output_path.resolve()}" in completed.stderr, (
        f"expected the resolved report path on stderr; got {completed.stderr}"
    )
