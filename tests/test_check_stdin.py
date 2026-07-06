"""Stdin coverage for the `stilyagi check` command."""

from __future__ import annotations

import io
import os
import pathlib
import subprocess  # noqa: S404 - tests invoke a trusted local interpreter.
import sys
import typing as typ

from stilyagi import cli, diagnostics

if typ.TYPE_CHECKING:
    import pytest


def test_cli_main_reads_stdin_and_attributes_diagnostic_to_filename(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Read Markdown from stdin and keep the rendered path stable."""
    monkeypatch.setattr(sys, "stdin", io.StringIO("# Notes\n"))
    monkeypatch.setattr(
        "stilyagi.rules.registry.run_rules",
        lambda document, config: [
            diagnostics.Diagnostic(
                path="README.md",
                code="IR000",
                message="Synthetic IR error",
            ),
        ],
    )

    assert cli.main(["check", "-", "--stdin-filename", "README.md"]) == 1
    captured = capsys.readouterr()
    assert (
        captured.out == "README.md:1:1: IR000 Synthetic IR error\n1 diagnostic found\n"
    )
    assert not captured.err


def test_python_module_entrypoint_reads_clean_stdin_and_exits_zero(
    tmp_path: pathlib.Path,
) -> None:
    """Accept a clean stdin document through the console entry point."""
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "stilyagi",
            "check",
            "-",
            "--stdin-filename",
            "README.md",
        ],
        cwd=tmp_path,
        env=_python_module_environment(),
        input="# Notes\n",
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode == 0
    assert completed.stdout == "0 diagnostics found\n"
    assert not completed.stderr


def test_python_module_entrypoint_rejects_stdin_mixed_with_path(
    tmp_path: pathlib.Path,
) -> None:
    """Reject the usage error that combines stdin with a file target."""
    (tmp_path / "notes.md").write_text("# Notes\n", encoding="utf-8")
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "stilyagi",
            "check",
            "-",
            "notes.md",
        ],
        cwd=tmp_path,
        env=_python_module_environment(),
        input="# Notes\n",
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode == 2
    assert "stdin target cannot be combined with file targets" in completed.stderr


def _python_module_environment() -> dict[str, str]:
    """Return an environment that can import the local `stilyagi` package."""
    python_path = pathlib.Path(__file__).resolve().parents[1] / "python"
    env = dict(os.environ)
    env["PYTHONPATH"] = (
        f"{python_path}{os.pathsep}{env['PYTHONPATH']}"
        if env.get("PYTHONPATH")
        else str(python_path)
    )
    return env
