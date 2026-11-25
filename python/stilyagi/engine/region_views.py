"""Convert one raw IR region into the typed view builtin rules consume.

This module owns the raw-to-typed conversion for a single region: its identity,
syntax, scope, attributes, owner metadata, origin span, and segments. The
document-level projection in :mod:`stilyagi.engine.rule_projection` collects
these views, so the recovery policy for one malformed entry lives beside the
entry it recovers from rather than in the collection loop.

Every recovery is counted in the caller's :class:`AnomalyTally` under the fixed
label vocabulary, never guessed at here. A region that cannot be identified is
dropped; a segment whose advertised span does not address its text is demoted
to synthetic, so a byte-exact finding can never point at other bytes.
"""

import typing as typ

from stilyagi.engine.ir_mapping import (
    ir_mapping,
    is_sequence,
    segment_with_text,
    source_span,
    string_tuple,
)
from stilyagi.model.region import RegionOwner, RegionSegment, RegionView
from stilyagi.model.source import SourceSpan

if typ.TYPE_CHECKING:  # pragma: no cover - typing only
    import collections.abc as cabc

    from stilyagi.engine.projection_anomalies import AnomalyTally

__all__ = ["region_view"]


def region_view(
    raw_region: object,
    nodes: cabc.Mapping[str, SourceSpan],
    source_bytes: bytes | None,
    anomalies: AnomalyTally,
) -> RegionView | None:
    """Convert one raw region mapping into a safe typed view.

    Parameters
    ----------
    raw_region:
        One entry of the IR ``regions`` array.
    nodes:
        Located node spans by id, used for the region's origin span.
    source_bytes:
        Original file bytes, or ``None`` when the caller has none.
    anomalies:
        The projection's tally, incremented once per recovered entry.

    Returns
    -------
    RegionView | None
        The typed region, or ``None`` when it cannot be identified.
    """
    region = ir_mapping(raw_region)
    if region is None:
        anomalies["malformed_region"] += 1
        return None
    region_id = region.get("id")
    kind = region.get("kind")
    if not isinstance(region_id, str) or not isinstance(kind, str):
        anomalies["malformed_region"] += 1
        return None
    segments = tuple(_region_segments(region, source_bytes, anomalies))
    node_span = _origin_span(region, nodes)
    return RegionView(
        region_id=region_id,
        kind=kind,
        syntax=_string(region.get("syntax"), "markdown"),
        scope=string_tuple(region.get("scope")),
        attrs=_attribute_mapping(region.get("attrs")),
        segments=segments,
        span=node_span
        if node_span is not None
        else _bounding_span(
            segment.span for segment in segments if segment.span is not None
        ),
        node_span=node_span,
        owner=_owner_view(region.get("owner"), anomalies),
    )


def _owner_view(value: object, anomalies: AnomalyTally) -> RegionOwner | None:
    """Convert a raw owner value into a typed view, or report it unusable.

    An absent owner is ordinary: Markdown regions never carry one, and a
    module or anonymous item documents no name. An owner that is present but
    not a mapping with a string ``kind`` and optional string names is counted
    under ``malformed_region`` and dropped, so no rule reads half-validated
    metadata. The region itself is still projected because its text is
    unaffected.

    Returns
    -------
    RegionOwner | None
        The typed owner, or ``None`` when absent or unusable.
    """
    owner = ir_mapping(value)
    typed = None if owner is None else _typed_owner(owner)
    if typed is None and value is not None:
        anomalies["malformed_region"] += 1
    return typed


def _typed_owner(owner: cabc.Mapping[str, object]) -> RegionOwner | None:
    """Return a typed owner, or ``None`` when any field has the wrong type.

    Returns
    -------
    RegionOwner | None
        The owner when ``kind`` is a string and both names are absent or
        strings, otherwise ``None``.
    """
    kind = owner.get("kind")
    name = owner.get("name")
    qualname = owner.get("qualname")
    if not isinstance(kind, str):
        return None
    if not _is_optional_string(name) or not _is_optional_string(qualname):
        return None
    return RegionOwner(
        kind=kind,
        name=typ.cast("str | None", name),
        qualname=typ.cast("str | None", qualname),
    )


def _is_optional_string(value: object) -> bool:
    """Return whether ``value`` is ``None`` or a string.

    Returns
    -------
    bool
        ``True`` for ``None`` and for strings, ``False`` for anything else.

    Examples
    --------
    >>> _is_optional_string(None), _is_optional_string("x"), _is_optional_string(1)
    (True, True, False)
    """
    return value is None or isinstance(value, str)


def _origin_span(
    region: cabc.Mapping[str, object],
    nodes: cabc.Mapping[str, SourceSpan],
) -> SourceSpan | None:
    """Return the bounding span of a region's origin nodes, if any.

    Returns
    -------
    SourceSpan | None
        The covering span, or ``None`` when no origin node was located.
    """
    return _bounding_span(
        nodes[node_id]
        for node_id in string_tuple(region.get("origin_nodes"))
        if node_id in nodes
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
    anomalies: AnomalyTally,
) -> cabc.Iterator[RegionSegment]:
    """Yield well-formed segments from one raw region mapping."""
    raw_segments = region.get("segments")
    if not is_sequence(raw_segments):
        anomalies["malformed_region"] += 1
        return
    for raw_segment in raw_segments:
        segment = _segment_view(raw_segment, source_bytes, anomalies)
        if segment is not None:
            yield segment


def _segment_view(
    raw_segment: object,
    source_bytes: bytes | None,
    anomalies: AnomalyTally,
) -> RegionSegment | None:
    """Convert one raw segment mapping into a safe typed view."""
    typed = segment_with_text(raw_segment)
    if typed is None:
        anomalies["malformed_segment"] += 1
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
        anomalies["invalid_segment_span"] += 1
        return None
    if source_bytes is not None and not _slice_matches(source_bytes, span, text):
        # The advertised span does not address this text. Treat the segment as
        # synthetic rather than let a byte-exact finding point at other bytes.
        anomalies["source_mismatch"] += 1
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
