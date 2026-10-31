"""Contract tests for the typed rule boundary introduced by roadmap 2.3.1."""

import pytest
from stilyagi import diagnostics, model
from stilyagi.engine import renderers, rule_view
from stilyagi.model.source import SourceSpan


class TestSourceSpan:
    """The shared source-coordinate type is total and never inverted."""

    def test_rejects_inverted_range(self) -> None:
        """An end before the start is refused at construction."""
        with pytest.raises(ValueError, match="must not precede"):
            SourceSpan(5, 4)

    def test_rejects_negative_start(self) -> None:
        """Negative byte offsets are not addressable."""
        with pytest.raises(ValueError, match="non-negative"):
            SourceSpan(-1, 4)

    def test_contains_is_inclusive_of_boundaries(self) -> None:
        """Containment admits spans that share an edge."""
        assert SourceSpan(0, 10).contains(SourceSpan(0, 10)), (
            "expected containment to include an identical span"
        )
        assert SourceSpan(0, 10).contains(SourceSpan(9, 10)), (
            "expected containment to include a span sharing an edge"
        )

    def test_overlaps_is_half_open(self) -> None:
        """Touching spans do not overlap, so adjacent edits never collide."""
        assert not SourceSpan(0, 4).overlaps(SourceSpan(4, 8)), (
            "expected touching spans not to overlap"
        )
        assert SourceSpan(0, 5).overlaps(SourceSpan(4, 8)), (
            "expected overlapping spans to be detected"
        )


class TestDiagnosticSpan:
    """Diagnostics carry an optional byte span without losing location data."""

    def test_diagnostic_defaults_to_no_span(self) -> None:
        """Operational diagnostics render a null span."""
        diagnostic = diagnostics.Diagnostic(
            path="docs/example.md", code="MD001", message="text"
        )
        assert diagnostic.span is None, "expected a diagnostic to default to no span"

    def test_diagnostic_accepts_span(self) -> None:
        """A rule diagnostic may carry a source-backed span."""
        diagnostic = diagnostics.Diagnostic(
            path="docs/example.md",
            code="STY001",
            message="repeated word",
            severity=diagnostics.Severity.WARNING,
            line=1,
            column=5,
            span=SourceSpan(4, 7),
        )
        assert diagnostic.span == SourceSpan(4, 7), (
            "expected the diagnostic to keep its source span"
        )
        assert diagnostics.is_failing_severity(diagnostic.severity) is False, (
            "expected a warning severity not to fail the run"
        )


class TestJsonSpanRendering:
    """The JSON contract exposes byte offsets next to line/column."""

    def test_span_is_rendered_as_byte_offsets(self) -> None:
        """A spanned diagnostic serializes byte_start and byte_end."""
        payload = _render_one(
            diagnostics.Diagnostic(
                path="docs/example.md",
                code="MD001",
                message="heading jump",
                line=3,
                column=1,
                span=SourceSpan(8, 18),
            )
        )
        assert payload["span"] == {"byte_start": 8, "byte_end": 18}, (
            "expected the span to render as byte offsets"
        )
        assert payload["location"] == {"line": 3, "column": 1}, (
            "expected the location to render line and column"
        )

    def test_operational_diagnostic_renders_null_span(self) -> None:
        """Diagnostics without a span keep the key with a null value."""
        payload = _render_one(
            diagnostics.Diagnostic(path="docs/example.md", code="MD001", message="text")
        )
        assert payload["span"] is None, "expected a missing span to render as null"


def _render_one(diagnostic: diagnostics.Diagnostic) -> dict[str, object]:
    """Render a single diagnostic through the real JSON renderer."""
    return renderers.diagnostic_payload(diagnostic)


class TestIrRegionView:
    """The region-aware view exposes the IR facts the builtin rules need."""

    def test_region_view_exposes_kind_scope_and_attrs(self) -> None:
        """Heading depth and scope survive the projection."""
        document = model.Document(
            syntax=model.Syntax.MARKDOWN,
            ir={
                "regions": [
                    {
                        "id": "r0",
                        "kind": "heading",
                        "scope": ["markdown", "heading", "h1"],
                        "attrs": {"depth": 1},
                        "segments": [
                            {
                                "text": "Title",
                                "node": "n1",
                                "source": {"byte_start": 2, "byte_end": 7},
                            }
                        ],
                    }
                ]
            },
        )
        regions = list(rule_view.iter_regions(document))
        assert len(regions) == 1, "expected the document to expose one region"
        assert regions[0].kind == "heading", (
            "expected the region kind to survive the projection"
        )
        assert regions[0].scope == ("markdown", "heading", "h1"), (
            "expected the region scope to survive the projection"
        )
        assert regions[0].attrs["depth"] == 1, (
            "expected the region attrs to survive the projection"
        )
        assert regions[0].segments[0].node == "n1", (
            "expected the segment node id to survive the projection"
        )
        assert regions[0].segments[0].span == SourceSpan(2, 7), (
            "expected the segment source span to survive the projection"
        )

    def test_inline_code_spans_come_from_canonical_nodes(self) -> None:
        """Inline-code exclusion uses node spans rather than region ownership."""
        document = model.Document(
            syntax=model.Syntax.MARKDOWN,
            ir={
                "nodes": [
                    {
                        "id": "n5",
                        "kind": "inlineCode",
                        "span": {"byte_start": 9, "byte_end": 17},
                    },
                    {
                        "id": "n6",
                        "kind": "text",
                        "span": {"byte_start": 17, "byte_end": 25},
                    },
                ],
                "regions": [],
            },
        )
        spans = rule_view.inline_code_spans(document)
        assert spans == (SourceSpan(9, 17),), (
            "expected inline-code spans to come from canonical nodes"
        )
