"""Tests for the IR-error adapter seam."""

from __future__ import annotations

import pathlib

from stilyagi import diagnostics, engine, model
from stilyagi.engine.checker import map_ir_errors


def test_map_ir_errors_maps_a_synthetic_error_to_a_diagnostic() -> None:
    """Convert the IR error envelope into the public diagnostic model."""
    document = model.Document(
        syntax=model.Syntax.MARKDOWN,
        ir={
            "line_index": [0, 6, 12],
            "errors": [
                {
                    "code": "IR123",
                    "message": "Synthetic IR error",
                    "span": {"byte_start": 7, "byte_end": 9},
                },
            ],
        },
    )

    assert map_ir_errors(document, "docs/example.md") == [
        diagnostics.Diagnostic(
            path="docs/example.md",
            code="IR000",
            message="Synthetic IR error",
            severity=diagnostics.Severity.ERROR,
            line=2,
            column=2,
        ),
    ]


def test_map_ir_errors_handles_empty_or_missing_ir_errors() -> None:
    """Return no diagnostics when the IR carries no recoverable errors."""
    empty_document = model.Document(
        syntax=model.Syntax.MARKDOWN,
        ir={"line_index": [0, 4], "errors": []},
    )
    none_document = model.Document(
        syntax=model.Syntax.MARKDOWN,
    )

    assert not map_ir_errors(empty_document, "docs/example.md")
    assert not map_ir_errors(none_document, "docs/example.md")


def test_map_ir_errors_keeps_real_malformed_markdown_clean() -> None:
    """Pin the extractor's current Markdown recovery behaviour."""
    fixture_root = pathlib.Path("tests/fixtures/corpus/markdown/malformed")
    for fixture_path in sorted(fixture_root.iterdir()):
        if not fixture_path.is_file():
            continue
        document = engine.extract_document(
            fixture_path.read_text(encoding="utf-8"),
            model.Syntax.MARKDOWN,
        )

        assert document.ir is not None
        assert document.ir["errors"] == []
        assert not map_ir_errors(document, fixture_path.as_posix())
