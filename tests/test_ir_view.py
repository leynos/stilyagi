"""Tests for the typed, read-only IR view."""

import pathlib
import typing as typ

from stilyagi import engine, model
from stilyagi.engine.ir_view import (
    SegmentView,
    SourceSpan,
    byte_start_from_span,
    iter_segments,
    line_index,
    segment_for_span,
    source_backed_spans,
)
from syrupy.extensions.json import JSONSnapshotExtension

from tests.support.assertions import assert_with_context

_MARKDOWN_FIXTURES = pathlib.Path("tests/fixtures/corpus/markdown/valid")

if typ.TYPE_CHECKING:
    from syrupy.assertion import SnapshotAssertion


def _extract_fixture(name: str) -> model.Document:
    """Extract one real Markdown fixture through the public engine boundary."""
    source = (_MARKDOWN_FIXTURES / name).read_text(encoding="utf-8")
    return engine.extract_document(source, model.Syntax.MARKDOWN)


def test_iter_segments_preserves_real_source_and_synthetic_segments() -> None:
    """Expose the paragraph fixture's source-backed and synthetic segments."""
    document = _extract_fixture("heading-table-link-suppression.md")

    assert_with_context(
        tuple(iter_segments(document))[1:5]
        == (
            SegmentView(SourceSpan(19, 46), "This paragraph links to the", None),
            SegmentView(None, " ", "softbreak_space"),
            SegmentView(SourceSpan(48, 63), "Stilyagi design", None),
            SegmentView(SourceSpan(104, 105), ".", None),
        ),
        "expected the real paragraph's segment provenance",
    )


def test_source_backed_spans_excludes_decoded_link_and_image_regions() -> None:
    """Leave decoded link titles and image alt text without source spans."""
    document = _extract_fixture("links-and-images.md.fixture")
    decoded_texts = {"Inline title", "plain alt", "AT&T"}
    decoded_segments = tuple(
        segment for segment in iter_segments(document) if segment.text in decoded_texts
    )

    assert decoded_segments, "expected decoded link and image segments"
    assert_with_context(
        all(segment.span is None for segment in decoded_segments),
        "expected decoded link and image segments to have no source span",
    )


def test_source_backed_spans_merges_touching_segments() -> None:
    """Merge touching source-backed spans before later containment checks."""
    document = model.Document(
        syntax=model.Syntax.MARKDOWN,
        ir={
            "regions": [
                {
                    "segments": [
                        {"text": "a", "source": {"byte_start": 1, "byte_end": 2}},
                        {"text": "b", "source": {"byte_start": 2, "byte_end": 3}},
                    ],
                },
            ],
        },
    )

    assert_with_context(
        source_backed_spans(document) == (SourceSpan(1, 3),),
        "expected touching source spans to merge into SourceSpan(1, 3)",
    )


def test_ir_view_tolerates_malformed_payloads() -> None:
    """Return empty or absent views instead of raising on malformed IR."""
    malformed_document = model.Document(
        syntax=model.Syntax.MARKDOWN,
        ir={"regions": [{"segments": [{"source": {"byte_start": "bad"}}]}]},
    )

    assert not tuple(iter_segments(malformed_document)), "expected no segments"
    assert not source_backed_spans(malformed_document), "expected no source spans"
    assert line_index(malformed_document) is None, "expected no line index"
    assert byte_start_from_span({"byte_start": "bad"}) is None, (
        "expected a non-integer byte start to be absent"
    )


def test_segment_for_span_and_line_index_read_real_ir(
    snapshot: SnapshotAssertion,
) -> None:
    """Read a source-backed segment and line index from the extracted fixture."""
    document = _extract_fixture("heading-table-link-suppression.md")
    span = SourceSpan(48, 63)

    assert_with_context(
        segment_for_span(document, span)
        == SegmentView(
            span,
            "Stilyagi design",
            None,
        ),
        "expected the real source-backed link text segment",
    )
    assert_with_context(
        line_index(document) == snapshot(extension_class=JSONSnapshotExtension),
        "expected the real fixture's line-index bytes to match the snapshot",
    )
    assert byte_start_from_span({"byte_start": 48}) == 48, (
        "expected the integer byte start to be preserved"
    )
