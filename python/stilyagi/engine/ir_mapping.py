"""Safe, typed access to the extractor's untyped IR envelope.

The IR is a plain mapping whose shape is owned by Rust. Every Python consumer
must tolerate a missing envelope, malformed fields, and non-mapping entries
without raising, because the extractor is allowed to evolve. These helpers are
the single place that tolerance lives, so it is written and tested once rather
than re-derived by each projection.
"""

import collections.abc as cabc
import typing as typ

from stilyagi.model.source import SourceSpan

if typ.TYPE_CHECKING:
    from stilyagi import model

__all__ = [
    "ir_mapping",
    "ir_sequence",
    "ir_value",
    "is_sequence",
    "merge_touching_spans",
    "segment_with_text",
    "source_span",
    "span_fields",
    "string_tuple",
]


def ir_value(document: model.Document, key: str) -> object:
    """Return one raw IR field when an envelope is available.

    Parameters
    ----------
    document:
        Extracted document whose IR envelope may carry ``key``.
    key:
        IR field name, for example ``"regions"``.

    Returns
    -------
    object
        The raw field value, or ``None`` when the envelope or field is absent.

    Examples
    --------
    >>> from stilyagi import model
    >>> ir_value(model.Document(syntax=model.Syntax.MARKDOWN), "regions") is None
    True
    """
    return document.ir.get(key) if document.ir is not None else None


def ir_sequence(document: model.Document, key: str) -> cabc.Sequence[object]:
    """Return one sequence-valued IR field, or an empty sequence.

    Parameters
    ----------
    document:
        Extracted document whose IR envelope may carry ``key``.
    key:
        IR field name, for example ``"nodes"``.

    Returns
    -------
    collections.abc.Sequence[object]
        The field when it is a non-text sequence, otherwise ``()``.

    Examples
    --------
    >>> from stilyagi import model
    >>> ir_sequence(model.Document(syntax=model.Syntax.MARKDOWN), "nodes")
    ()
    """
    value = ir_value(document, key)
    return typ.cast("cabc.Sequence[object]", value) if is_sequence(value) else ()


def is_sequence(value: object) -> bool:
    """Return whether a value is a non-text sequence.

    Parameters
    ----------
    value:
        Untyped IR value.

    Returns
    -------
    bool
        ``True`` for lists, tuples, and other non-string sequences.

    Examples
    --------
    >>> is_sequence(["a"])
    True
    >>> is_sequence("a")
    False
    """
    return isinstance(value, cabc.Sequence) and not isinstance(value, (str, bytes))


def ir_mapping(value: object) -> cabc.Mapping[str, object] | None:
    """Narrow one untyped IR value to a string-keyed mapping, or ``None``.

    Parameters
    ----------
    value:
        An untyped value lifted out of the IR envelope.

    Returns
    -------
    collections.abc.Mapping[str, object] | None
        The value as a mapping when it is one, otherwise ``None``.

    Examples
    --------
    >>> ir_mapping({"kind": "heading"})
    {'kind': 'heading'}
    >>> ir_mapping("heading") is None
    True
    """
    if not isinstance(value, cabc.Mapping):
        return None
    return typ.cast("cabc.Mapping[str, object]", value)


def string_tuple(value: object) -> tuple[str, ...]:
    """Return the string members of a sequence-valued IR field.

    Parameters
    ----------
    value:
        Untyped IR value, normally a list of names or codes.

    Returns
    -------
    tuple[str, ...]
        Every string member in order. Non-string members are dropped, because
        the extractor may add fields this version does not model, and ``()`` is
        returned when ``value`` is not a non-text sequence.

    Examples
    --------
    >>> string_tuple(["alpha", 1, "beta"])
    ('alpha', 'beta')
    >>> string_tuple("alpha")
    ()
    """
    if not is_sequence(value):
        return ()
    values = typ.cast("cabc.Sequence[object]", value)
    return tuple(item for item in values if isinstance(item, str))


def segment_with_text(
    raw_segment: object,
) -> tuple[cabc.Mapping[str, object], str] | None:
    """Return one raw segment mapping together with its validated text.

    Parameters
    ----------
    raw_segment:
        Untyped element of a region's ``segments`` sequence.

    Returns
    -------
    tuple[collections.abc.Mapping[str, object], str] | None
        The mapping and its ``text`` field when the element is a mapping with
        string text, otherwise ``None``.

    Examples
    --------
    >>> mapping, text = segment_with_text({"text": "hello"})
    >>> text
    'hello'
    >>> segment_with_text({"text": 3}) is None
    True
    """
    segment = ir_mapping(raw_segment)
    if segment is None:
        return None
    text = segment.get("text")
    if not isinstance(text, str):
        return None
    return segment, text


def span_fields(value: object) -> tuple[int, int] | None:
    """Return the integer byte offsets of a raw IR span mapping.

    Parameters
    ----------
    value:
        Untyped IR span candidate, normally ``{"byte_start", "byte_end"}``.

    Returns
    -------
    tuple[int, int] | None
        The two offsets when the candidate is a mapping and both are integers,
        otherwise ``None``. Ordering is deliberately left to the caller: a
        reversed span is absent to ``source_span`` but malformed to
        suppression resolution, and each reports that difference its own way.

    Examples
    --------
    >>> span_fields({"byte_start": 1, "byte_end": 4})
    (1, 4)
    >>> span_fields({"byte_start": "1", "byte_end": 4}) is None
    True
    """
    typed = ir_mapping(value)
    if typed is None:
        return None
    start = typed.get("byte_start")
    end = typed.get("byte_end")
    if not isinstance(start, int) or not isinstance(end, int):
        return None
    return start, end


def source_span(source: object) -> SourceSpan | None:
    """Return a well-ordered source span from one raw source mapping.

    Parameters
    ----------
    source:
        Untyped IR span candidate, normally ``{"byte_start", "byte_end"}``.

    Returns
    -------
    SourceSpan | None
        The span when both offsets are integers, non-negative, and ordered,
        otherwise ``None``. A malformed span is absent rather than raising, so
        one corrupt IR entry cannot abort a whole run.

    Examples
    --------
    >>> source_span({"byte_start": 1, "byte_end": 4})
    SourceSpan(byte_start=1, byte_end=4)
    >>> source_span({"byte_start": 4, "byte_end": 1}) is None
    True
    >>> source_span({"byte_start": -1, "byte_end": 4}) is None
    True
    """
    fields = span_fields(source)
    if fields is None:
        return None
    byte_start, byte_end = fields
    if byte_start < 0 or byte_end < byte_start:
        return None
    return SourceSpan(byte_start, byte_end)


def merge_touching_spans(spans: list[SourceSpan]) -> tuple[SourceSpan, ...]:
    """Merge sorted overlapping or touching source spans.

    Parameters
    ----------
    spans:
        Source spans sorted by ``byte_start``.

    Returns
    -------
    tuple[SourceSpan, ...]
        Disjoint spans covering the same bytes.

    Examples
    --------
    >>> merge_touching_spans([SourceSpan(0, 2), SourceSpan(2, 4)])
    (SourceSpan(byte_start=0, byte_end=4),)
    >>> merge_touching_spans([SourceSpan(0, 2), SourceSpan(3, 4)])
    (SourceSpan(byte_start=0, byte_end=2), SourceSpan(byte_start=3, byte_end=4))
    """
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
