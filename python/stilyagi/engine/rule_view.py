"""Read-only views over the canonical IR that builtin rules consume.

The flat :mod:`stilyagi.engine.ir_view` projection keeps only ``span``,
``text`` and ``synthetic_reason`` per segment. Rules additionally need region
kind, syntax, scope, heading depth, the canonical span of each region, and the
inline-code node spans that must be excluded from text matching.

The expensive per-document work lives in
:mod:`stilyagi.engine.rule_projection`; these helpers are thin adapters for
callers that hold only a document, such as tests and suppression resolution.
A caller that needs several of them at once should project once instead.
"""

import typing as typ

from stilyagi.engine.ir_mapping import ir_mapping, ir_sequence
from stilyagi.engine.rule_projection import (
    DocumentRegionView,
    project,
    select_regions,
)
from stilyagi.model.region import RegionSegment, RegionView

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from stilyagi import model
    from stilyagi.model.source import SourceSpan
    from stilyagi.rules.base import RegionTarget

__all__ = [
    "DocumentRegionView",
    "RegionSegment",
    "RegionView",
    "ignore_next_units",
    "inline_code_spans",
    "iter_regions",
    "project",
    "raw_suppressions",
    "regions_for_target",
    "select_regions",
]


def iter_regions(
    document: model.Document,
    *,
    source_bytes: bytes | None = None,
) -> cabc.Iterator[RegionView]:
    """Yield every well-formed region in document order.

    Parameters
    ----------
    document:
        Extracted document whose IR may carry regions.
    source_bytes:
        Original file bytes. When supplied, a segment's advertised span is
        kept only if that slice decodes to exactly the segment text, so a
        stale or malformed span can never produce a byte-exact finding.

    Yields
    ------
    RegionView
        Regions carrying the minimum structural facts the rules need.

    Examples
    --------
    >>> from stilyagi import model
    >>> list(iter_regions(model.Document(syntax=model.Syntax.MARKDOWN)))
    []
    """
    yield from project(document, source_bytes=source_bytes).regions


def regions_for_target(
    document: model.Document,
    target: RegionTarget,
    *,
    source_bytes: bytes | None = None,
) -> tuple[RegionView, ...]:
    """Return the regions one rule target claims, in document order.

    Parameters
    ----------
    document:
        Extracted document whose IR carries the regions.
    target:
        The rule's declared syntax, kinds, and required scope tokens.
    source_bytes:
        Original file bytes used to verify source-backed segments.

    Returns
    -------
    tuple[RegionView, ...]
        Regions that satisfy every part of the target.

    Examples
    --------
    >>> from stilyagi import model
    >>> from stilyagi.rules.base import RegionTarget
    >>> regions_for_target(
    ...     model.Document(syntax=model.Syntax.MARKDOWN),
    ...     RegionTarget(kinds=("heading",)),
    ... )
    ()
    """
    return select_regions(iter_regions(document, source_bytes=source_bytes), target)


def ignore_next_units(document: model.Document) -> tuple[SourceSpan, ...]:
    """Return the prose units an ``ignore-next`` directive may consume.

    Headings, paragraphs, and table cells are units. Thin list and blockquote
    containers are skipped, and a nested paragraph remains its own unit. An
    empty region is skipped because ``ignore-next`` consumes the next unit that
    actually carries prose.

    Parameters
    ----------
    document:
        Extracted document whose regions should be considered.

    Returns
    -------
    tuple[SourceSpan, ...]
        Nonempty eligible unit spans in canonical source order.

    Examples
    --------
    >>> from stilyagi import model
    >>> ignore_next_units(model.Document(syntax=model.Syntax.MARKDOWN))
    ()
    """
    return project(document).prose_units


def inline_code_spans(document: model.Document) -> tuple[SourceSpan, ...]:
    """Return canonical IR node spans whose kind marks inline code.

    ``region.segments[].node`` records the owning region node, so it cannot
    identify inline-code leaves. The canonical ``nodes`` array can: each node
    carries its own ``kind`` and ``span``.

    Parameters
    ----------
    document:
        Extracted document whose IR may carry canonical nodes.

    Returns
    -------
    tuple[SourceSpan, ...]
        Sorted inline-code spans, merging touching ranges.

    Examples
    --------
    >>> from stilyagi import model
    >>> inline_code_spans(model.Document(syntax=model.Syntax.MARKDOWN))
    ()
    """
    return project(document).inline_code_spans


def raw_suppressions(
    document: model.Document,
) -> tuple[cabc.Mapping[str, object], ...]:
    """Return well-formed raw suppression mappings from the IR envelope.

    Parameters
    ----------
    document:
        Extracted document whose IR may carry suppression entries.

    Returns
    -------
    tuple[collections.abc.Mapping[str, object], ...]
        Suppression mappings in IR order.

    Examples
    --------
    >>> from stilyagi import model
    >>> raw_suppressions(model.Document(syntax=model.Syntax.MARKDOWN))
    ()
    """
    mappings: list[cabc.Mapping[str, object]] = []
    for raw in ir_sequence(document, "suppressions"):
        mapping = ir_mapping(raw)
        if mapping is not None:
            mappings.append(mapping)
    return tuple(mappings)
