"""Token models shared by the text rules and the rule context.

These records describe one segment's tokenization. They live outside both
:mod:`stilyagi.rules.base` and :mod:`stilyagi.rules.builtin.text` so the rule
context can declare that it carries tokenized segments without importing the
builtin package, which imports the context in turn.
"""

import dataclasses as dc
import typing as typ

if typ.TYPE_CHECKING:
    from stilyagi.model.region import RegionSegment, RegionView

__all__ = [
    "Token",
    "TokenizedSegment",
]


@dc.dataclass(frozen=True, slots=True)
class Token:
    """One alphabetic token with character offsets inside its segment.

    Parameters
    ----------
    text:
        The token's original spelling.
    char_start:
        Inclusive character index in the segment text.
    char_end:
        Exclusive character index in the segment text.

    Examples
    --------
    >>> Token("the", 0, 3).text
    'the'
    """

    text: str
    char_start: int
    char_end: int


@dc.dataclass(frozen=True, slots=True)
class TokenizedSegment:
    """One source-backed segment tokenized once for every text rule.

    Parameters
    ----------
    region:
        The region that owns the segment.
    segment:
        The source-backed segment whose text was tokenized.
    tokens:
        Alphabetic tokens in character order.
    offsets:
        Cumulative UTF-8 byte offsets for the segment text, so a token's
        character indices can be converted without re-encoding per finding.

    Examples
    --------
    >>> from stilyagi.model.region import RegionSegment, RegionView
    >>> from stilyagi.model.source import SourceSpan
    >>> item = TokenizedSegment(
    ...     RegionView("r0", "paragraph", "markdown", (), {}, ()),
    ...     RegionSegment(SourceSpan(0, 3), "the"),
    ...     (Token("the", 0, 3),),
    ...     (0, 3),
    ... )
    >>> item.tokens[0].text
    'the'
    """

    region: RegionView
    segment: RegionSegment
    tokens: tuple[Token, ...]
    offsets: tuple[int, ...]
