"""Unit tests for the `stilyagi check` command."""

import io
import json
import logging
import pathlib
import typing as typ

import pytest
from stilyagi import cli, diagnostics, engine
from syrupy.extensions.json import JSONSnapshotExtension

from tests.support.assertions import assert_with_context

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    import os

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


def test_main_summarises_an_empty_directory(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An empty directory should be a successful check with a zero summary."""
    target = tmp_path / "empty"
    target.mkdir()
    monkeypatch.chdir(tmp_path)

    assert cli.main(["check", target.name]) == 0, "expected an empty check to exit zero"
    captured = capsys.readouterr()
    assert captured.out == (
        "checked 0 files (0 skipped, 0 unreadable); 0 errors, 0 warnings\n"
    ), "expected the exact zero-file run summary"
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
        lambda _request: [synthetic_diagnostic],
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
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Malformed discovered config should fail with the documented exit code."""
    (tmp_path / "stilyagi.toml").write_text("[lint\n", encoding="utf-8")
    _write_markdown(tmp_path / "docs" / "notes.md", "Notes")
    monkeypatch.chdir(tmp_path)

    assert cli.main(["check", "."]) == 2, "expected cli.main(['check', '.']) == 2"
    captured = capsys.readouterr()
    messages = (captured.err,)
    assert_with_context(
        any(message.startswith("stilyagi check:") for message in messages),
        "expected a user-facing check failure log message",
    )
    assert any("toml" in message.lower() for message in messages), (
        "expected a TOML failure log message"
    )


def test_main_rejects_fix_combined_with_diff(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A mutating flag combined with a non-mutating one is a usage error.

    D-06 rejects the pair outright rather than letting one silently win,
    because silent precedence cannot be withdrawn once scripts depend on it.
    """
    target = tmp_path / "notes.md"
    original = "# Notes\n"
    target.write_text(original, encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    exit_code = cli.main(["check", ".", "--fix", "--diff"])

    assert exit_code == 2, "expected the conflicting pair to exit two"
    captured = capsys.readouterr()
    assert_with_context(
        "cannot be combined" in captured.err,
        "expected the usage error on standard error",
    )
    assert not captured.out, "expected no report on standard output"
    assert_with_context(
        target.read_text(encoding="utf-8") == original,
        "expected the rejected pair to leave the source untouched",
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
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A failed extraction is emitted once as a user-facing log message."""
    _write_markdown(tmp_path / "docs" / "notes.md", "Notes")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(engine, "extract_document", _raise_bridge_error)

    root_logger = logging.getLogger()
    previous_level = root_logger.level
    root_output = io.StringIO()
    root_handler = logging.StreamHandler(root_output)
    root_logger.addHandler(root_handler)
    try:
        assert cli.main(["check", "."]) == 2, "expected cli.main(['check', '.']) == 2"
    finally:
        root_logger.removeHandler(root_handler)
        root_logger.setLevel(previous_level)
    captured = capsys.readouterr()
    warnings = captured.err.splitlines()
    assert_with_context(
        any("failed to check" in message for message in warnings),
        "expected any(('failed to check' in message for messa...",
    )
    assert len(warnings) == 1, "expected exactly one extraction failure warning"
    assert not root_output.getvalue(), (
        "expected the root handler not to duplicate warnings"
    )
    assert captured.out.startswith("checked 1 files "), (
        "expected the normal run summary to remain on stdout"
    )


def test_main_skips_a_symlinked_directory_target(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A symlinked directory target must be visible as one skipped input."""
    source_directory = tmp_path / "source"
    _write_markdown(source_directory / "notes.md", "Notes")
    target = tmp_path / "linked-source"
    target.symlink_to(source_directory, target_is_directory=True)
    monkeypatch.chdir(tmp_path)

    exit_code = cli.main(["check", target.name])
    captured = capsys.readouterr()

    assert exit_code == 0, "expected a skipped symlink target to exit zero"
    assert captured.out == (
        "checked 0 files (1 skipped, 0 unreadable); 0 errors, 0 warnings\n"
    ), "expected the symlink target summary"
    assert captured.err.count("skipping symlinked directory target") == 1, (
        "expected one warning for the skipped symlinked directory target"
    )


def test_main_reports_directory_walk_failure_after_checking_partial_results(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Retain partial discoveries and report traversal failure as exit two."""
    _write_markdown(tmp_path / "notes.md", "Notes")
    monkeypatch.chdir(tmp_path)

    def walk_with_failure(
        path: pathlib.Path,
        *,
        follow_symlinks: bool = False,
        on_error: cabc.Callable[[OSError], None] | None = None,
    ) -> cabc.Iterator[tuple[pathlib.Path, list[str], list[str]]]:
        """Yield one source and report a later traversal failure."""
        assert not follow_symlinks, "expected symlink traversal to remain disabled"
        yield path, [], ["notes.md"]
        assert on_error is not None, "expected a pathlib walk error callback"
        on_error(PermissionError(13, "permission denied", path.as_posix()))

    monkeypatch.setattr(pathlib.Path, "walk", walk_with_failure)

    exit_code = cli.main(["check", "."])
    captured = capsys.readouterr()

    assert exit_code == 2, "expected exit_code == 2 after an incomplete walk"
    assert captured.out == (
        "checked 1 files (0 skipped, 0 unreadable); 0 errors, 0 warnings\n"
    ), "expected the successfully discovered input to be checked"
    assert captured.err.count("failed to discover") == 1, (
        "expected one user-facing traversal failure warning"
    )


def test_main_reports_explicit_target_stat_failure_as_operational(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An explicit target stat error is reported and selects exit status two."""
    target = tmp_path / "restricted.md"
    _write_markdown(target, "Restricted")
    original_lstat = pathlib.Path.lstat

    def fail_target_lstat(path: pathlib.Path) -> os.stat_result:
        """Raise a permission error only for the requested target."""
        if path == target:
            raise PermissionError(13, "permission denied", target.as_posix())
        return original_lstat(path)

    monkeypatch.setattr(pathlib.Path, "lstat", fail_target_lstat)

    exit_code = cli.main(["check", target.as_posix()])
    captured = capsys.readouterr()

    assert exit_code == 2, "a target stat failure is an operational error"
    assert captured.out == (
        "checked 0 files (0 skipped, 0 unreadable); 0 errors, 0 warnings\n"
    ), "the command emits the empty-run summary"
    assert "failed to discover" in captured.err, "the command reports the failure"
    assert target.as_posix() in captured.err, "the warning identifies the target"


def test_main_reports_target_expansion_failure_as_operational(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An unresolved home directory is reported instead of escaping the CLI."""
    target = pathlib.Path("~/notes.md")
    original_expanduser = pathlib.Path.expanduser

    def fail_target_expansion(path: pathlib.Path) -> pathlib.Path:
        """Simulate a home lookup failure for the command-line target."""
        if path == target:
            raise RuntimeError
        return original_expanduser(path)

    monkeypatch.setattr(pathlib.Path, "expanduser", fail_target_expansion)

    exit_code = cli.main(["check", target.as_posix()])
    captured = capsys.readouterr()

    assert exit_code == 2, "target expansion failure is an operational error"
    assert captured.out == (
        "checked 0 files (0 skipped, 0 unreadable); 0 errors, 0 warnings\n"
    ), "the command emits the empty-run summary"
    assert "failed to discover" in captured.err, "the command reports the failure"
    assert target.as_posix() in captured.err, "the warning identifies the raw target"


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
