"""An independent oracle for the adjacent-repeated-word contract.

The oracle tokenizes with :mod:`re` and does its own byte arithmetic, so it
shares no code with the rule's ``str.isalpha`` scan or its UTF-8 prefix table.
A bug in either implementation cannot satisfy both.

The property tests use it to state what a maximal run is, which token a finding
must name, and which bytes an edit must remove.
"""

import re

from stilyagi.model.source import SourceSpan
from stilyagi.rules.builtin.text import Token

__all__ = [
    "byte_offset",
    "collapse_runs",
    "expected_findings",
    "extends_run",
    "joinable",
    "oracle_tokens",
    "span_for",
]

#: Tokens matched by the independent ``re`` oracle. The pattern accepts every
#: Unicode letter, including characters such as ``²``, ``½`` and ``Ⅷ`` that
#: ``str.isalpha`` rejects, so the two matchers deliberately do not agree.
TOKEN_PATTERN = re.compile(r"[^\W\d_]+")


def oracle_tokens(text: str) -> tuple[Token, ...]:
    """Tokenize with ``re`` instead of the rule's ``isalpha`` scan."""
    return tuple(
        Token(match.group(0), match.start(), match.end())
        for match in TOKEN_PATTERN.finditer(text)
    )


def expected_findings(
    text: str,
) -> tuple[tuple[Token, SourceSpan, SourceSpan], ...]:
    """Return each maximal run's second token and the whole suffix edit."""
    tokens = oracle_tokens(text)
    found: list[tuple[Token, SourceSpan, SourceSpan]] = []
    index = 0
    while index < len(tokens) - 1:
        end = index
        while extends_run(text, tokens, end, index):
            end += 1
        if end > index:
            found.append((
                tokens[index + 1],
                span_for(text, tokens[index + 1]),
                SourceSpan(
                    byte_offset(text, tokens[index].char_end),
                    byte_offset(text, tokens[end].char_end),
                ),
            ))
            index = end + 1
            continue
        index += 1
    return tuple(found)


def extends_run(
    text: str,
    tokens: tuple[Token, ...],
    end: int,
    index: int,
) -> bool:
    """Whether the token after ``end`` repeats the run's first word."""
    return (
        end + 1 < len(tokens)
        and tokens[end + 1].text == tokens[index].text
        and joinable(text[tokens[end].char_end : tokens[end + 1].char_start])
    )


def joinable(gap: str) -> bool:
    """Return whether a gap is made only of ASCII spaces and tabs."""
    return not gap.strip(" \t")


def byte_offset(text: str, index: int) -> int:
    """Return the byte offset of one character index."""
    return len(text[:index].encode("utf-8"))


def span_for(text: str, token: Token) -> SourceSpan:
    """Return a token's byte span in the original source."""
    return SourceSpan(
        byte_offset(text, token.char_start),
        byte_offset(text, token.char_end),
    )


def collapse_runs(text: str) -> str:
    """Collapse every repeated run in ``text`` to its first token."""
    tokens = oracle_tokens(text)
    pieces: list[str] = []
    cursor = 0
    index = 0
    while index < len(tokens) - 1:
        end = index
        while extends_run(text, tokens, end, index):
            end += 1
        if end > index:
            pieces.append(text[cursor : tokens[index].char_end])
            cursor = tokens[end].char_end
            index = end + 1
            continue
        index += 1
    pieces.append(text[cursor:])
    return "".join(pieces)
