"""Operational handling of source encoding-detection failures."""

import json
import typing as typ

import pytest
from stilyagi import cli, engine, model

if typ.TYPE_CHECKING:
    import pathlib


@pytest.mark.parametrize(
    "invalid_source",
    [
        pytest.param(
            b'# coding: x-stilyagi-invalid-codec\n"""Broken encoding."""\n',
            id="unknown-codec",
        ),
        pytest.param(
            b'\xef\xbb\xbf# coding: latin-1\n"""Broken encoding."""\n',
            id="utf8-bom-cookie-conflict",
        ),
        pytest.param(
            b'# coding: utf-8\xff\n"""Broken encoding."""\n',
            id="invalid-header-bytes",
        ),
    ],
)
def test_cli_continues_after_python_encoding_detection_failure(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    invalid_source: bytes,
) -> None:
    """Treat encoding-detection SyntaxError as a read failure and continue."""
    root = tmp_path / "src"
    root.mkdir()
    (root / "a-broken.py").write_bytes(invalid_source)
    (root / "z-valid.rs").write_text("//! Rust docs.\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    extracted_syntaxes: list[model.Syntax] = []
    original_extract = engine.extract_document

    def track_extraction(source: str, syntax: model.Syntax) -> model.Document:
        """Record each extraction while retaining the real implementation."""
        extracted_syntaxes.append(syntax)
        return original_extract(source, syntax)

    monkeypatch.setattr(engine, "extract_document", track_extraction)

    exit_code = cli.main(["check", ".", "--verbose"])
    captured = capsys.readouterr()

    assert exit_code == 2, "an invalid Python encoding is an operational failure"
    assert extracted_syntaxes == [model.Syntax.RUST_DOC_COMMENT], (
        "later discovered inputs remain checked after the read failure"
    )
    assert captured.out == (
        "checked 2 files (0 skipped, 1 unreadable); 0 errors, 0 warnings\n"
    ), "the run summary includes the unreadable Python file"
    assert "failed to read src/a-broken.py" in captured.err, (
        "the invalid source encoding is reported as a file read failure"
    )
    metrics_line = next(
        line
        for line in captured.err.splitlines()
        if line.startswith("stilyagi check metrics: ")
    )
    metrics_payload = json.loads(metrics_line.removeprefix("stilyagi check metrics: "))
    assert metrics_payload["stilyagi_check_unreadable_files_total"] == 1, (
        "verbose metrics count the unreadable Python file"
    )
    assert metrics_payload["stilyagi_check_operational_failures_total"]["read"] == 1, (
        "verbose metrics classify the error as a read failure"
    )
    assert metrics_payload["stilyagi_rust_extraction_documents_total"] == 1, (
        "verbose metrics prove the later Rust file was extracted"
    )
