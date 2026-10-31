"""Property tests for the repetition rule's byte contract.

Two invariants are generated rather than enumerated: the reported span must
address exactly the repetition it names (V-1), and the unsafe edit must remove
only the repeated suffix while leaving every other byte alone (V-3). Both
checks are written against an independent tokenizer and byte arithmetic rather
than against the rule's own helpers, so a shared bug cannot satisfy both.

The preservation check splices the rule's production edits and compares the
result with an independently collapsed paragraph. A mutation control then
shifts one edit boundary one byte into a multi-byte code point and requires the
fix planner to refuse it, so a planner that silently accepted every range
would fail rather than pass.
"""

import itertools
import re
import typing as typ

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from stilyagi import diagnostics, engine, model
from stilyagi.engine.fix_planning import admissibility
from stilyagi.fixes import TextEdit
from stilyagi.model.source import SourceSpan
from stilyagi.rules.builtin.text import Token

from tests.support.rule_fixtures import LintSetup

if typ.TYPE_CHECKING:
    import collections.abc as cabc

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
    """Splicing the rule's own edits collapses only the repeated runs."""
    source = text.encode("utf-8")
    result = LintSetup().run(source)
    spans = _production_edit_spans(result)
    edits = sorted(spans, key=lambda span: span.byte_start)

    for earlier, later in itertools.pairwise(edits):
        assert earlier.byte_end <= later.byte_start, "edits must be disjoint"

    assert _splice(source, edits) == _collapse_runs(text).encode("utf-8"), (
        "expected splicing the rule's edits to collapse only repeated runs"
    )
    for span in edits:
        source[: span.byte_start].decode("utf-8")
        source[: span.byte_end].decode("utf-8")


_MULTIBYTE_SOURCES = (
    "é é\n",
    "Ünïcode Ünïcode é é\n",
    "the thé thé\n",
    "a é é\n",
)


@pytest.mark.parametrize("text", _MULTIBYTE_SOURCES)
def test_a_boundary_shifted_into_a_continuation_byte_is_rejected(text: str) -> None:
    """The mutation control: a one-byte shift into a code point is refused."""
    source = text.encode("utf-8")
    document = engine.extract_document(text, model.Syntax.MARKDOWN)
    result = LintSetup().run(source)
    assert result, "expected the fixture to produce an edit"

    mutations = 0
    for diagnostic in result:
        assert diagnostic.fix is not None, "expected each finding to carry a fix"
        (edit,) = diagnostic.fix.edits
        assert admissibility.classify_edit(edit, source, document, "STY001") is None, (
            "expected the rule's own edit to be admissible"
        )
        mutated = _continuation_shift(edit, source)
        if mutated is None:
            continue
        mutations += 1
        rejection = admissibility.classify_edit(mutated, source, document, "STY001")
        assert rejection is not None, "expected the shifted edit to be refused"
        assert rejection.identifier == "fix-error/non-utf8-boundary", (
            "expected the refusal to name the UTF-8 boundary"
        )
    assert mutations, "expected at least one shift into a continuation byte"


def _production_edit_spans(
    result: cabc.Sequence[diagnostics.Diagnostic],
) -> list[SourceSpan]:
    """Return each finding's edit as a source span, in diagnostic order."""
    spans: list[SourceSpan] = []
    for diagnostic in result:
        assert diagnostic.fix is not None, "expected each finding to carry a fix"
        spans.extend(
            SourceSpan(edit.byte_start, edit.byte_end) for edit in diagnostic.fix.edits
        )
    return spans


def _splice(source: bytes, spans: cabc.Iterable[SourceSpan]) -> bytes:
    """Return ``source`` with every span's bytes removed."""
    pieces: list[bytes] = []
    cursor = 0
    for span in spans:
        pieces.append(source[cursor : span.byte_start])
        cursor = span.byte_end
    pieces.append(source[cursor:])
    return b"".join(pieces)


def _continuation_shift(edit: TextEdit, source: bytes) -> TextEdit | None:
    """Return the edit with its end moved one byte into a code point, if any.

    A ``STY001`` edit starts where a token ends, and a run's tokens are joined
    only by spaces or tabs, so its start is always a character boundary. Only
    the end can fall inside a multi-byte code point.

    Returns
    -------
    TextEdit | None
        The shifted edit, or ``None`` when the end is already a boundary.
    """
    if edit.byte_end > 0 and _is_continuation_byte(source[edit.byte_end - 1]):
        return TextEdit(edit.byte_start, edit.byte_end - 1, edit.replacement)
    return None


#: The two high bits identify a UTF-8 lead byte; ``10`` marks a continuation.
_HIGH_BITS_MASK = 0b1100_0000
_CONTINUATION_PREFIX = 0b1000_0000


def _is_continuation_byte(value: int) -> bool:
    """Return whether ``value`` continues a multi-byte code point."""
    return value & _HIGH_BITS_MASK == _CONTINUATION_PREFIX


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
