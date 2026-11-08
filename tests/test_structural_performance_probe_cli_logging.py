"""Command-line logging tests for the structural performance probe.

The end-to-end tests spawn ``python -m tests.performance.structural_probe``
against a temporary output path, so they verify the documented operator
workflow rather than the logging calls in isolation. The configuration tests
check that the requested level reaches the logging setup. Unit-level record
assertions live in ``tests/test_structural_performance_probe_logging.py``.

Run this module with
``pytest tests/test_structural_performance_probe_cli_logging.py``.
"""

import pathlib
import subprocess  # ruff: ignore[suspicious-subprocess-import] -- justified: invoking the probe CLI under test
import sys

import pytest

from tests.performance import structural_probe

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[1]

LOG_FORMAT = "%(levelname)s %(name)s: %(message)s"


@pytest.mark.parametrize("log_level", ["DEBUG", "INFO", "WARNING", "ERROR"])
def test_configure_logging_passes_the_requested_level(
    log_level: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pass each requested CLI level through to the logging configuration."""
    calls: list[dict[str, object]] = []

    def fake_basic_config(**kwargs: object) -> None:
        """Record the logging configuration keyword arguments."""
        calls.append(kwargs)

    monkeypatch.setattr(structural_probe.logging, "basicConfig", fake_basic_config)
    structural_probe._configure_logging(log_level)

    assert calls == [{"level": log_level, "format": LOG_FORMAT}], (
        f"expected the requested level; got {calls}"
    )


def test_configure_logging_is_skipped_without_a_level(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Leave logging unconfigured when the CLI option is absent."""
    calls: list[dict[str, object]] = []

    def fake_basic_config(**kwargs: object) -> None:
        """Record the logging configuration keyword arguments."""
        calls.append(kwargs)

    monkeypatch.setattr(structural_probe.logging, "basicConfig", fake_basic_config)
    structural_probe._configure_logging(None)

    assert not calls, f"expected no logging configuration; got {calls}"


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


@pytest.mark.parametrize("log_level", ["INFO", "WARNING", "ERROR"])
def test_cli_non_debug_levels_suppress_debug_records(
    tmp_path: pathlib.Path,
    log_level: str,
) -> None:
    """Honour the requested level instead of always enabling DEBUG."""
    output_path = tmp_path / f"baseline-{log_level.lower()}.json"

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
            log_level,
        ],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert output_path.is_file(), f"expected a report at {output_path}"
    assert "DEBUG" not in completed.stderr, (
        f"expected no DEBUG records at {log_level}; got {completed.stderr}"
    )
    assert "fixture discovered:" not in completed.stderr, (
        f"expected discovery records to be filtered; got {completed.stderr}"
    )


def test_cli_error_level_still_reports_write_failures(tmp_path: pathlib.Path) -> None:
    """Emit ERROR records while suppressing DEBUG records."""
    output_path = tmp_path / "directory-in-the-way"
    output_path.mkdir()

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
            "ERROR",
        ],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0, "expected the unwritable report to fail"
    assert f"report write failed: path={output_path.resolve()}" in completed.stderr, (
        f"expected the write failure at ERROR level; got {completed.stderr}"
    )
    assert "DEBUG" not in completed.stderr, (
        f"expected no DEBUG records at ERROR; got {completed.stderr}"
    )


def test_cli_without_log_level_keeps_failure_output_single(
    tmp_path: pathlib.Path,
) -> None:
    """Avoid logging's last-resort handler duplicating an uncaught traceback."""
    output_path = tmp_path / "directory-in-the-way"
    output_path.mkdir()

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
        ],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0, "expected the unwritable report to fail"
    assert "report write failed: path=" not in completed.stderr, (
        f"expected no logging fallback output; got {completed.stderr}"
    )
    assert completed.stderr.count("Traceback (most recent call last)") == 1, (
        f"expected exactly one traceback; got {completed.stderr}"
    )
