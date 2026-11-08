"""Unit logging behaviour tests for the structural performance probe.

The probe is an operator-run benchmark rather than production code, so its
diagnostics are exercised by driving the probe helpers directly and inspecting
the captured records with ``caplog``. End-to-end assertions over the real
command line live in
``tests/test_structural_performance_probe_cli_logging.py``.

Run this module with
``pytest tests/test_structural_performance_probe_logging.py``.
"""

import logging
import pathlib
import subprocess  # ruff: ignore[suspicious-subprocess-import] -- justified: typing a simulated child process result and its failure
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


def test_discover_fixtures_logs_each_resolved_path(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Record every resolved fixture path at DEBUG level at the boundary."""
    caplog.set_level(logging.DEBUG, logger=structural_probe_execution.__name__)

    fixtures = structural_probe_execution._discover_fixtures(REPOSITORY_ROOT)

    messages = _messages(caplog)
    for fixture in fixtures:
        assert f"fixture discovered: path={fixture.path}" in messages, (
            f"expected a discovery log for {fixture.path}; got {messages}"
        )
    assert _level_of(caplog, "fixture discovered: path=") == logging.DEBUG, (
        f"expected DEBUG level; got {_level_of(caplog, 'fixture discovered: path=')}"
    )


def test_discover_structural_fixtures_emits_no_log_records(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Keep fixture discovery a quiet, repeatable query."""
    caplog.set_level(logging.DEBUG)

    first = structural_probe.discover_structural_fixtures(REPOSITORY_ROOT)
    second = structural_probe.discover_structural_fixtures(REPOSITORY_ROOT)

    assert first == second, "expected discovery to be repeatable"
    assert caplog.records == [], f"expected a quiet query; got {_messages(caplog)}"


def test_missing_fixture_is_logged_before_raising(
    caplog: pytest.LogCaptureFixture,
    tmp_path: pathlib.Path,
) -> None:
    """Report the actual missing fixture path at ERROR level before failing."""
    caplog.set_level(logging.ERROR, logger=structural_probe_execution.__name__)
    missing_path = (tmp_path / structural_probe.MARKDOWN_FIXTURE).as_posix()

    with pytest.raises(FileNotFoundError, match="structural fixture is missing"):
        structural_probe_execution.measure_probe(
            mode="warm",
            iterations=1,
            root=tmp_path,
        )

    messages = _messages(caplog)
    assert "structural fixture discovery failed" in messages, (
        f"expected a missing-fixture error log; got {messages}"
    )
    assert _level_of(caplog, "structural fixture discovery failed") == logging.ERROR, (
        "expected the missing-fixture log at ERROR level"
    )
    failures = [
        record
        for record in caplog.records
        if record.getMessage() == "structural fixture discovery failed"
    ]
    exc_info = failures[0].exc_info
    assert exc_info is not None, "expected the discovery failure context"
    assert isinstance(exc_info[1], FileNotFoundError), (
        f"expected a FileNotFoundError; got {exc_info[1]!r}"
    )
    assert missing_path in str(exc_info[1]), (
        f"expected the missing fixture path; got {exc_info[1]}"
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
    failures = [
        record
        for record in caplog.records
        if record.getMessage().startswith("report write failed: path=")
    ]
    exc_info = failures[0].exc_info
    assert exc_info is not None, "expected the OSError traceback in the record"
    assert isinstance(
        exc_info[1],
        (IsADirectoryError, PermissionError),
    ), f"expected the write error context; got {exc_info[1]!r}"


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


def test_cold_run_logs_each_iteration_index(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Log a distinct iteration index for every cold measurement."""
    caplog.set_level(logging.DEBUG, logger=structural_probe_execution.__name__)
    source = MARKDOWN_FIXTURE.read_text(encoding="utf-8")

    def fake_run(
        command: list[str],
        **_kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        """Return a canned child payload without spawning a process."""
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout='{"duration_ns": 7}',
            stderr="",
        )

    with mock.patch.object(structural_probe_execution.subprocess, "run", fake_run):
        run = structural_probe_execution._measure_run(
            "cold",
            2,
            source,
            MARKDOWN_STRUCTURAL_FIXTURE,
        )

    assert run.durations_ns == (7, 7), f"expected two cold samples; got {run}"
    messages = _messages(caplog)
    for index in (0, 1):
        prefix = f"cold iteration subprocess: mode=cold iteration={index} command="
        assert any(message.startswith(prefix) for message in messages), (
            f"expected an iteration {index} log; got {messages}"
        )


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
