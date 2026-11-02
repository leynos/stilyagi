"""Contract tests for the typed rule boundary introduced by roadmap 2.3.1."""

import pytest
from stilyagi import diagnostics, model
from stilyagi.engine import renderers, rule_view
from stilyagi.engine.ir_mapping import segment_with_text, source_span, span_fields
from stilyagi.model.source import SourceSpan, is_utf8_boundary
from stilyagi.rules.registry import RuleRunRequest

from tests.support.rule_fixtures import LintSetup, spans_of


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


class TestRawSpanTolerance:
    """Malformed IR spans are absent to projection rather than fatal."""

    def test_a_negative_start_is_absent(self) -> None:
        """A negative offset cannot address the source and must not raise."""
        assert source_span({"byte_start": -1, "byte_end": 4}) is None, (
            "expected a negative byte start to be dropped"
        )
        assert source_span({"byte_start": -3, "byte_end": -1}) is None, (
            "expected an entirely negative span to be dropped"
        )

    def test_a_reversed_span_is_absent(self) -> None:
        """Ordering is still enforced alongside the non-negative bound."""
        assert source_span({"byte_start": 4, "byte_end": 1}) is None, (
            "expected a reversed span to be dropped"
        )

    def test_a_non_mapping_span_is_absent(self) -> None:
        """A span that is not a mapping cannot carry offsets."""
        assert source_span(42) is None, "expected a non-mapping span to be dropped"
        assert span_fields(42) is None, (
            "expected span_fields to reject a non-mapping value"
        )

    def test_a_non_integer_offset_is_absent(self) -> None:
        """Offsets must be integers, not strings that merely look numeric."""
        assert span_fields({"byte_start": "0", "byte_end": 4}) is None, (
            "expected a string offset to be rejected"
        )
        assert source_span({"byte_start": 0, "byte_end": None}) is None, (
            "expected a missing offset to be rejected"
        )

    def test_segment_with_text_rejects_a_non_mapping(self) -> None:
        """A segment that is not a mapping has no text to project."""
        assert segment_with_text(42) is None, (
            "expected a non-mapping segment to be rejected"
        )


class TestUtf8Boundary:
    """Byte offsets are only addressable when they fall on a code-point edge."""

    def test_an_offset_past_the_end_is_not_a_boundary(self) -> None:
        """An out-of-range offset cannot address the source."""
        assert is_utf8_boundary(b"abc", 4) is False, (
            "expected an offset past the end not to be a boundary"
        )

    def test_a_negative_offset_is_not_a_boundary(self) -> None:
        """A negative offset is outside the source entirely."""
        assert is_utf8_boundary(b"abc", -1) is False, (
            "expected a negative offset not to be a boundary"
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


def _heading_region(
    depth: int,
    *,
    origin_nodes: tuple[str, ...] = (),
) -> dict[str, object]:
    """Build one heading region with no source-backed segments."""
    return {
        "id": f"r{depth}",
        "kind": "heading",
        "syntax": "markdown",
        "scope": ["markdown", "heading", f"h{depth}"],
        "attrs": {"depth": depth},
        "segments": [{"text": "heading", "synthetic": "placeholder"}],
        "origin_nodes": list(origin_nodes),
    }


class TestNodeSpanValidation:
    """Node spans are kept only when they address real, aligned source bytes."""

    @pytest.mark.parametrize(
        "node_span",
        [
            pytest.param({"byte_start": 0, "byte_end": 99}, id="past-end-of-file"),
            pytest.param({"byte_start": 0, "byte_end": 1}, id="cuts-a-code-point"),
            pytest.param({"byte_start": 1, "byte_end": 2}, id="starts-mid-point"),
        ],
    )
    def test_an_unaddressable_node_span_is_dropped(
        self,
        node_span: dict[str, int],
    ) -> None:
        """Out-of-bounds and mid-code-point node spans never reach a rule."""
        document = model.Document(
            syntax=model.Syntax.MARKDOWN,
            ir={
                "nodes": [{"id": "n1", "kind": "heading", "span": node_span}],
                "regions": [_heading_region(1, origin_nodes=("n1",))],
            },
        )

        view = rule_view.project(document, source_bytes="é\n".encode())

        assert view.regions[0].node_span is None, (
            "expected an unaddressable node span to be dropped"
        )
        assert view.regions[0].span is None, (
            "expected the region span not to fall back to the dropped node span"
        )

    def test_an_aligned_node_span_is_kept(self) -> None:
        """A bounded, code-point-aligned span remains the canonical node span."""
        document = model.Document(
            syntax=model.Syntax.MARKDOWN,
            ir={
                "nodes": [
                    {
                        "id": "n1",
                        "kind": "heading",
                        "span": {"byte_start": 0, "byte_end": 3},
                    }
                ],
                "regions": [_heading_region(1, origin_nodes=("n1",))],
            },
        )

        view = rule_view.project(document, source_bytes="é\n".encode())

        assert view.regions[0].node_span == SourceSpan(0, 3), (
            "expected the aligned node span to survive projection"
        )


def test_a_heading_without_a_node_span_is_omitted_but_still_sets_depth() -> None:
    """``MD001`` never reports an unlocatable heading, but its depth counts."""
    source = b"# One\n### Three\n##### Five\n"
    document = model.Document(
        syntax=model.Syntax.MARKDOWN,
        ir={
            "nodes": [
                {
                    "id": "n5",
                    "kind": "heading",
                    "span": {"byte_start": 16, "byte_end": 26},
                }
            ],
            "regions": [
                _heading_region(1),
                _heading_region(3),
                _heading_region(5, origin_nodes=("n5",)),
            ],
        },
    )

    result = LintSetup().run_document(document, source)

    assert spans_of(result) == ((16, 26),), (
        "expected only the locatable h5 jump to report, from an h3 baseline"
    )


class TestProjectionTolerance:
    """Malformed IR entries are skipped rather than aborting the projection."""

    def test_a_non_mapping_node_is_skipped(self) -> None:
        """A node entry that is not a mapping contributes no span."""
        document = model.Document(
            syntax=model.Syntax.MARKDOWN,
            ir={"nodes": [42], "regions": []},
        )

        view = rule_view.project(document, source_bytes=b"text")

        assert view.inline_code_spans == (), (
            "expected a non-mapping node to contribute no inline-code span"
        )

    def test_a_non_mapping_region_is_skipped(self) -> None:
        """A region entry that is not a mapping is dropped."""
        document = model.Document(
            syntax=model.Syntax.MARKDOWN,
            ir={"regions": [42]},
        )

        assert list(rule_view.iter_regions(document)) == [], (
            "expected a non-mapping region to be dropped"
        )

    def test_a_region_without_an_id_or_kind_is_skipped(self) -> None:
        """Both the region id and kind must be strings to form a view."""
        document = model.Document(
            syntax=model.Syntax.MARKDOWN,
            ir={"regions": [{"id": 1, "kind": "heading"}]},
        )

        assert list(rule_view.iter_regions(document)) == [], (
            "expected a region with a non-string id to be dropped"
        )

    def test_a_region_with_non_sequence_segments_is_skipped(self) -> None:
        """A ``segments`` value that is not a sequence yields no segments."""
        document = model.Document(
            syntax=model.Syntax.MARKDOWN,
            ir={"regions": [{"id": "r0", "kind": "heading", "segments": "nope"}]},
        )

        regions = list(rule_view.iter_regions(document))

        assert len(regions) == 1, "expected the region itself to survive"
        assert regions[0].segments == (), (
            "expected a non-sequence segments value to yield no segments"
        )

    def test_a_non_mapping_segment_is_skipped(self) -> None:
        """A segment entry that is not a mapping is dropped."""
        document = model.Document(
            syntax=model.Syntax.MARKDOWN,
            ir={"regions": [{"id": "r0", "kind": "heading", "segments": [42]}]},
        )

        regions = list(rule_view.iter_regions(document))

        assert regions[0].segments == (), "expected a non-mapping segment to be dropped"

    def test_a_segment_with_a_malformed_source_span_is_skipped(self) -> None:
        """A reversed source span cannot address text and is dropped."""
        document = model.Document(
            syntax=model.Syntax.MARKDOWN,
            ir={
                "regions": [
                    {
                        "id": "r0",
                        "kind": "heading",
                        "segments": [
                            {
                                "text": "Title",
                                "source": {"byte_start": 4, "byte_end": 1},
                            }
                        ],
                    }
                ]
            },
        )

        regions = list(rule_view.iter_regions(document))

        assert regions[0].segments == (), (
            "expected a malformed segment source span to be dropped"
        )


class TestRuleRunRequestSlice:
    """The request exposes the original bytes a rule may address."""

    def test_slice_returns_the_addressed_bytes(self) -> None:
        """A span selects a half-open byte range from the source."""
        request = RuleRunRequest.__new__(RuleRunRequest)
        object.__setattr__(request, "source_bytes", b"hello")

        assert request.slice(SourceSpan(1, 4)) == b"ell", (
            "expected the slice to return the addressed bytes"
        )
