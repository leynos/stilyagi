"""Tests for detector subprocess failure modes.

Every way the pinned ``nose`` subprocess can fail — a timeout, a non-zero
exit, or an unrunnable executable — must become an actionable gate execution
error rather than a traceback.
"""

import typing as typ

import pytest
from duplication_gate_test_support import detector, stub_settings

if typ.TYPE_CHECKING:
    from collections import abc as cabc


class TestRunDetectorExecution:
    """Subprocess execution failures from the detector wrapper."""

    def test_rejects_unreadable_output(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Non-JSON detector output fails with an execution error."""
        monkeypatch.setenv("NOSE_BIN", "/stub/nose")

        def runner(command: cabc.Sequence[str]) -> str:
            """Answer the version probe, then emit unparseable output."""
            return "nose 0.20.0\n" if "--version" in command else "not json"

        with pytest.raises(detector.GateExecutionError, match="not valid JSON"):
            detector.run_detector(stub_settings(), runner=runner)

    def test_run_command_reports_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A slow detector becomes an actionable execution error."""

        def timeout(*_args: object, **_kwargs: object) -> typ.NoReturn:
            """Fail the subprocess the way an exceeded timeout does."""
            raise detector.subprocess.TimeoutExpired(["nose", "query"], 120)

        monkeypatch.setattr(detector.subprocess, "run", timeout)

        with pytest.raises(
            detector.GateExecutionError, match="timed out after 120 seconds"
        ):
            detector._run_command(("nose", "query"))

    def test_run_command_reports_a_non_zero_exit(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A detector that fails carries its status and diagnostic out."""

        def failing(
            *_args: object, **_kwargs: object
        ) -> detector.subprocess.CompletedProcess[str]:
            """Report a non-zero exit with a diagnostic on stderr."""
            return detector.subprocess.CompletedProcess(
                args=["nose", "query"], returncode=2, stdout="", stderr="bad query\n"
            )

        monkeypatch.setattr(detector.subprocess, "run", failing)

        with pytest.raises(
            detector.GateExecutionError,
            match=r"nose exited with status 2: bad query",
        ):
            detector._run_command(("nose", "query"))

    def test_run_command_reports_an_execution_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An unrunnable detector points at the install remediation."""

        def unrunnable(*_args: object, **_kwargs: object) -> typ.NoReturn:
            """Fail the subprocess the way an unexecutable binary does."""
            raise OSError(13, "Permission denied")

        monkeypatch.setattr(detector.subprocess, "run", unrunnable)

        with pytest.raises(
            detector.GateExecutionError,
            match=r"cannot run nose: .*Permission denied.*make install-nose",
        ):
            detector._run_command(("nose", "query"))
