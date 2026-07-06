"""Unit tests for the `stilyagi check` command."""

from __future__ import annotations

import json
import typing as typ

from stilyagi import cli, diagnostics

if typ.TYPE_CHECKING:
    import pathlib

    import pytest


def test_main_returns_zero_for_a_clean_tree(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A clean Markdown tree should exit successfully with text output."""
    _write_markdown(tmp_path / "docs" / "notes.md", "Notes")
    monkeypatch.chdir(tmp_path)

    assert cli.main(["check", "."]) == 0
    captured = capsys.readouterr()
    assert captured.out == "0 diagnostics found\n"
    assert not captured.err


def test_main_renders_json_for_synthetic_diagnostics(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A synthetic rule diagnostic should surface through the JSON renderer."""
    _write_markdown(tmp_path / "docs" / "notes.md", "Notes")
    monkeypatch.chdir(tmp_path)

    synthetic_diagnostic = diagnostics.Diagnostic(
        path="docs/notes.md",
        code="STY999",
        message="Synthetic diagnostic",
        severity=diagnostics.Severity.WARNING,
        line=1,
        column=1,
    )
    monkeypatch.setattr(
        "stilyagi.rules.registry.run_rules",
        lambda _document, _config: [synthetic_diagnostic],
    )

    assert cli.compute_exit_code([], had_error=True) == 2
    assert cli.compute_exit_code([synthetic_diagnostic]) == 1
    assert cli.compute_exit_code([]) == 0
    assert cli.main(["check", ".", "--output-format", "json"]) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "diagnostics": [
            {
                "path": "docs/notes.md",
                "code": "STY999",
                "message": "Synthetic diagnostic",
                "severity": "warning",
                "location": {"line": 1, "column": 1},
                "fix_applicable": False,
            }
        ],
    }


def test_main_returns_two_for_invalid_configuration(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Malformed discovered config should fail with the documented exit code."""
    (tmp_path / "stilyagi.toml").write_text("[lint\n", encoding="utf-8")
    _write_markdown(tmp_path / "docs" / "notes.md", "Notes")
    monkeypatch.chdir(tmp_path)

    assert cli.main(["check", "."]) == 2
    captured = capsys.readouterr()
    assert "stilyagi check:" in captured.err
    assert "toml" in captured.err.lower()
    assert not captured.out


def _write_markdown(path: pathlib.Path, title: str) -> None:
    """Write one tiny Markdown file for the unit tree."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {title}\n", encoding="utf-8")
