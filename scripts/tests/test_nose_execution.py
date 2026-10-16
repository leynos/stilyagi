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


class TestEmptyScope:
    """A root that selects no source files must not read as a clean scan."""

    def test_rejects_a_scope_that_selected_nothing(self) -> None:
        """Nose's empty-scope diagnostic becomes a gate execution error.

        nose exits 0 with an empty family list for a root that exists but holds
        nothing it can parse, which is the same report a genuinely clean scan
        produces. The stderr warning is the only signal distinguishing them.
        """
        with pytest.raises(
            detector.GateExecutionError,
            match=r"scanned no source files: warning: no supported source "
            r"files found under: /nowhere",
        ):
            detector._reject_empty_scope(
                "warning: no supported source files found under: /nowhere\n"
                "  (supported extensions: py/pyi, rs)\n"
            )

    def test_accepts_a_scope_that_selected_files(self) -> None:
        """A scan that found files leaves the diagnostic path alone.

        Silent stderr covers both a clean scan and one with findings; a run
        that reports no families is the gate's healthy state, so the guard must
        key on nose's own warning rather than on an empty family list.
        """
        detector._reject_empty_scope("")

    def test_the_run_command_boundary_enforces_the_guard(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`_run_command` applies the guard to the detector's stderr."""

        def empty_scope(
            *_args: object, **_kwargs: object
        ) -> detector.subprocess.CompletedProcess[str]:
            """Report success with an empty family list and the scope warning."""
            return detector.subprocess.CompletedProcess(
                args=["nose", "query"],
                returncode=0,
                stdout='{"families": [], "summary": {"families": 0}}',
                stderr="warning: no supported source files found under: planted\n",
            )

        monkeypatch.setattr(detector.subprocess, "run", empty_scope)

        with pytest.raises(detector.GateExecutionError, match="scanned no source"):
            detector._run_command(("nose", "query"))
