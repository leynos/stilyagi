"""Property test for the inline-code index the text rules query.

The index answers containment by binary search over a folded span list, so its
correctness depends on that fold preserving enclosure under arbitrary order,
overlap, nesting, and duplication. The oracle is a direct scan over every span,
which shares no code with the indexed search.
"""

from hypothesis import given, settings
from hypothesis import strategies as st
from stilyagi.model.source import SourceSpan
from stilyagi.rules.inline_code import InlineCodeIndex

#: Offsets stay small so generated cases concentrate on overlap and boundary
#: shapes rather than on large empty gaps.
_INLINE_OFFSET_LIMIT = 24
_INLINE_SPAN_LIMIT = 6


@st.composite
def _inline_spans(draw: st.DrawFn) -> tuple[SourceSpan, ...]:
    """Build an unordered span list that may overlap, nest, or repeat."""
    count = draw(st.integers(min_value=0, max_value=_INLINE_SPAN_LIMIT))
    spans: list[SourceSpan] = []
    for _ in range(count):
        start = draw(st.integers(min_value=0, max_value=_INLINE_OFFSET_LIMIT))
        span_end = start + draw(
            st.integers(min_value=0, max_value=_INLINE_OFFSET_LIMIT)
        )
        spans.append(SourceSpan(start, span_end))
    return tuple(spans)


@st.composite
def _inline_candidate(draw: st.DrawFn) -> SourceSpan:
    """Build one candidate span for a containment query."""
    start = draw(st.integers(min_value=0, max_value=_INLINE_OFFSET_LIMIT))
    return SourceSpan(
        start,
        start + draw(st.integers(min_value=0, max_value=_INLINE_OFFSET_LIMIT)),
    )


@settings(max_examples=200, deadline=None)
@given(spans=_inline_spans(), candidate=_inline_candidate())
def test_inline_code_index_contains_agrees_with_a_direct_scan(
    spans: tuple[SourceSpan, ...],
    candidate: SourceSpan,
) -> None:
    """The indexed query answers exactly what scanning every span answers."""
    index = InlineCodeIndex.from_spans(spans)
    expected = any(span.contains(candidate) for span in spans)

    assert index.contains(candidate) is expected, (spans, candidate)
