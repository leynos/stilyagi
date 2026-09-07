"""Unit tests for the `stilyagi check` command."""

import json
import logging
import typing as typ

import pytest
from stilyagi import cli, diagnostics, engine
from syrupy.extensions.json import JSONSnapshotExtension

from tests.support.assertions import assert_with_context

if typ.TYPE_CHECKING:
    import pathlib

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
    assert_with_context(
        captured.out
        == "checked 1 files (0 skipped, 0 unreadable); 0 errors, 0 warnings\n",
        "expected captured.out to carry the clean-run summary",
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

    assert_with_context(
        cli.compute_exit_code([], had_error=True) == 2,
        "expected cli.compute_exit_code([], had_error=True) == 2",
    )
    assert_with_context(
        cli.compute_exit_code([synthetic_diagnostic]) == 0,
        "expected cli.compute_exit_code([synthetic_diagnostic...",
    )
    assert cli.compute_exit_code([]) == 0, "expected cli.compute_exit_code([]) == 0"
    assert_with_context(
        cli.main(["check", ".", "--output-format", "json"]) == 0,
        "expected cli.main(['check', '.', '--output-format', ...",
    )

    payload = json.loads(capsys.readouterr().out)
    assert_with_context(
        payload["summary"]
        == {
            "checked_files": 1,
            "skipped_files": 0,
            "unreadable_files": 0,
            "errors": 0,
            "warnings": 1,
        },
        "expected payload['summary'] to distinguish warning-only runs",
    )
    assert_with_context(
        payload == snapshot(extension_class=JSONSnapshotExtension),
        "expected the rendered diagnostic payload to match it...",
    )


def test_main_returns_two_for_invalid_configuration(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Malformed discovered config should fail with the documented exit code."""
    (tmp_path / "stilyagi.toml").write_text("[lint\n", encoding="utf-8")
    _write_markdown(tmp_path / "docs" / "notes.md", "Notes")
    monkeypatch.chdir(tmp_path)

    with caplog.at_level(logging.WARNING):
        assert cli.main(["check", "."]) == 2, "expected cli.main(['check', '.']) == 2"
    messages = tuple(record.getMessage() for record in caplog.records)
    assert_with_context(
        any(message.startswith("stilyagi check:") for message in messages),
        "expected a user-facing check failure log message",
    )
    assert any("toml" in message.lower() for message in messages), (
        "expected a TOML failure log message"
    )


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
    assert_with_context(
        observed_stages == snapshot(extension_class=JSONSnapshotExtension),
        "expected every check-pipeline stage to be represente...",
    )


def test_check_logs_extraction_failure_alongside_stderr(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failed extraction is emitted once as a user-facing log message."""
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
    assert_with_context(
        any("failed to check" in message for message in warnings),
        "expected any(('failed to check' in message for messa...",
    )
    assert len(warnings) == 1, "expected exactly one extraction failure warning"


def test_main_skips_a_symlinked_directory_target(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A symlinked directory target must be visible as one skipped input."""
    source_directory = tmp_path / "source"
    _write_markdown(source_directory / "notes.md", "Notes")
    target = tmp_path / "linked-source"
    target.symlink_to(source_directory, target_is_directory=True)
    monkeypatch.chdir(tmp_path)

    with caplog.at_level(logging.WARNING):
        exit_code = cli.main(["check", target.name])

    assert exit_code == 0, "expected a skipped symlink target to exit zero"
    assert (
        capsys.readouterr().out
        == "checked 0 files (1 skipped, 0 unreadable); 0 errors, 0 warnings\n"
    ), "expected the symlink target summary"
    assert any(
        record.levelno == logging.WARNING
        and "skipping symlinked directory target" in record.getMessage()
        for record in caplog.records
    ), "expected a warning for the skipped symlinked directory target"


def test_check_reraises_unexpected_extraction_failure(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Unexpected adapter failures are logged with a traceback and re-raised."""
    _write_markdown(tmp_path / "docs" / "notes.md", "Notes")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(engine, "extract_document", _raise_adapter_error)

    with caplog.at_level(logging.ERROR), pytest.raises(TypeError, match="adapter"):
        cli.main(["check", "."])

    errors = [
        record
        for record in caplog.records
        if record.levelno >= logging.ERROR
        and "unexpected extraction failure" in record.getMessage()
    ]
    assert len(errors) == 1, "expected one unexpected extraction failure log"
    assert errors[0].exc_info is not None, "expected exception traceback details"


def _raise_bridge_error(_source: str, _syntax: object) -> typ.NoReturn:
    """Raise the deterministic extractor failure used by the logging test."""
    message = "bridge exploded"
    raise engine.BridgeExtractionError(message)


def _raise_adapter_error(_source: str, _syntax: object) -> typ.NoReturn:
    """Raise an unexpected adapter failure used by the propagation test."""
    message = "adapter exploded"
    raise TypeError(message)


def _write_markdown(path: pathlib.Path, title: str) -> None:
    """Write one tiny Markdown file for the unit tree."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {title}\n", encoding="utf-8")
