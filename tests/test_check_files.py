"""Faithful-read and whole-batch coverage for the `stilyagi check` command.

Two contracts live here, and both are about a run that succeeds or that keeps
going. The first is that a source the read boundary accepts arrives at the
extractor byte-faithful: a byte-order mark is stripped, a CRLF line ending
survives, and a Python source with a legacy encoding cookie is decoded by the
encoding it declares rather than by the platform default. The second is that a
mid-batch failure is not a short circuit -- the files after the failure are
still checked, and the diagnostics found before it are still rendered.

The complementary contract, every way a discovered file can fail to become
source, is a parametrized table in `tests/test_check_read_failures.py`.

Run them with:

    make test

or, for this module alone:

    .venv/bin/python -m pytest tests/test_check_files.py
"""

import pathlib
import typing as typ

from stilyagi import cli, config, discovery, engine, model

from tests.support.assertions import assert_with_context
from tests.support.malformed_corpus import materialize_malformed_corpus

if typ.TYPE_CHECKING:
    import pytest


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


def test_cli_main_preserves_crlf_source_for_extraction(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Pass CRLF source to the extractor without newline translation."""
    source = (
        pathlib.Path("tests/fixtures/corpus/markdown/valid/")
        / "paragraph-soft-break-crlf.md.fixture"
    ).read_bytes()
    target = tmp_path / "notes.md"
    target.write_bytes(source)
    extracted_sources: list[str] = []

    def capture_source(text: str, _syntax: object) -> model.Document:
        """Record the source passed through the command-line pipeline."""
        extracted_sources.append(text)
        return model.Document(syntax=model.Syntax.MARKDOWN)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(engine, "extract_document", capture_source)

    assert cli.main(["check", target.name]) == 0, "expected a clean check"
    assert not capsys.readouterr().err, "expected no read error"
    assert_with_context(
        extracted_sources == [source.decode("utf-8")],
        "expected extraction to receive the original CRLF text",
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
