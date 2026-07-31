"""Unit tests for the `stilyagi check` command."""

import json
import logging
import typing as typ

from stilyagi import cli, diagnostics, engine
from syrupy.extensions.json import JSONSnapshotExtension

if typ.TYPE_CHECKING:
    import pathlib

    import pytest
    from syrupy.assertion import SnapshotAssertion


def test_main_returns_zero_for_a_clean_tree(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A clean Markdown tree should exit successfully with text output."""
    _write_markdown(tmp_path / "docs" / "notes.md", "Notes")
    monkeypatch.chdir(tmp_path)

    assert cli.main(["check", "."]) == 0, "expected cli.main(['check', '.']) == 0"
    captured = capsys.readouterr()
    assert captured.out == "0 diagnostics found\n", (
        "expected captured.out == '0 diagnostics found\\n'"
    )
    assert not captured.err, "expected not captured.err"


def test_main_renders_json_for_synthetic_diagnostics(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    snapshot: SnapshotAssertion,
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

    assert cli.compute_exit_code([], had_error=True) == 2, (
        "expected cli.compute_exit_code([], had_error=True) == 2"
    )
    assert cli.compute_exit_code([synthetic_diagnostic]) == 1, (
        "expected cli.compute_exit_code([synthetic_diagnostic..."
    )
    assert cli.compute_exit_code([]) == 0, "expected cli.compute_exit_code([]) == 0"
    assert cli.main(["check", ".", "--output-format", "json"]) == 1, (
        "expected cli.main(['check', '.', '--output-format', ..."
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload == snapshot(extension_class=JSONSnapshotExtension), (
        "expected the rendered diagnostic payload to match it..."
    )


def test_main_returns_two_for_invalid_configuration(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Malformed discovered config should fail with the documented exit code."""
    (tmp_path / "stilyagi.toml").write_text("[lint\n", encoding="utf-8")
    _write_markdown(tmp_path / "docs" / "notes.md", "Notes")
    monkeypatch.chdir(tmp_path)

    assert cli.main(["check", "."]) == 2, "expected cli.main(['check', '.']) == 2"
    captured = capsys.readouterr()
    assert "stilyagi check:" in captured.err, (
        "expected 'stilyagi check:' in captured.err"
    )
    assert "toml" in captured.err.lower(), "expected 'toml' in captured.err.lower()"
    assert not captured.out, "expected not captured.out"


def test_check_pipeline_emits_stage_boundary_logs(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    snapshot: SnapshotAssertion,
) -> None:
    """The clean check path logs discovery, config resolution, and rendering."""
    _write_markdown(tmp_path / "docs" / "notes.md", "Notes")
    monkeypatch.chdir(tmp_path)

    with caplog.at_level(logging.DEBUG):
        assert cli.main(["check", "."]) == 0, "expected cli.main(['check', '.']) == 0"

    messages = tuple(record.getMessage() for record in caplog.records)
    observed_stages = {
        "discovery": any("target discovery started" in message for message in messages),
        "config": any("resolving config for" in message for message in messages),
        "rendering": any("rendering" in message for message in messages),
    }
    assert observed_stages == snapshot(extension_class=JSONSnapshotExtension), (
        "expected every check-pipeline stage to be represente..."
    )


def test_check_logs_extraction_failure_alongside_stderr(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failed extraction is logged in addition to the user-facing stderr."""
    _write_markdown(tmp_path / "docs" / "notes.md", "Notes")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(engine, "extract_document", _raise_bridge_error)

    with caplog.at_level(logging.WARNING):
        assert cli.main(["check", "."]) == 2, "expected cli.main(['check', '.']) == 2"

    warnings = [
        record.getMessage()
        for record in caplog.records
        if record.levelno >= logging.WARNING
    ]
    assert any("failed to check" in message for message in warnings), (
        "expected any(('failed to check' in message for messa..."
    )
    assert "stilyagi check: failed to check" in capsys.readouterr().err, (
        "expected 'stilyagi check: failed to check' in capsys..."
    )


def _raise_bridge_error(_source: str, _syntax: object) -> typ.NoReturn:
    """Raise the deterministic extractor failure used by the logging test."""
    message = "bridge exploded"
    raise RuntimeError(message)


def _write_markdown(path: pathlib.Path, title: str) -> None:
    """Write one tiny Markdown file for the unit tree."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {title}\n", encoding="utf-8")
