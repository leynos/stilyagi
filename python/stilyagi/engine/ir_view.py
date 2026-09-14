"""Provide a typed, read-only view over the extractor's IR mapping."""

import collections.abc as cabc
import dataclasses as dc
import typing as typ

if typ.TYPE_CHECKING:
    from stilyagi import model


@dc.dataclass(frozen=True, slots=True, order=True)
class SourceSpan:
    """A half-open UTF-8 byte range in the original source.

    Examples
    --------
    >>> SourceSpan(3, 8)
    SourceSpan(byte_start=3, byte_end=8)
    """

    byte_start: int
    byte_end: int


@dc.dataclass(frozen=True, slots=True)
class SegmentView:
    """One IR segment with source provenance when the extractor provides it.

    Examples
    --------
    >>> SegmentView(SourceSpan(0, 4), "Text", None).span
    SourceSpan(byte_start=0, byte_end=4)
    """

    span: SourceSpan | None
    text: str
    synthetic_reason: str | None


def iter_segments(document: model.Document) -> cabc.Iterator[SegmentView]:
    """Yield well-formed segments from every IR region in document order.

    Parameters
    ----------
    document:
        Extracted document whose IR may carry region segments.

    Yields
    ------
    SegmentView
        Source-backed or synthetic segments that can be interpreted safely.
    """
    raw_regions = _ir_sequence(document, "regions")
    for raw_region in raw_regions:
        yield from _region_segments(raw_region)


def source_backed_spans(document: model.Document) -> tuple[SourceSpan, ...]:
    """Return sorted source-backed spans, merging touching ranges.

    Parameters
    ----------
    document:
        Extracted document whose segment provenance should be collected.

    Returns
    -------
    tuple[SourceSpan, ...]
        Disjoint source ranges suitable for later containment checks.
    """
    spans = sorted(
        segment.span for segment in iter_segments(document) if segment.span is not None
    )
    return _merge_touching_spans(spans)


def segment_for_span(
    document: model.Document,
    span: SourceSpan,
) -> SegmentView | None:
    """Return the source-backed segment that wholly contains a span.

    Parameters
    ----------
    document:
        Extracted document whose segment provenance should be inspected.
    span:
        Candidate byte span.

    Returns
    -------
    SegmentView | None
        The containing source-backed segment, or ``None`` when absent.
    """
    return next(
        (
            segment
            for segment in iter_segments(document)
            if segment.span is not None
            and segment.span.byte_start <= span.byte_start
            and span.byte_end <= segment.span.byte_end
        ),
        None,
    )


def line_index(document: model.Document) -> tuple[int, ...] | None:
    """Return a valid IR line index, or ``None`` when the IR omits one.

    Parameters
    ----------
    document:
        Extracted document whose IR may carry line-start byte offsets.

    Returns
    -------
    tuple[int, ...] | None
        Typed line-start offsets, or ``None`` for malformed input.
    """
    raw_line_index = _ir_value(document, "line_index")
    if not _is_sequence(raw_line_index):
        return None
    values = typ.cast("cabc.Sequence[object]", raw_line_index)
    if not all(isinstance(start, int) for start in values):
        return None
    return tuple(typ.cast("int", start) for start in values)


def byte_start_from_span(span: object) -> int | None:
    """Return a span mapping's byte start when the IR provides one.

    Parameters
    ----------
    span:
        Untyped IR span candidate.

    Returns
    -------
    int | None
        The byte start when it is an integer, otherwise ``None``.
    """
    if not isinstance(span, cabc.Mapping):
        return None
    typed_span = typ.cast("cabc.Mapping[str, object]", span)
    byte_start = typed_span.get("byte_start")
    return byte_start if isinstance(byte_start, int) else None


def _ir_sequence(document: model.Document, key: str) -> cabc.Sequence[object]:
    """Return one sequence-valued IR field, or an empty sequence."""
    value = _ir_value(document, key)
    return typ.cast("cabc.Sequence[object]", value) if _is_sequence(value) else ()


def _ir_value(document: model.Document, key: str) -> object:
    """Return one raw IR field when an IR envelope is available."""
    return document.ir.get(key) if document.ir is not None else None


def _is_sequence(value: object) -> bool:
    """Return whether a value is a non-text sequence."""
    return isinstance(value, cabc.Sequence) and not isinstance(value, (str, bytes))


def _region_segments(raw_region: object) -> cabc.Iterator[SegmentView]:
    """Yield well-formed segment views from one raw region mapping."""
    if not isinstance(raw_region, cabc.Mapping):
        return
    typed_region = typ.cast("cabc.Mapping[str, object]", raw_region)
    raw_segments = typed_region.get("segments")
    if not _is_sequence(raw_segments):
        return
    for raw_segment in typ.cast("cabc.Sequence[object]", raw_segments):
        segment = _segment_view(raw_segment)
        if segment is not None:
            yield segment


def _segment_view(raw_segment: object) -> SegmentView | None:
    """Convert one raw segment mapping into a safe typed view."""
    if not isinstance(raw_segment, cabc.Mapping):
        return None
    typed_segment = typ.cast("cabc.Mapping[str, object]", raw_segment)
    text = typed_segment.get("text")
    if not isinstance(text, str):
        return None
    source = typed_segment.get("source")
    if source is None:
        synthetic = typed_segment.get("synthetic")
        return SegmentView(
            None, text, synthetic if isinstance(synthetic, str) else None
        )
    span = _source_span(source)
    return SegmentView(span, text, None) if span is not None else None


def _source_span(source: object) -> SourceSpan | None:
    """Return a well-ordered source span from one raw source mapping."""
    if not isinstance(source, cabc.Mapping):
        return None
    typed_source = typ.cast("cabc.Mapping[str, object]", source)
    byte_start = typed_source.get("byte_start")
    byte_end = typed_source.get("byte_end")
    if not isinstance(byte_start, int) or not isinstance(byte_end, int):
        return None
    return SourceSpan(byte_start, byte_end) if byte_start <= byte_end else None


def _merge_touching_spans(spans: list[SourceSpan]) -> tuple[SourceSpan, ...]:
    """Merge sorted overlapping or touching source spans."""
    merged: list[SourceSpan] = []
    for span in spans:
        if not merged or merged[-1].byte_end < span.byte_start:
            merged.append(span)
            continue
        previous = merged.pop()
        merged.append(
            SourceSpan(previous.byte_start, max(previous.byte_end, span.byte_end))
        )
    return tuple(merged)
