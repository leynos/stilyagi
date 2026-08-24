"""Fixture helpers that derive fix offsets from extracted source provenance."""

import typing as typ

from stilyagi.engine.ir_view import SourceSpan, iter_segments

if typ.TYPE_CHECKING:
    from stilyagi import model


class SourceTextNotFoundError(ValueError):
    """Raised when requested text has no source-backed segment provenance."""

    def __init__(self, needle: str) -> None:
        """Build an error that identifies the text missing from source segments."""
        super().__init__(f"source-backed text not found: {needle!r}")


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
        If no source-backed segment contains the requested text.

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
    for segment in iter_segments(document):
        if segment.span is None or needle not in segment.text:
            continue
        prefix = segment.text.partition(needle)[0]
        start = segment.span.byte_start + len(prefix.encode())
        return SourceSpan(start, start + len(needle.encode()))
    raise SourceTextNotFoundError(needle)
