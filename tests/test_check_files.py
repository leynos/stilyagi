"""Failure-mode coverage for the `stilyagi check` command."""

import dataclasses as dc
import functools
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


@dc.dataclass(frozen=True, slots=True)
class _InjectedReadFailure:
    """Describe one read failure injected by a file-check test."""

    filename: str
    error_factory: cabc.Callable[[], Exception]
    detail: str


def _run_failing_check(
    harness: _FailingCheckHarness,
    target: pathlib.Path,
    *,
    unreadable_files: int,
) -> str:
    """Run one failing check and return warnings captured on stderr."""
    _stub_discovery(harness.monkeypatch, target)

    exit_code = cli.run_check(cli.CheckOptions(targets=(target.name,)))
    captured = harness.capsys.readouterr()

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
    return captured.err


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
    """Return the logged-warning fragments expected for one failed file read."""
    return ("stilyagi check: failed to read ", target.name, detail)


def _setup_injected_read_failure(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: _InjectedReadFailure,
) -> tuple[pathlib.Path, tuple[str, ...]]:
    """Arrange a Markdown file whose read raises the configured failure."""
    target = tmp_path / failure.filename
    target.write_text("# Read failure\n", encoding="utf-8")
    _patch_read_text_failure(monkeypatch, target, failure.error_factory)
    return target, _read_failure_fragments(target, failure.detail)


def _setup_unreadable_utf8(
    tmp_path: pathlib.Path,
    _monkeypatch: pytest.MonkeyPatch,
) -> tuple[pathlib.Path, tuple[str, ...]]:
    """Arrange a Markdown file whose bytes are not valid UTF-8."""
    target = tmp_path / "broken.md"
    target.write_bytes(b"\xff")
    return target, _read_failure_fragments(target, "can't decode byte 0xff")


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
    expected = f"stilyagi check: failed to check {target.name}: bridge exploded"
    return target, (expected,)


@pytest.mark.parametrize(
    ("setup_failure", "unreadable_files"),
    [
        pytest.param(_setup_unreadable_utf8, 1, id="unreadable-utf8"),
        pytest.param(
            functools.partial(
                _setup_injected_read_failure,
                failure=_InjectedReadFailure(
                    filename="restricted.md",
                    error_factory=functools.partial(
                        PermissionError, "permission denied"
                    ),
                    detail="permission denied",
                ),
            ),
            1,
            id="permission-error",
        ),
        pytest.param(_setup_mid_run_disappearance, 1, id="mid-run-disappearance"),
        pytest.param(_setup_directory_read, 1, id="directory-read"),
        pytest.param(_setup_extractor_failure, 0, id="extractor-failure"),
        pytest.param(
            functools.partial(
                _setup_injected_read_failure,
                failure=_InjectedReadFailure(
                    filename="huge.md",
                    error_factory=functools.partial(MemoryError, "read too large"),
                    detail="read too large",
                ),
            ),
            1,
            id="memory-error",
        ),
    ],
)
def test_cli_run_check_maps_file_failures_to_exit_two(
    harness: _FailingCheckHarness,
    setup_failure: _FailureSetup,
    unreadable_files: int,
) -> None:
    """Reject each documented file failure with exit code 2 and a logged warning."""
    target, expected_fragments = setup_failure(harness.tmp_path, harness.monkeypatch)

    log_messages = _run_failing_check(
        harness,
        target,
        unreadable_files=unreadable_files,
    )

    for fragment in expected_fragments:
        assert fragment in log_messages, f"expected {fragment!r} in the logged warnings"


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
    log_messages = captured.err
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
        lambda _options, _resolver: cli.DiscoveryInputs(
            (discovered_file,),
            0,
        ),
    )


def _raise_bridge_extraction_error() -> typ.NoReturn:
    """Raise the deterministic extractor failure used by the regression test."""
    message = "bridge exploded"
    raise engine.BridgeExtractionError(message)


@dc.dataclass(frozen=True, slots=True)
class _FailingCheckHarness:
    """Pytest collaborators required to run one failing check."""

    tmp_path: pathlib.Path
    monkeypatch: pytest.MonkeyPatch
    capsys: pytest.CaptureFixture[str]


@pytest.fixture(name="harness")
def _failing_check_harness(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> _FailingCheckHarness:
    """Provide the collaborators used by the failing-check test harness."""
    return _FailingCheckHarness(tmp_path, monkeypatch, capsys)


def test_cli_main_reads_bom_prefixed_source_and_reports_success(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Strip a UTF-8 byte-order mark instead of reporting a read failure."""
    root = tmp_path / "docs"
    root.mkdir()
    (root / "bom.md").write_bytes(b"\xef\xbb\xbf# Bom\n")
    monkeypatch.chdir(tmp_path)

    exit_code = cli.main(["check", "."])
    captured = capsys.readouterr()

    assert exit_code == 0, "expected exit_code == 0"
    assert not captured.err, "expected not captured.err"
    assert_with_context(
        captured.out
        == "checked 1 files (0 skipped, 0 unreadable); 0 errors, 0 warnings\n",
        "expected captured.out to report the BOM-prefixed file as checked",
    )


def test_cli_main_honours_python_source_encoding_cookie(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Decode a discovered Python source using its declared legacy encoding."""
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "legacy.py").write_bytes(
        '# coding: latin-1\n"""caf\xe9"""\n'.encode("latin-1")
    )
    monkeypatch.chdir(tmp_path)

    exit_code = cli.main(["check", "."])
    captured = capsys.readouterr()

    assert exit_code == 0, "expected exit_code == 0"
    assert not captured.err, "expected not captured.err"
    assert_with_context(
        captured.out
        == "checked 1 files (0 skipped, 0 unreadable); 0 errors, 0 warnings\n",
        "expected the Python source with an encoding cookie to be checked",
    )
