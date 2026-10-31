"""Shared token and byte-offset helpers for the builtin text rules.

A *word* is a maximal run of characters satisfying :meth:`str.isalpha`. Digits,
underscores, apostrophes, hyphens, and combining marks are boundaries. There is
no Unicode normalization or language-aware token claim.

Rules scan one source-backed segment at a time. They never join adjacent
segments, even when their bytes touch, because a segment boundary is a markup
boundary and joining would let a repeat or a banned term cross it.
"""

import typing as typ

from stilyagi.diagnostics_location import line_column_from_offset
from stilyagi.engine import ir_view
from stilyagi.model.source import SourceSpan
from stilyagi.rules.tokens import Token, TokenizedSegment

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from stilyagi.model.region import RegionSegment, RegionView
    from stilyagi.rules.base import RuleContext

__all__ = [
    "Token",
    "TokenizedSegment",
    "alpha_tokens",
    "is_inline_code",
    "location",
    "only_blanks_between",
    "source_segments",
    "token_span",
    "tokenize_segments",
    "utf8_offsets",
]


def alpha_tokens(text: str) -> tuple[Token, ...]:
    """Return the alphabetic tokens in ``text``.

    Parameters
    ----------
    text:
        One segment's text.

    Returns
    -------
    tuple[Token, ...]
        Tokens in order, with character offsets.

    Examples
    --------
    >>> [(token.text, token.char_start, token.char_end)
    ...  for token in alpha_tokens("the the.")]
    [('the', 0, 3), ('the', 4, 7)]
    >>> [(token.text, token.char_start, token.char_end)
    ...  for token in alpha_tokens("a1 b")]
    [('a', 0, 1), ('b', 3, 4)]
    """
    tokens: list[Token] = []
    start: int | None = None
    for index, char in enumerate(text):
        if char.isalpha():
            if start is None:
                start = index
            continue
        if start is not None:
            tokens.append(Token(text[start:index], start, index))
            start = None
    if start is not None:
        tokens.append(Token(text[start:], start, len(text)))
    return tuple(tokens)


def only_blanks_between(
    text: str,
    tokens: cabc.Sequence[Token],
    first: int,
    last: int,
) -> bool:
    """Return whether every gap between ``first`` and ``last`` is blank.

    Only ASCII spaces and tabs count as blank, matching the documented
    repetition contract.

    Parameters
    ----------
    text:
        The segment text the tokens came from.
    tokens:
        Tokens in character order.
    first:
        Index of the first token in the run.
    last:
        Index of the last token in the run.

    Returns
    -------
    bool
        ``True`` when each gap is made only of spaces or tabs.

    Examples
    --------
    >>> only_blanks_between("the the", alpha_tokens("the the"), 0, 1)
    True
    >>> only_blanks_between("the,the", alpha_tokens("the,the"), 0, 1)
    False
    """
    return all(
        not text[tokens[index].char_end : tokens[index + 1].char_start].strip(" \t")
        for index in range(first, last)
    )


def utf8_offsets(text: str) -> tuple[int, ...]:
    """Return the byte offset of every character boundary in ``text``.

    Parameters
    ----------
    text:
        Segment text that has already been validated as source-backed.

    Returns
    -------
    tuple[int, ...]
        ``len(text) + 1`` cumulative UTF-8 byte offsets. The first is ``0`` and
        the last is the encoded length.

    Examples
    --------
    >>> utf8_offsets("aé")
    (0, 1, 3)
    >>> utf8_offsets("")
    (0,)
    """
    offsets = [0]
    total = 0
    for char in text:
        total += len(char.encode("utf-8"))
        offsets.append(total)
    return tuple(offsets)


def token_span(
    segment: RegionSegment,
    offsets: cabc.Sequence[int],
    token: Token,
) -> SourceSpan:
    """Map a token's character range to original source byte offsets.

    Parameters
    ----------
    segment:
        The source-backed segment the token came from.
    offsets:
        Cumulative UTF-8 offsets for the segment's text.
    token:
        The token to convert.

    Returns
    -------
    SourceSpan
        The token's byte range in the original source.

    Raises
    ------
    ValueError
        If the segment has no source span, which would make the offsets
        meaningless.

    Examples
    --------
    >>> from stilyagi.model.region import RegionSegment
    >>> segment = RegionSegment(SourceSpan(10, 13), "aé")
    >>> token_span(segment, utf8_offsets("aé"), Token("aé", 0, 2))
    SourceSpan(byte_start=10, byte_end=13)
    """
    if segment.span is None:
        message = "token spans require a source-backed segment"
        raise ValueError(message)
    base = segment.span.byte_start
    return SourceSpan(base + offsets[token.char_start], base + offsets[token.char_end])


def location(
    context: RuleContext[typ.Any],
    span: SourceSpan | None,
) -> tuple[int, int]:
    """Return the 1-based line and column for a span's start.

    Parameters
    ----------
    context:
        Rule context carrying the document's IR line index.
    span:
        The finding's byte span, or ``None`` when unknown.

    Returns
    -------
    tuple[int, int]
        The 1-based ``(line, column)`` position, or ``(1, 1)`` when unknown.
    """
    offset = span.byte_start if span is not None else None
    return line_column_from_offset(ir_view.line_index(context.document), offset)


def is_inline_code(
    segment: RegionSegment,
    inline_code_spans: cabc.Sequence[SourceSpan],
) -> bool:
    """Return whether a segment lies inside an inline-code node.

    Parameters
    ----------
    segment:
        Candidate segment.
    inline_code_spans:
        Canonical inline-code node spans.

    Returns
    -------
    bool
        ``True`` when the segment is source-backed and wholly contained in an
        inline-code span.
    """
    span = segment.span
    if span is None:
        return False
    return any(
        inline.byte_start <= span.byte_start and span.byte_end <= inline.byte_end
        for inline in inline_code_spans
    )


def source_segments(
    regions: cabc.Iterable[RegionView],
    inline_code_spans: cabc.Sequence[SourceSpan],
) -> cabc.Iterator[tuple[RegionView, RegionSegment]]:
    """Yield source-backed segments that are eligible for text matching.

    Synthetic segments have no source interval and cannot produce a byte-exact
    finding. Inline-code segments are excluded so ``STY001`` and ``TERM001``
    never report inside code spans.

    Parameters
    ----------
    regions:
        Regions already filtered by the rule's target.
    inline_code_spans:
        Canonical inline-code node spans.

    Yields
    ------
    tuple[RegionView, RegionSegment]
        Each eligible region and one of its eligible segments.
    """
    for region in regions:
        for segment in region.segments:
            if segment.span is not None and not is_inline_code(
                segment, inline_code_spans
            ):
                yield region, segment


def tokenize_segments(
    regions: cabc.Iterable[RegionView],
    inline_code_spans: cabc.Sequence[SourceSpan],
) -> tuple[TokenizedSegment, ...]:
    """Tokenize every eligible segment exactly once.

    The token list and UTF-8 prefix table are the expensive per-segment
    products the text rules share. Building them here means a document with
    both ``STY001`` and ``TERM001`` selected tokenizes each segment once rather
    than once per rule.

    Parameters
    ----------
    regions:
        Regions already filtered by the rule's target.
    inline_code_spans:
        Canonical inline-code node spans.

    Returns
    -------
    tuple[TokenizedSegment, ...]
        Eligible segments with their tokens and byte offsets, in document
        order.

    Examples
    --------
    >>> tokenize_segments((), ())
    ()
    """
    return tuple(
        TokenizedSegment(
            region=region,
            segment=segment,
            tokens=alpha_tokens(segment.text),
            offsets=utf8_offsets(segment.text),
        )
        for region, segment in source_segments(regions, inline_code_spans)
    )
