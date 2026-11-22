"""Project the canonical IR into the typed facts builtin rules consume.

One :func:`project` call builds every per-document index the rules need: the
region list, the canonical node-id index, the inline-code node spans, and the
prose units an ``ignore-next`` directive may consume. Projecting once and
sharing the result keeps a document's cost independent of how many rules are
selected.

A segment that advertises no source is synthetic. An advertised source that
cannot be read as a span is dropped and counted under
``invalid_segment_span``. When the caller supplies source bytes, an advertised
span is trusted only if it is bounded, UTF-8 aligned, and addresses exactly the
segment text; otherwise the segment is demoted to synthetic under
``source_mismatch``, so a byte-exact finding can never point at other bytes.

Recovering from malformed IR is not silent. Every recovered node, region,
segment, or unusable owner is counted under one of the six fixed labels and
returned in the projection's immutable snapshot, so a projection that suppresses
a finding can be told apart from a document that genuinely had none. The
single-region conversion lives in :mod:`stilyagi.engine.region_views`.
Projecting is itself read-only: the snapshot is turned into a metric and a log
line once per document by the rule runner, which knows the document's reported
path.
"""

import dataclasses as dc
import typing as typ

from stilyagi.engine.ir_mapping import (
    ir_mapping,
    ir_sequence,
    merge_touching_spans,
    source_span,
)
from stilyagi.engine.projection_anomalies import (
    AnomalyCounts,
    AnomalyTally,
    anomaly_snapshot,
)
from stilyagi.engine.region_views import region_view
from stilyagi.model.source import SourceSpan, is_utf8_boundary

if typ.TYPE_CHECKING:  # pragma: no cover - typing only
    import collections.abc as cabc

    from stilyagi import model
    from stilyagi.model.region import RegionView
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
    anomaly_counts:
        Recoveries this projection made, in fixed reporting order. Empty when
        the IR was well formed. The rule runner reports these once per
        document; projection and view queries never do.

    Examples
    --------
    >>> DocumentRegionView().regions
    ()
    """

    regions: tuple[RegionView, ...] = ()
    inline_code_spans: tuple[SourceSpan, ...] = ()
    prose_units: tuple[SourceSpan, ...] = ()
    anomaly_counts: AnomalyCounts = ()

    def for_target(self, target: RegionTarget) -> tuple[RegionView, ...]:
        """Return the regions ``target`` claims, in document order.

        Parameters
        ----------
        target:
            The rule's declared syntaxes, kinds, owner kinds, and required scope
            tokens.

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

    Projection is a read-only operation: it records no metric and emits no log
    line. A recovery it made is returned in ``anomaly_counts`` for the caller's
    reporting boundary to record, so projecting the same document twice — as
    suppression resolution does — cannot double-count its anomalies.

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
        Regions, inline-code spans, prose units, and anomaly counts for this
        document.

    Examples
    --------
    >>> from stilyagi import model
    >>> project(model.Document(syntax=model.Syntax.MARKDOWN)).regions
    ()
    >>> project(model.Document(syntax=model.Syntax.MARKDOWN)).anomaly_counts
    ()
    """
    anomalies = AnomalyTally()
    nodes, inline_spans = _node_facts(document, source_bytes, anomalies)
    regions = tuple(
        region
        for raw_region in ir_sequence(document, "regions")
        if (region := region_view(raw_region, nodes, source_bytes, anomalies))
        is not None
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
        anomaly_counts=anomaly_snapshot(anomalies),
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
        The rule's declared syntaxes, kinds, owner kinds, and required scope
            tokens.

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
    source_bytes: bytes | None,
    anomalies: AnomalyTally,
) -> tuple[dict[str, SourceSpan], list[SourceSpan]]:
    """Return the node-id index and inline-code spans in one node pass.

    A node span is kept only when it addresses the original source: it must be
    within bounds and both ends must fall between UTF-8 code points. A heading
    node's span is the only acceptable ``MD001`` span, so an IR entry that
    cannot be located is dropped here rather than diagnosed against arbitrary
    bytes.

    Returns
    -------
    tuple[dict[str, SourceSpan], list[SourceSpan]]
        Locatable node spans by id, and the locatable inline-code spans.
    """
    index: dict[str, SourceSpan] = {}
    inline: list[SourceSpan] = []
    for raw_node in ir_sequence(document, "nodes"):
        node = ir_mapping(raw_node)
        if node is None:
            anomalies["malformed_node"] += 1
            continue
        span = source_span(node.get("span"))
        if span is None or not _addresses_source(span, source_bytes):
            anomalies["invalid_node_span"] += 1
            continue
        node_id = node.get("id")
        if isinstance(node_id, str):
            index[node_id] = span
        kind = node.get("kind")
        if isinstance(kind, str) and kind in _INLINE_CODE_KINDS:
            inline.append(span)
    return index, inline


def _addresses_source(span: SourceSpan, source_bytes: bytes | None) -> bool:
    """Return whether a node span is bounded and UTF-8 aligned in the source.

    ``source_bytes`` is ``None`` for callers that project a document without
    its bytes, such as suppression resolution; bounds cannot be checked then.

    Returns
    -------
    bool
        ``True`` when the span is addressable, or when no source was supplied.
    """
    if source_bytes is None:
        return True
    return (
        span.byte_end <= len(source_bytes)
        and is_utf8_boundary(source_bytes, span.byte_start)
        and is_utf8_boundary(source_bytes, span.byte_end)
    )
