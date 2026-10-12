"""Stdin coverage for the `stilyagi check` command."""

import io
import json
import subprocess  # ruff: ignore[suspicious-subprocess-import] - tests invoke a trusted local interpreter.
import sys
import typing as typ

from stilyagi import cli, diagnostics

from tests.support.assertions import assert_with_context
from tests.support.subprocess_env import python_module_environment

if typ.TYPE_CHECKING:
    import pathlib

    import pytest


def test_cli_main_reads_stdin_and_attributes_diagnostic_to_filename(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Read Markdown from stdin and keep the rendered path stable."""
    monkeypatch.setattr(sys, "stdin", io.StringIO("# Notes\n"))
    monkeypatch.setattr(
        "stilyagi.rules.registry.run_rules",
        lambda _document, _config: [
            diagnostics.Diagnostic(
                path="README.md",
                code="IR000",
                message="Synthetic IR error",
            ),
        ],
    )

    assert_with_context(
        cli.main(["check", "-", "--stdin-filename", "README.md"]) == 1,
        "expected cli.main(['check', '-', '--stdin-filename',...",
    )
    captured = capsys.readouterr()
    assert_with_context(
        captured.out
        == (
            "README.md:1:1: error IR000 Synthetic IR error\n"
            "checked 1 files (0 skipped, 0 unreadable); 1 errors, 0 warnings\n"
        ),
        "expected captured.out == 'README.md:1:1: error IR000...",
    )
    assert not captured.err, "expected not captured.err"


def test_verbose_stdin_skip_records_its_fixed_reason(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Count an unsupported stdin suffix in the same bounded skip category."""
    monkeypatch.setattr(sys, "stdin", io.StringIO("source"))

    assert (
        cli.main(["check", "-", "--stdin-filename", "notes.txt", "--verbose"]) == 0
    ), "an unsupported stdin filename is skipped without failing the run"

    captured = capsys.readouterr()
    metric_line = next(
        line
        for line in captured.err.splitlines()
        if line.startswith("stilyagi check metrics: ")
    )
    metrics_payload = json.loads(metric_line.removeprefix("stilyagi check metrics: "))

    assert captured.out == (
        "checked 0 files (1 skipped, 0 unreadable); 0 errors, 0 warnings\n"
    ), "the run summary counts the unregistered stdin candidate"
    assert metrics_payload["stilyagi_check_skipped_candidates_total"] == {
        "symlinked_directory_target": 0,
        "unregistered_candidate": 1,
    }, "unsupported stdin filenames use the bounded unregistered reason"


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
        env=python_module_environment(),
        input="# Notes\n",
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode == 0, "expected completed.returncode == 0"
    assert_with_context(
        completed.stdout
        == "checked 1 files (0 skipped, 0 unreadable); 0 errors, 0 warnings\n",
        "expected completed.stdout to carry the stdin summary",
    )
    assert not completed.stderr, "expected not completed.stderr"


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
        env=python_module_environment(),
        input="# Notes\n",
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode == 2, "expected completed.returncode == 2"
    assert_with_context(
        "stdin target cannot be combined with file targets" in completed.stderr,
        "expected 'stdin target cannot be combined with file ...",
    )
