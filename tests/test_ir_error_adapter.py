"""Tests for the IR-error adapter seam."""

from stilyagi import diagnostics, engine, model
from stilyagi.engine.checker import map_ir_errors

from tests.support.assertions import assert_with_context
from tests.support.malformed_corpus import MALFORMED_MARKDOWN_CORPUS


def test_map_ir_errors_maps_a_synthetic_error_to_a_diagnostic() -> None:
    """Convert the IR error envelope into the public diagnostic model."""
    document = model.Document(
        syntax=model.Syntax.MARKDOWN,
        ir={
            "line_index": [0, 6, 12],
            "errors": [
                {
                    "code": "suppression-blanket-forbidden",
                    "message": "Synthetic IR error",
                    "span": {"byte_start": 7, "byte_end": 9},
                },
            ],
        },
    )

    assert_with_context(
        map_ir_errors(document, "docs/example.md")
        == [
            diagnostics.Diagnostic(
                path="docs/example.md",
                code="suppression-blanket-forbidden",
                message="Synthetic IR error",
                severity=diagnostics.Severity.ERROR,
                line=2,
                column=2,
            ),
        ],
        "expected map_ir_errors(document, 'docs/example.md') ...",
    )


def test_map_ir_errors_demotes_unclassified_codes_to_warnings() -> None:
    """Keep new extraction anomaly codes on the non-gating severity path."""
    document = model.Document(
        syntax=model.Syntax.RUST_DOC_COMMENT,
        ir={
            "line_index": [0],
            "errors": [{"code": "future-anomaly", "message": "Recovered"}],
        },
    )

    diagnostics_list = map_ir_errors(document, "src/lib.rs")

    assert_with_context(
        diagnostics_list[0].severity is diagnostics.Severity.WARNING,
        "expected diagnostics_list[0].severity is diagnostics.Severity.WARNING",
    )


def test_map_ir_errors_handles_empty_or_missing_ir_errors() -> None:
    """Return no diagnostics when the IR carries no recoverable errors."""
    empty_document = model.Document(
        syntax=model.Syntax.MARKDOWN,
        ir={"line_index": [0, 4], "errors": []},
    )
    none_document = model.Document(
        syntax=model.Syntax.MARKDOWN,
    )

    assert_with_context(
        not map_ir_errors(empty_document, "docs/example.md"),
        "expected not map_ir_errors(empty_document, 'docs/exa...",
    )
    assert_with_context(
        not map_ir_errors(none_document, "docs/example.md"),
        "expected not map_ir_errors(none_document, 'docs/exam...",
    )


def test_map_ir_errors_keeps_real_malformed_markdown_clean() -> None:
    """Pin the extractor's current Markdown recovery behaviour."""
    fixture_root = MALFORMED_MARKDOWN_CORPUS
    for fixture_path in sorted(fixture_root.iterdir()):
        if not fixture_path.is_file():
            continue
        document = engine.extract_document(
            fixture_path.read_text(encoding="utf-8"),
            model.Syntax.MARKDOWN,
        )

        assert document.ir is not None, "expected document.ir is not None"
        assert document.ir["errors"] == [], "expected document.ir['errors'] == []"
        assert_with_context(
            not map_ir_errors(document, fixture_path.as_posix()),
            "expected not map_ir_errors(document, fixture_path.as...",
        )


def test_map_ir_errors_demotes_unknown_suppression_prefix_codes_to_warnings() -> None:
    """Classify suppression codes by membership, not by a broad prefix rule."""
    document = model.Document(
        syntax=model.Syntax.MARKDOWN,
        ir={
            "line_index": [0],
            "errors": [{"code": "suppression-unknown-variant", "message": "New"}],
        },
    )

    diagnostics_list = map_ir_errors(document, "docs/example.md")

    assert_with_context(
        diagnostics_list[0].severity is diagnostics.Severity.WARNING,
        "expected an unlisted suppression-* code to fail safe to a warning",
    )
