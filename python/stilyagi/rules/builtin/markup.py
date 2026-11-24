"""Conservative Markdown exclusion tests for the documentation rules.

The punctuation policy checks only plain prose. A candidate carrying inline
code, escapes, links, HTML, or emphasis markers needs a Markdown parser to
judge, and a line that begins with a structural marker is not prose at all.
These predicates answer those two questions and nothing else: they are
deliberately conservative, so a line they cannot vouch for is skipped rather
than guessed at. They never parse Markdown and never rewrite text.
"""

__all__ = ["has_excluded_markup", "starts_with_markup"]

#: Plain-summary candidates containing one of these are not checked. The set is
#: deliberately conservative: it covers inline code, escapes, links, HTML, and
#: emphasis markers, all of which need a Markdown parser to judge.
_EXCLUDED_MARKUP_CHARACTERS: frozenset[str] = frozenset('`\\[]<>*_"')

#: Line-initial markers that make a line structure rather than prose.
_LINE_MARKERS: tuple[str, ...] = ("#", ">", "-", "+", "*", "```", "~~~")

#: Characters a thematic break may repeat.
_THEMATIC_BREAK_CHARACTERS: frozenset[str] = frozenset("-_*=")

#: How many repeated characters a thematic break needs.
_MIN_THEMATIC_BREAK_LENGTH = 3


def starts_with_markup(text: str) -> bool:
    """Return whether a line begins with a Markdown structure marker.

    The test is deliberately conservative and is not a Markdown parser: a line
    it cannot vouch for is skipped by the punctuation policy rather than
    guessed at.

    Parameters
    ----------
    text:
        One physical line's text.

    Returns
    -------
    bool
        ``True`` for a heading, block quote, list marker, fence, doctest
        prompt, or thematic break after leading whitespace.

    Examples
    --------
    >>> starts_with_markup("  - item")
    True
    >>> starts_with_markup("Read records.")
    False
    >>> starts_with_markup("---")
    True
    >>> starts_with_markup("1. step")
    True
    """
    candidate = text.lstrip()
    if not candidate:
        return False
    if candidate.startswith(_LINE_MARKERS):
        return True
    if _is_ordered_list_marker(candidate):
        return True
    return _is_thematic_break(candidate)


def has_excluded_markup(text: str) -> bool:
    """Return whether a candidate contains markup this slice cannot judge.

    Parameters
    ----------
    text:
        The trimmed summary candidate.

    Returns
    -------
    bool
        ``True`` when the candidate contains a backtick, backslash, bracket,
        angle bracket, emphasis marker, or double quote.

    Examples
    --------
    >>> has_excluded_markup("Read records.")
    False
    >>> has_excluded_markup("Read `records`.")
    True
    """
    return any(character in _EXCLUDED_MARKUP_CHARACTERS for character in text)


def _is_ordered_list_marker(candidate: str) -> bool:
    """Return whether a line starts with ``digits`` then ``.`` or ``)``."""
    digits = 0
    while digits < len(candidate) and candidate[digits].isdigit():
        digits += 1
    return digits > 0 and candidate[digits : digits + 1] in {".", ")"}


def _is_thematic_break(candidate: str) -> bool:
    """Return whether a line is three or more identical break characters."""
    body = candidate.rstrip()
    return (
        len(body) >= _MIN_THEMATIC_BREAK_LENGTH
        and body[0] in _THEMATIC_BREAK_CHARACTERS
        and body.count(body[0]) == len(body)
    )
