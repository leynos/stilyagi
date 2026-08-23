"""Failure-mode coverage for the `stilyagi check` command."""

import pathlib
import typing as typ

import pytest
from stilyagi import cli, config, discovery, engine, model

from tests.support.assertions import assert_with_context
from tests.support.malformed_corpus import materialize_malformed_corpus

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    type _FailureSetup = cabc.Callable[
        [pathlib.Path, pytest.MonkeyPatch],
        tuple[pathlib.Path, tuple[str, ...]],
    ]


def _run_failing_check(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
    target: pathlib.Path,
    *,
    unreadable_files: int,
) -> str:
    """Run one failing check against a stubbed target and return stderr."""
    _stub_discovery(monkeypatch, target)

    with caplog.at_level("WARNING"):
        exit_code = cli.run_check(cli.CheckOptions(targets=(target.name,)))
    captured = capsys.readouterr()

    assert exit_code == 2, "expected exit_code == 2"
    # A hard file error still renders the (empty) accumulated diagnostics before
    # the exit-2 signal, rather than suppressing stdout entirely.
    assert_with_context(
        captured.out
        == (
            "checked 1 files "
            f"(0 skipped, {unreadable_files} unreadable); 0 errors, 0 warnings\n"
        ),
        "expected captured.out to report the file-read outcome",
    )
    return "\n".join(record.getMessage() for record in caplog.records)


def _patch_read_text_failure(
    monkeypatch: pytest.MonkeyPatch,
    target: pathlib.Path,
    error_factory: cabc.Callable[[], Exception],
) -> None:
    """Make reads of the target file raise the supplied error."""
    original_read_text = pathlib.Path.read_text

    def read_text(path: pathlib.Path, *args: object, **kwargs: object) -> str:
        """Raise the injected failure for the target file only."""
        if path == target:
            raise error_factory()
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "read_text", read_text)


def _read_failure_fragments(
    target: pathlib.Path,
    detail: str,
) -> tuple[str, ...]:
    """Return the stderr fragments expected for one failed file read."""
    return ("stilyagi check: failed to read ", target.name, detail)


def _setup_unreadable_utf8(
    tmp_path: pathlib.Path,
    _monkeypatch: pytest.MonkeyPatch,
) -> tuple[pathlib.Path, tuple[str, ...]]:
    """Arrange a Markdown file whose bytes are not valid UTF-8."""
    target = tmp_path / "broken.md"
    target.write_bytes(b"\xff")
    return target, _read_failure_fragments(target, "can't decode byte 0xff")


def _setup_permission_error(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[pathlib.Path, tuple[str, ...]]:
    """Arrange a Markdown file whose read raises a permission failure."""
    target = tmp_path / "restricted.md"
    target.write_text("# Restricted\n", encoding="utf-8")
    _patch_read_text_failure(
        monkeypatch,
        target,
        lambda: PermissionError("permission denied"),
    )
    expected = f"stilyagi check: failed to read {target.name}: permission denied"
    return target, (expected,)


def _setup_mid_run_disappearance(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[pathlib.Path, tuple[str, ...]]:
    """Arrange a Markdown file that vanishes between discovery and read."""
    target = tmp_path / "vanished.md"
    target.write_text("# Vanished\n", encoding="utf-8")

    def vanish() -> FileNotFoundError:
        """Remove the target before the read to emulate a race."""
        target.unlink()
        return FileNotFoundError("target disappeared during read")

    _patch_read_text_failure(monkeypatch, target, vanish)
    expected = (
        f"stilyagi check: failed to read {target.name}: target disappeared during read"
    )
    return target, (expected,)


def _setup_directory_read(
    tmp_path: pathlib.Path,
    _monkeypatch: pytest.MonkeyPatch,
) -> tuple[pathlib.Path, tuple[str, ...]]:
    """Arrange a directory masquerading as one discovered input."""
    target = tmp_path / "docs"
    target.mkdir()
    return target, _read_failure_fragments(target, "Is a directory")


def _setup_extractor_failure(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[pathlib.Path, tuple[str, ...]]:
    """Arrange a readable file whose extraction blows up in the bridge."""
    target = tmp_path / "notes.md"
    target.write_text("# Notes\n", encoding="utf-8")
    monkeypatch.setattr(
        engine,
        "extract_document",
        lambda _source, _syntax: _raise_bridge_extraction_error(),
    )
    expected = f"stilyagi check: failed to check {target.as_posix()}: bridge exploded"
    return target, (expected,)


@pytest.mark.parametrize(
    "setup_failure",
    [
        _setup_unreadable_utf8,
        _setup_permission_error,
        _setup_mid_run_disappearance,
        _setup_directory_read,
        _setup_extractor_failure,
    ],
    ids=[
        "unreadable-utf8",
        "permission-error",
        "mid-run-disappearance",
        "directory-read",
        "extractor-failure",
    ],
)
def test_cli_run_check_maps_file_failures_to_exit_two(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
    setup_failure: _FailureSetup,
) -> None:
    """Reject each documented file failure with exit code 2 and stderr."""
    target, expected_fragments = setup_failure(tmp_path, monkeypatch)

    stderr = _run_failing_check(
        monkeypatch,
        capsys,
        caplog,
        target,
        unreadable_files=int(setup_failure is not _setup_extractor_failure),
    )

    for fragment in expected_fragments:
        assert fragment in stderr, f"expected {fragment!r} in stderr"


def test_cli_main_recovers_from_real_malformed_markdown(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Accept every malformed Markdown fixture without emitting diagnostics."""
    target_root = tmp_path / "docs"
    expected_names = materialize_malformed_corpus(target_root)
    monkeypatch.chdir(tmp_path)

    # Assert the whole malformed corpus reaches discovery; otherwise a fixture
    # that is skipped would let this regression pass vacuously.
    discovered = discovery.discover_files([target_root], config.StilyagiConfig())
    discovered_names = tuple(sorted(item.resolved_path.name for item in discovered))
    assert_with_context(
        discovered_names == expected_names,
        "expected discovered_names == expected_names",
    )

    exit_code = cli.main(["check", "."])
    captured = capsys.readouterr()

    assert exit_code == 0, "expected exit_code == 0"
    assert not captured.err, "expected not captured.err"
    assert_with_context(
        captured.out
        == (
            "checked "
            f"{len(expected_names)} files (0 skipped, 0 unreadable); "
            "0 errors, 0 warnings\n"
        ),
        "expected captured.out to report every recovered fixture",
    )


def _synthetic_ir_extract(source: str, _syntax: object) -> model.Document:
    """Return a document that carries one IR error for the 'warn' source only."""
    errors = (
        [{"code": "IR900", "message": "synthetic", "span": {"byte_start": 0}}]
        if "WARN" in source
        else []
    )
    return model.Document(
        syntax=model.Syntax.MARKDOWN,
        ir={"line_index": [0, 8], "errors": errors},
    )


def test_cli_main_checks_every_file_and_renders_earlier_diagnostics_on_failure(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A mid-batch failure must not stop earlier diagnostics or later files."""
    root = tmp_path / "docs"
    root.mkdir()
    (root / "a-clean.md").write_text("# Clean\n", encoding="utf-8")
    (root / "b-warn.md").write_text("WARN\n", encoding="utf-8")
    # Sorted discovery order puts the unreadable file last, so the earlier warn
    # diagnostic is accumulated before the failure is encountered.
    (root / "c-broken.md").write_bytes(b"\xff")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(engine, "extract_document", _synthetic_ir_extract)

    with caplog.at_level("WARNING"):
        exit_code = cli.main(["check", "."])
    captured = capsys.readouterr()

    # The unreadable file forces exit 2, yet the earlier file's diagnostic is
    # still rendered and the clean file did not short-circuit the batch.
    assert exit_code == 2, "expected exit_code == 2"
    assert_with_context(
        "docs/b-warn.md:1:1: warning IR900 synthetic" in captured.out,
        "expected 'docs/b-warn.md:1:1: warning IR900 synthetic'...",
    )
    assert_with_context(
        "checked 3 files (0 skipped, 1 unreadable); 0 errors, 1 warnings"
        in captured.out,
        "expected the mixed run summary in captured.out",
    )
    log_messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "failed to read" in log_messages, "expected 'failed to read' in logs"
    assert "c-broken.md" in log_messages, "expected 'c-broken.md' in logs"


def _stub_discovery(
    monkeypatch: pytest.MonkeyPatch,
    target: pathlib.Path,
) -> None:
    """Return one discovered file so the file-read branch stays focused."""
    discovered_file = cli.CheckInput(
        reported_path=target.name,
        resolved_path=target,
        syntax=model.Syntax.MARKDOWN,
    )
    monkeypatch.setattr(
        cli,
        "_discover_targets",
        lambda _options, _resolver: ((discovered_file,), 0),
    )


def _raise_bridge_extraction_error() -> typ.NoReturn:
    """Raise the deterministic extractor failure used by the regression test."""
    message = "bridge exploded"
    raise engine.BridgeExtractionError(message)
