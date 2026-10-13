"""Fixture helpers that derive fix offsets from extracted source provenance."""

import typing as typ

from stilyagi.engine import ir_view
from stilyagi.engine.ir_view import SourceSpan, iter_segments

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from stilyagi import model


class SourceTextNotFoundError(ValueError):
    """Raised when requested text has no source-backed segment provenance."""

    def __init__(self, needle: str) -> None:
        """Build an error that identifies the text missing from source segments."""
        super().__init__(f"source-backed text not found: {needle!r}")


class NoUnclaimedByteError(ValueError):
    """Raised when a document offers no byte range for a synthetic span."""

    def __init__(self, *, claims_nothing: bool) -> None:
        """Build an error naming which property of the document failed."""
        detail = (
            "the document has no source-backed spans"
            if claims_nothing
            else "every byte of the source is source-backed"
        )
        super().__init__(f"no unclaimed byte available: {detail}")


def find_source_span(document: model.Document, needle: str) -> SourceSpan:
    """Return the byte span of one unique needle inside a source-backed segment.

    Parameters
    ----------
    document:
        Extracted document containing source-backed segment provenance.
    needle:
        Text to locate within exactly one source-backed segment.

    Returns
    -------
    stilyagi.engine.ir_view.SourceSpan
        The original-source byte range occupied by ``needle``.

    Raises
    ------
    SourceTextNotFoundError
        If the source-backed segments do not contain the requested text
        exactly once.

    Examples
    --------
    >>> from stilyagi import model
    >>> document = model.Document(
    ...     model.Syntax.MARKDOWN,
    ...     ir={"regions": [{"segments": [{"text": "word", "source": {
    ...         "byte_start": 0, "byte_end": 4}}]}]},
    ... )
    >>> find_source_span(document, "word")
    SourceSpan(byte_start=0, byte_end=4)
    """
    matches: list[SourceSpan] = []
    needle_width = len(needle.encode())
    for segment in iter_segments(document):
        if segment.span is None:
            continue
        offset = segment.text.find(needle)
        while offset != -1:
            start = segment.span.byte_start + len(segment.text[:offset].encode())
            matches.append(SourceSpan(start, start + needle_width))
            offset = segment.text.find(needle, offset + len(needle))
    if len(matches) != 1:
        raise SourceTextNotFoundError(needle)
    return matches[0]


def find_unclaimed_span(document: model.Document) -> SourceSpan:
    """Return a one-byte range that no source-backed span claims.

    A synthetic span cannot be invented: it has to be a real offset the IR
    genuinely does not cover, or the admissibility check accepts it and the
    scenario passes for the wrong reason. The gap between two source-backed
    spans -- the soft line break the extractor normalised away -- is exactly
    such a range, so it is found by measuring rather than by guessing an offset.

    The search is bounded by the furthest byte the IR does claim, so the result
    is always a byte the extractor *looked past* rather than one beyond the end
    of everything it produced.

    Parameters
    ----------
    document:
        Extracted document containing source-backed segment provenance.

    Returns
    -------
    stilyagi.engine.ir_view.SourceSpan
        A one-byte range that no merged source-backed span contains.

    Raises
    ------
    NoUnclaimedByteError
        If the document claims no source bytes at all, or claims every byte up
        to its own extent, in which case the scenario's premise does not hold.
    """
    claimed = tuple(ir_view.source_backed_spans(document))
    if not claimed:
        raise NoUnclaimedByteError(claims_nothing=True)
    for offset in range(_claimed_extent(claimed)):
        if not _is_claimed(claimed, offset):
            return SourceSpan(offset, offset + 1)
    raise NoUnclaimedByteError(claims_nothing=False)


def _claimed_extent(claimed: cabc.Sequence[SourceSpan]) -> int:
    """Return the furthest byte the claimed spans reach."""
    return max(span.byte_end for span in claimed)


def _is_claimed(claimed: cabc.Sequence[SourceSpan], offset: int) -> bool:
    """Report whether any claimed span covers the byte at ``offset``."""
    return any(
        span.byte_start <= offset and offset + 1 <= span.byte_end for span in claimed
    )
