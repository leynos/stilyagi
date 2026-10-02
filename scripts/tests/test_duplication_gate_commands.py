"""Command-line behaviour tests for the duplication gate.

The ``check`` and ``allow`` commands are exercised through their real
argument-parsing boundary with injected readers, detectors, and manifests, so
the CLI contract — exit statuses, diagnostics, and round-tripped allow entries
— is pinned without invoking the pinned detector binary. The separate
boundary module pins how input-loading failures are translated.
"""

import textwrap
import typing as typ
from pathlib import Path

import pytest
from duplication_gate_test_support import (
    allowlist,
    copied_gate_workspace,
    detector,
    gate,
    gate_environment,
    run_gate_command,
    write_stub_nose,
)

if typ.TYPE_CHECKING:
    from syrupy.assertion import SnapshotAssertion


def _finding() -> detector.Finding:
    """Build a representative blocking finding."""
    return detector.Finding(
        witness="copy-paste",
        value=22.1,
        locations=(
            detector.Location(file="python/stilyagi/a.py", start=1, end=20, name=None),
            detector.Location(
                file="python/stilyagi/b.py", start=30, end=49, name="beta"
            ),
        ),
    )


class TestGateCommands:
    """CLI orchestration and diagnostics."""

    def test_check_reports_blocking_findings(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        snapshot: SnapshotAssertion,
    ) -> None:
        """The check command emits the blocking report and status one."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(gate, "load_allowlist", lambda _path: ())
        monkeypatch.setattr(gate, "detect_findings", lambda: [_finding()])
        with pytest.raises(SystemExit) as error:
            gate.check()
        assert error.value.code == 1, "Blocking findings must return status one."
        assert capsys.readouterr().out == snapshot, (
            "Blocking report must remain actionable and deterministic."
        )

    def test_check_reports_stale_entries(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        snapshot: SnapshotAssertion,
    ) -> None:
        """Allow entries covering nothing are reported for removal."""
        monkeypatch.chdir(tmp_path)
        entry = allowlist.AllowEntry(
            keys=("python/stilyagi/gone.py",), reason="resolved"
        )
        monkeypatch.setattr(gate, "load_allowlist", lambda _path: (entry,))
        monkeypatch.setattr(gate, "detect_findings", lambda: [])
        gate.check()
        assert capsys.readouterr().out == snapshot, (
            "Stale entries must be reported alongside a passing gate."
        )

    def test_stale_diagnostic_distinguishes_shrinking_from_fixing(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The stale message must not tell developers the duplication is gone.

        A family leaves the ranking when it falls below `top` or shrinks under
        `min-size`, which is not the same as being fixed. The gate cannot tell
        the two apart, so the diagnostic has to say so rather than asserting
        the duplication was resolved.
        """
        monkeypatch.chdir(tmp_path)
        entry = allowlist.AllowEntry(keys=("python/stilyagi/gone.py",), reason="r")
        monkeypatch.setattr(gate, "load_allowlist", lambda _path: (entry,))
        monkeypatch.setattr(gate, "detect_findings", lambda: [])
        gate.check()
        message = capsys.readouterr().out
        for phrase in ("fell below", "min-size", "not because it was fixed"):
            assert phrase in message, (
                f"The stale diagnostic must name {phrase!r} so removal is not "
                "read as proof the code was deduplicated."
            )

    def test_check_reports_detector_schema_errors(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Malformed detector reports exit cleanly instead of showing a traceback."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(gate, "load_allowlist", lambda _path: ())

        def raise_schema_error() -> list[detector.Finding]:
            """Fail the way a schema violation inside the detector does."""
            msg = "nose report families must be an array"
            raise TypeError(msg)

        monkeypatch.setattr(gate, "detect_findings", raise_schema_error)
        with pytest.raises(SystemExit) as error:
            gate.check()

        assert error.value.code == 2, "Malformed detector reports must return two."
        assert capsys.readouterr().err == (
            "configuration error: nose report families must be an array\n"
        ), "Schema errors must use the configuration diagnostic."
        assert Path.cwd() == tmp_path, (
            "The check command must not change its caller's working directory."
        )

    def test_check_reports_a_version_mismatch(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """An unpinned detector fails the gate with a remediation message."""
        workspace = tmp_path
        stub = write_stub_nose(workspace, version="nose 0.19.0")
        monkeypatch.setenv("NOSE_BIN", str(stub))
        monkeypatch.chdir(workspace)
        monkeypatch.setattr(gate, "load_allowlist", lambda _path: ())
        with pytest.raises(SystemExit) as error:
            gate.check()
        assert error.value.code == 2, "A version mismatch must return two."
        assert "make install-nose" in capsys.readouterr().err, (
            "The mismatch diagnostic must name the install remediation."
        )

    def test_allow_reports_malformed_existing_entries(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Malformed existing allows exit cleanly instead of showing a traceback."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            '[[tool.duplication_gate.allow]]\nunit = "python/stilyagi/a.py"\n',
            encoding="utf-8",
        )
        monkeypatch.setattr(gate, "PYPROJECT", pyproject)

        with pytest.raises(SystemExit) as error:
            gate.allow(first="python/stilyagi/b.py", reason="reviewed exception")

        assert error.value.code == 2, "Malformed existing allows must return two."
        assert capsys.readouterr().err == (
            "configuration error: duplication_gate.allow[0] "
            "requires a non-empty reason\n"
        ), "Malformed allows must use the configuration diagnostic."

    def test_allow_reports_malformed_parent_table(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A scalar where a parent table belongs exits cleanly, not with a trace."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('tool = "scalar"\n', encoding="utf-8")
        monkeypatch.setattr(gate, "PYPROJECT", pyproject)

        with pytest.raises(SystemExit) as error:
            gate.allow(first="python/stilyagi/a.py", reason="reviewed exception")

        assert error.value.code == 2, "Malformed parent tables must return two."
        assert capsys.readouterr().err == (
            "configuration error: [tool] must be a table\n"
        ), "A malformed parent table must use the configuration diagnostic."

    def test_allow_reports_write_failures(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A filesystem failure while recording an allow exits cleanly."""
        write_error = OSError("read-only filesystem")

        def fail_write(*_args: object, **_kwargs: object) -> None:
            """Fail the way an unwritable manifest does."""
            raise write_error

        monkeypatch.setattr(gate, "append_allow_entry", fail_write)

        with pytest.raises(SystemExit) as exit_error:
            gate.allow(first="python/stilyagi/a.py", reason="reviewed exception")

        assert exit_error.value.code == 2, "Write failures must return two."
        assert capsys.readouterr().err == (
            "configuration error: read-only filesystem\n"
        ), "Write failures must use the configuration diagnostic."

    def test_allow_rejects_malformed_keys(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """An absolute key is refused before anything is written."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text("[project]\nname = 'x'\n", encoding="utf-8")
        monkeypatch.setattr(gate, "PYPROJECT", pyproject)

        with pytest.raises(SystemExit) as error:
            gate.allow(first="/python/stilyagi/a.py", reason="reviewed exception")

        assert error.value.code == 2, "Malformed keys must return two."
        assert "repository-relative" in capsys.readouterr().err, (
            "The diagnostic must explain the key requirement."
        )
        assert "duplication_gate" not in pyproject.read_text(encoding="utf-8"), (
            "A rejected key must not be recorded."
        )

    def test_allow_rejects_a_catch_all_key(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A catch-all key is refused before anything is written."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text("[project]\nname = 'x'\n", encoding="utf-8")
        monkeypatch.setattr(gate, "PYPROJECT", pyproject)

        with pytest.raises(SystemExit) as error:
            gate.allow(first="**/*", reason="reviewed exception")

        assert error.value.code == 2, "Catch-all keys must return two."
        assert "catch-all" in capsys.readouterr().err, (
            "The diagnostic must explain why a catch-all key is refused."
        )
        assert "duplication_gate" not in pyproject.read_text(encoding="utf-8"), (
            "A rejected catch-all key must not be recorded."
        )

    @pytest.mark.parametrize(
        ("second", "expected_keys"),
        [
            pytest.param(None, ("python/stilyagi/a.py",), id="unit"),
            pytest.param(
                ["python/stilyagi/b.py::beta"],
                ("python/stilyagi/a.py", "python/stilyagi/b.py::beta"),
                id="members",
            ),
        ],
    )
    def test_allow_cli_round_trips_unit_and_members(
        self,
        tmp_path: Path,
        second: list[str] | None,
        expected_keys: tuple[str, ...],
    ) -> None:
        """The real allow CLI records both supported exception forms."""
        _workspace, script = copied_gate_workspace(tmp_path)
        arguments = ["allow", "--first", "python/stilyagi/a.py"]
        for key in second or ():
            arguments.extend(("--second", key))
        arguments.extend(("--reason", "reviewed exception"))

        result = run_gate_command(script, *arguments)
        assert result.returncode == 0, result.stderr
        entries = allowlist.load_allowlist(script.parent.parent / "pyproject.toml")
        assert entries[0].keys == expected_keys, "CLI must retain its requested keys."
        assert entries[0].reason == "reviewed exception", (
            "CLI must retain the supplied reason."
        )

    def test_check_cli_passes_with_a_stub_detector(self, tmp_path: Path) -> None:
        """The gate exits zero through its real CLI when every family is allowed."""
        workspace, script = copied_gate_workspace(tmp_path)
        stub = write_stub_nose(tmp_path)
        (workspace / "pyproject.toml").write_text(
            textwrap.dedent(
                """\
                [tool.nose]
                version = "0.20.0"
                roots = ["python/stilyagi"]
                mode = "syntax"
                min-size = 24

                [[tool.duplication_gate.allow]]
                members = ["python/stilyagi/a.py", "python/stilyagi/b.py"]
                reason = "parallel wire contracts"
                """
            ),
            encoding="utf-8",
        )
        result = run_gate_command(
            script,
            "check",
            environment=gate_environment(NOSE_BIN=str(stub)),
        )
        assert result.returncode == 0, result.stderr
        assert "duplication gate passed" in result.stdout, (
            "An allowed family must leave the gate passing."
        )
