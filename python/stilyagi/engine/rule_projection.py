"""Project the canonical IR into the typed facts builtin rules consume.

One :func:`project` call builds every per-document index the rules need: the
region list, the canonical node-id index, the inline-code node spans, and the
prose units an ``ignore-next`` directive may consume. Projecting once and
sharing the result keeps a document's cost independent of how many rules are
selected.

A segment's advertised source span is trusted only when the source slice
decodes to exactly the segment text. A stale or malformed span is demoted to a
synthetic segment, so a byte-exact finding can never point at other bytes.
"""

import dataclasses as dc
import typing as typ

from stilyagi.engine.ir_mapping import (
    ir_mapping,
    ir_sequence,
    is_sequence,
    merge_touching_spans,
    segment_with_text,
    source_span,
    string_tuple,
)
from stilyagi.model.region import RegionSegment, RegionView
from stilyagi.model.source import SourceSpan

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from stilyagi import model
    from stilyagi.rules.base import RegionTarget

__all__ = [
    "DocumentRegionView",
    "project",
    "select_regions",
]

_INLINE_CODE_KINDS: frozenset[str] = frozenset({"inlineCode", "inline_code"})
_IGNORE_NEXT_KINDS: frozenset[str] = frozenset({"heading", "paragraph", "table_cell"})


@dc.dataclass(frozen=True, slots=True)
class DocumentRegionView:
    """Every region-derived fact one document offers its rules.

    Parameters
    ----------
    regions:
        Projected regions in canonical document order.
    inline_code_spans:
        Canonical inline-code node spans, merged when touching.
    prose_units:
        Nonempty heading, paragraph, and table-cell spans in source order, the
        units an ``ignore-next`` directive may consume.

    Examples
    --------
    >>> DocumentRegionView().regions
    ()
    """

    regions: tuple[RegionView, ...] = ()
    inline_code_spans: tuple[SourceSpan, ...] = ()
    prose_units: tuple[SourceSpan, ...] = ()

    def for_target(self, target: RegionTarget) -> tuple[RegionView, ...]:
        """Return the regions ``target`` claims, in document order.

        Parameters
        ----------
        target:
            The rule's declared syntax, kinds, and required scope tokens.

        Returns
        -------
        tuple[RegionView, ...]
            Regions satisfying every part of the target.

        Examples
        --------
        >>> from stilyagi.rules.base import RegionTarget
        >>> DocumentRegionView().for_target(RegionTarget(kinds=("heading",)))
        ()
        """
        return select_regions(self.regions, target)


def project(
    document: model.Document,
    *,
    source_bytes: bytes | None = None,
) -> DocumentRegionView:
    """Build the per-document region projection.

    Parameters
    ----------
    document:
        Extracted document whose IR carries regions, nodes, and suppressions.
    source_bytes:
        Original file bytes. When supplied, each segment's advertised span is
        kept only if that slice decodes to exactly the segment text.

    Returns
    -------
    DocumentRegionView
        Regions, inline-code spans, and prose units for this document.

    Examples
    --------
    >>> from stilyagi import model
    >>> project(model.Document(syntax=model.Syntax.MARKDOWN)).regions
    ()
    """
    nodes, inline_spans = _node_facts(document)
    regions = tuple(
        region
        for raw_region in ir_sequence(document, "regions")
        if (region := _region_view(raw_region, nodes, source_bytes)) is not None
    )
    return DocumentRegionView(
        regions=regions,
        inline_code_spans=merge_touching_spans(sorted(inline_spans)),
        prose_units=tuple(
            region.span
            for region in regions
            if region.kind in _IGNORE_NEXT_KINDS
            and not region.is_empty
            and region.span is not None
        ),
    )


def select_regions(
    regions: cabc.Iterable[RegionView],
    target: RegionTarget,
) -> tuple[RegionView, ...]:
    """Return the regions one rule target claims from a projection.

    Parameters
    ----------
    regions:
        Already-projected regions in document order.
    target:
        The rule's declared syntax, kinds, and required scope tokens.

    Returns
    -------
    tuple[RegionView, ...]
        Regions satisfying every part of the target, in document order.

    Examples
    --------
    >>> from stilyagi.rules.base import RegionTarget
    >>> select_regions((), RegionTarget(kinds=("heading",)))
    ()
    """
    return tuple(region for region in regions if target.matches_region(region))


def _node_facts(
    document: model.Document,
) -> tuple[dict[str, SourceSpan], list[SourceSpan]]:
    """Return the node-id index and inline-code spans in one node pass."""
    index: dict[str, SourceSpan] = {}
    inline: list[SourceSpan] = []
    for raw_node in ir_sequence(document, "nodes"):
        node = ir_mapping(raw_node)
        if node is None:
            continue
        span = source_span(node.get("span"))
        if span is None:
            continue
        node_id = node.get("id")
        if isinstance(node_id, str):
            index[node_id] = span
        kind = node.get("kind")
        if isinstance(kind, str) and kind in _INLINE_CODE_KINDS:
            inline.append(span)
    return index, inline


def _region_view(
    raw_region: object,
    nodes: cabc.Mapping[str, SourceSpan],
    source_bytes: bytes | None,
) -> RegionView | None:
    """Convert one raw region mapping into a safe typed view."""
    region = ir_mapping(raw_region)
    if region is None:
        return None
    region_id = region.get("id")
    kind = region.get("kind")
    if not isinstance(region_id, str) or not isinstance(kind, str):
        return None
    segments = tuple(_region_segments(region, source_bytes))
    return RegionView(
        region_id=region_id,
        kind=kind,
        syntax=_string(region.get("syntax"), "markdown"),
        scope=string_tuple(region.get("scope")),
        attrs=_attribute_mapping(region.get("attrs")),
        segments=segments,
        span=_region_span(region, segments, nodes),
    )


def _region_span(
    region: cabc.Mapping[str, object],
    segments: tuple[RegionSegment, ...],
    nodes: cabc.Mapping[str, SourceSpan],
) -> SourceSpan | None:
    """Return the canonical region span, preferring origin node spans."""
    origin_spans = [
        nodes[node_id]
        for node_id in string_tuple(region.get("origin_nodes"))
        if node_id in nodes
    ]
    if origin_spans:
        return _bounding_span(origin_spans)
    return _bounding_span(
        segment.span for segment in segments if segment.span is not None
    )


def _bounding_span(spans: cabc.Iterable[SourceSpan]) -> SourceSpan | None:
    """Return the span covering every supplied span, or ``None`` when empty."""
    materialized = list(spans)
    if not materialized:
        return None
    return SourceSpan(
        min(span.byte_start for span in materialized),
        max(span.byte_end for span in materialized),
    )


def _region_segments(
    region: cabc.Mapping[str, object],
    source_bytes: bytes | None,
) -> cabc.Iterator[RegionSegment]:
    """Yield well-formed segments from one raw region mapping."""
    raw_segments = region.get("segments")
    if not is_sequence(raw_segments):
        return
    for raw_segment in typ.cast("cabc.Sequence[object]", raw_segments):
        segment = _segment_view(raw_segment, source_bytes)
        if segment is not None:
            yield segment


def _segment_view(
    raw_segment: object,
    source_bytes: bytes | None,
) -> RegionSegment | None:
    """Convert one raw segment mapping into a safe typed view."""
    typed = segment_with_text(raw_segment)
    if typed is None:
        return None
    segment, text = typed
    node = segment.get("node")
    owner = node if isinstance(node, str) else None
    source = segment.get("source")
    if source is None:
        synthetic = segment.get("synthetic")
        return RegionSegment(
            span=None,
            text=text,
            node=owner,
            synthetic_reason=synthetic if isinstance(synthetic, str) else None,
        )
    span = source_span(source)
    if span is None:
        return None
    if source_bytes is not None and not _slice_matches(source_bytes, span, text):
        # The advertised span does not address this text. Treat the segment as
        # synthetic rather than let a byte-exact finding point at other bytes.
        return RegionSegment(
            span=None, text=text, node=owner, synthetic_reason="source_mismatch"
        )
    return RegionSegment(span=span, text=text, node=owner)


def _slice_matches(source_bytes: bytes, span: SourceSpan, text: str) -> bool:
    """Return whether ``span`` addresses exactly ``text`` in the source.

    The bounds check matters: Python clamps an over-long slice, so a span
    running past end-of-file would otherwise "match" whatever prefix it
    covered and advertise an interval the file does not have.

    Returns
    -------
    bool
        ``True`` when the span is in bounds and its bytes decode to ``text``.
    """
    if span.byte_start < 0 or span.byte_end > len(source_bytes):
        return False
    try:
        return source_bytes[span.byte_start : span.byte_end].decode("utf-8") == text
    except UnicodeDecodeError:
        return False


def _attribute_mapping(value: object) -> cabc.Mapping[str, object]:
    """Return a region attribute mapping, defaulting to empty."""
    typed_value = ir_mapping(value)
    return typed_value if typed_value is not None else {}


def _string(value: object, default: str) -> str:
    """Return a string-valued IR field or its default."""
    return value if isinstance(value, str) else default
