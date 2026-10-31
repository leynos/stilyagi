"""Property tests for the repetition rule's byte contract.

Two invariants are generated rather than enumerated: the reported span must
address exactly the repetition it names (V-1), and the unsafe edit must remove
only the repeated suffix while leaving every other byte alone (V-3). Both
checks are written against an independent tokenizer and byte arithmetic rather
than against the rule's own helpers, so a shared bug cannot satisfy both.
"""

import itertools
import re

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from stilyagi.model.source import SourceSpan
from stilyagi.rules.builtin.text import Token

from tests.support.rule_fixtures import LintSetup

pytest_plugins = ("tests.package_skeleton_support",)

pytestmark = pytest.mark.usefixtures("reset_extraction_state")

#: Characters where ``str.isalpha`` and the independent ``re`` oracle agree.
_WORDS = ("the", "The", "a", "é", "Ünïcode", "word")
_SEPARATORS = (" ", "\t")
#: A boundary that ends a token without creating a Markdown block.
_BOUNDARIES = (",", ".", ";", "!", "?", "-", "/", "1", "  ")

_TOKEN_PATTERN = re.compile(r"[^\W\d_]+")


@st.composite
def _prose(draw: st.DrawFn) -> str:
    """Build one paragraph of tokens separated by joinable or blocking gaps."""
    count = draw(st.integers(min_value=1, max_value=7))
    parts: list[str] = [draw(st.sampled_from(_WORDS))]
    for _ in range(count - 1):
        gap = draw(
            st.one_of(
                st.sampled_from(_SEPARATORS),
                st.sampled_from(_BOUNDARIES),
            )
        )
        parts.extend((gap, draw(st.sampled_from(_WORDS))))
    return "".join(parts) + "\n"


def _oracle_tokens(text: str) -> tuple[Token, ...]:
    """Tokenize with ``re`` instead of the rule's ``isalpha`` scan."""
    return tuple(
        Token(match.group(0), match.start(), match.end())
        for match in _TOKEN_PATTERN.finditer(text)
    )


def _expected_findings(
    text: str,
) -> tuple[tuple[Token, SourceSpan, SourceSpan], ...]:
    """Return each maximal run's second token and the whole suffix edit."""
    tokens = _oracle_tokens(text)
    found: list[tuple[Token, SourceSpan, SourceSpan]] = []
    index = 0
    while index < len(tokens) - 1:
        end = index
        while _extends_run(text, tokens, end, index):
            end += 1
        if end > index:
            found.append((
                tokens[index + 1],
                _span(text, tokens[index + 1]),
                SourceSpan(
                    _byte_offset(text, tokens[index].char_end),
                    _byte_offset(text, tokens[end].char_end),
                ),
            ))
            index = end + 1
            continue
        index += 1
    return tuple(found)


def _extends_run(
    text: str,
    tokens: tuple[Token, ...],
    end: int,
    index: int,
) -> bool:
    """Whether the token after ``end`` repeats the run's first word."""
    return (
        end + 1 < len(tokens)
        and tokens[end + 1].text == tokens[index].text
        and _joinable(text[tokens[end].char_end : tokens[end + 1].char_start])
    )


def _joinable(gap: str) -> bool:
    """Return whether a gap is made only of ASCII spaces and tabs."""
    return not gap.strip(" \t")


def _byte_offset(text: str, index: int) -> int:
    """Return the byte offset of one character index."""
    return len(text[:index].encode("utf-8"))


def _span(text: str, token: Token) -> SourceSpan:
    """Return a token's byte span in the original source."""
    return SourceSpan(
        _byte_offset(text, token.char_start),
        _byte_offset(text, token.char_end),
    )


@settings(max_examples=120, deadline=None)
@given(text=_prose())
def test_reported_spans_and_edits_match_the_oracle(text: str) -> None:
    """Every finding names the second token and removes the run's suffix."""
    source = text.encode("utf-8")
    expected = _expected_findings(text)
    result = LintSetup().run(source)

    assert len(result) == len(expected), "expected one finding per maximal repeated run"
    for diagnostic, (token, span, edit_span) in zip(result, expected, strict=True):
        assert diagnostic.span == span, (
            "expected each finding to carry the repetition's byte span"
        )
        assert source[span.byte_start : span.byte_end].decode("utf-8") == token.text, (
            "expected the span to address exactly the repeated token"
        )
        assert diagnostic.fix is not None, (
            "expected each finding to carry an unsafe edit"
        )
        (edit,) = diagnostic.fix.edits
        assert (edit.byte_start, edit.byte_end) == (
            edit_span.byte_start,
            edit_span.byte_end,
        ), "expected the edit to remove only the run's suffix"


@settings(max_examples=120, deadline=None)
@given(text=_prose())
def test_applying_the_edits_preserves_every_other_byte(text: str) -> None:
    """The spliced result keeps all bytes outside the removed suffixes."""
    source = text.encode("utf-8")
    expected = _expected_findings(text)
    edits = sorted(
        (edit for (_, _, edit_span) in expected for edit in (edit_span,)),
        key=lambda span: span.byte_start,
    )

    for earlier, later in itertools.pairwise(edits):
        assert earlier.byte_end <= later.byte_start, "edits must be disjoint"

    pieces: list[bytes] = []
    cursor = 0
    for span in edits:
        pieces.append(source[cursor : span.byte_start])
        cursor = span.byte_end
    pieces.append(source[cursor:])
    spliced = b"".join(pieces)

    assert spliced == _collapse_runs(text).encode("utf-8"), (
        "expected splicing the edits to collapse only repeated runs"
    )
    for span in edits:
        source[: span.byte_start].decode("utf-8")
        source[: span.byte_end].decode("utf-8")


def _collapse_runs(text: str) -> str:
    """Collapse every repeated run in ``text`` to its first token."""
    tokens = _oracle_tokens(text)
    pieces: list[str] = []
    cursor = 0
    index = 0
    while index < len(tokens) - 1:
        end = index
        while _extends_run(text, tokens, end, index):
            end += 1
        if end > index:
            pieces.append(text[cursor : tokens[index].char_end])
            cursor = tokens[end].char_end
            index = end + 1
            continue
        index += 1
    pieces.append(text[cursor:])
    return "".join(pieces)
