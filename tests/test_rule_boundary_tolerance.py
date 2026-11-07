"""Tolerance tests for malformed IR and source coordinates.

The rule boundary is deliberately total: a corrupt IR entry, a non-integer
offset, or a segment with no source must degrade to "absent" rather than abort
a whole run. These tests pin those degradation paths, which are hard to reach
through the real extractor because it never emits them.
"""

import pytest
from stilyagi import model
from stilyagi.engine import rule_view
from stilyagi.model.region import RegionSegment
from stilyagi.model.source import SourceSpan, is_utf8_boundary
from stilyagi.rules.builtin.text import Token, token_span, utf8_offsets
from stilyagi.rules.registry import RuleRunRequest

from tests.support.rule_fixtures import LintSetup, spans_of


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


class TestRuleRunRequestSlice:
    """The request exposes the original bytes a rule may address."""

    def test_slice_returns_the_addressed_bytes(self) -> None:
        """A span selects a half-open byte range from the source."""
        request = RuleRunRequest.__new__(RuleRunRequest)
        object.__setattr__(request, "source_bytes", b"hello")

        assert request.slice(SourceSpan(1, 4)) == b"ell", (
            "expected the slice to return the addressed bytes"
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

        assert not view.inline_code_spans, (
            "expected a non-mapping node to contribute no inline-code span"
        )

    def test_a_non_mapping_region_is_skipped(self) -> None:
        """A region entry that is not a mapping is dropped."""
        document = model.Document(
            syntax=model.Syntax.MARKDOWN,
            ir={"regions": [42]},
        )

        regions = list(rule_view.iter_regions(document))

        assert not regions, "expected a non-mapping region to be dropped"

    def test_a_region_without_an_id_or_kind_is_skipped(self) -> None:
        """Both the region id and kind must be strings to form a view."""
        document = model.Document(
            syntax=model.Syntax.MARKDOWN,
            ir={"regions": [{"id": 1, "kind": "heading"}]},
        )

        regions = list(rule_view.iter_regions(document))

        assert not regions, "expected a region with a non-string id to be dropped"

    def test_a_region_with_non_sequence_segments_is_skipped(self) -> None:
        """A ``segments`` value that is not a sequence yields no segments."""
        document = model.Document(
            syntax=model.Syntax.MARKDOWN,
            ir={"regions": [{"id": "r0", "kind": "heading", "segments": "nope"}]},
        )

        regions = list(rule_view.iter_regions(document))

        assert len(regions) == 1, "expected the region itself to survive"
        assert not regions[0].segments, (
            "expected a non-sequence segments value to yield no segments"
        )

    def test_a_non_mapping_segment_is_skipped(self) -> None:
        """A segment entry that is not a mapping is dropped."""
        document = model.Document(
            syntax=model.Syntax.MARKDOWN,
            ir={"regions": [{"id": "r0", "kind": "heading", "segments": [42]}]},
        )

        regions = list(rule_view.iter_regions(document))

        assert not regions[0].segments, "expected a non-mapping segment to be dropped"

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

        assert not regions[0].segments, (
            "expected a malformed segment source span to be dropped"
        )


def test_token_span_requires_a_source_backed_segment() -> None:
    """A synthetic segment has no bytes to address, so mapping it is an error."""
    segment = RegionSegment(None, "aé")

    with pytest.raises(ValueError, match="source-backed"):
        token_span(segment, utf8_offsets("aé"), Token("aé", 0, 2))


def _heading_region_without_depth() -> dict[str, object]:
    """Build one heading region whose attrs carry no depth."""
    return {
        "id": "r1",
        "kind": "heading",
        "syntax": "markdown",
        "scope": ["markdown", "heading"],
        "attrs": {},
        "segments": [{"text": "Two", "synthetic": "placeholder"}],
    }


def test_a_heading_without_a_depth_is_skipped() -> None:
    """A depth-less heading cannot become the depth the next heading compares to."""
    source = b"# One\n### Three\n"
    document = model.Document(
        syntax=model.Syntax.MARKDOWN,
        ir={
            "nodes": [
                {
                    "id": "n1",
                    "kind": "heading",
                    "span": {"byte_start": 0, "byte_end": 6},
                },
                {
                    "id": "n3",
                    "kind": "heading",
                    "span": {"byte_start": 6, "byte_end": 16},
                },
            ],
            "regions": [
                {
                    "id": "r0",
                    "kind": "heading",
                    "syntax": "markdown",
                    "scope": ["markdown", "heading", "h1"],
                    "attrs": {"depth": 1},
                    "segments": [{"text": "One", "synthetic": "placeholder"}],
                    "origin_nodes": ["n1"],
                },
                _heading_region_without_depth(),
                {
                    "id": "r2",
                    "kind": "heading",
                    "syntax": "markdown",
                    "scope": ["markdown", "heading", "h3"],
                    "attrs": {"depth": 3},
                    "segments": [{"text": "Three", "synthetic": "placeholder"}],
                    "origin_nodes": ["n3"],
                },
            ],
        },
    )

    result = LintSetup().run_document(document, source)

    assert spans_of(result) == ((6, 16),), (
        "expected the h3 jump from the retained h1 baseline to report"
    )
