"""Property tests for the builtin pack's byte contracts.

Two invariants are generated rather than enumerated: the reported span must
address exactly the repetition it names (V-1), and the unsafe edit must remove
only the repeated suffix while leaving every other byte alone (V-3). Both
checks are written against an independent tokenizer and byte arithmetic rather
than against the rule's own helpers, so a shared bug cannot satisfy both.

A third invariant covers the segment boundary: a run is found inside one
source-backed segment, and never across the markup that separates two of them.
The inline-code index's own containment property lives in
`tests/test_inline_code_index.py`.

The preservation check splices the rule's production edits and compares the
result with an independently collapsed paragraph. A mutation control then
shifts one edit boundary one byte into a multi-byte code point and requires the
fix planner to refuse it, so a planner that silently accepted every range
would fail rather than pass.
"""

import itertools
import typing as typ

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from stilyagi import diagnostics, engine, model
from stilyagi.engine.fix_planning import admissibility
from stilyagi.fixes import TextEdit
from stilyagi.model.source import SourceSpan

from tests.support.rule_fixtures import LintSetup
from tests.support.word_run_oracle import collapse_runs, expected_findings

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from stilyagi.rules.builtin.text import Token

pytest_plugins = ("tests.package_skeleton_support",)

pytestmark = pytest.mark.usefixtures("reset_extraction_state")

#: Characters where ``str.isalpha`` and the independent ``re`` oracle agree.
_WORDS = ("the", "The", "a", "é", "Ünïcode", "word")
_SEPARATORS = (" ", "\t")
#: A boundary that ends a token without creating a Markdown block.
_BOUNDARIES = (",", ".", ";", "!", "?", "-", "/", "1", "  ")


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


@settings(max_examples=120, deadline=None)
@given(text=_prose())
def test_reported_spans_and_edits_match_the_oracle(text: str) -> None:
    """Every finding names the second token and removes the run's suffix."""
    source = text.encode("utf-8")
    expected = expected_findings(text)
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
    """Applying the rule's own edits collapses only the repeated runs."""
    source = text.encode("utf-8")
    result = LintSetup().run(source)
    edits = sorted(_production_edits(result), key=lambda edit: edit.byte_start)

    for earlier, later in itertools.pairwise(edits):
        assert earlier.byte_end <= later.byte_start, "edits must be disjoint"

    assert _apply_edits(source, edits) == collapse_runs(text).encode("utf-8"), (
        "expected applying the rule's edits to collapse only repeated runs"
    )
    for edit in edits:
        source[: edit.byte_start].decode("utf-8")
        source[: edit.byte_end].decode("utf-8")


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


def _production_edits(
    result: cabc.Sequence[diagnostics.Diagnostic],
) -> list[TextEdit]:
    """Return each finding's edits, replacements included, in diagnostic order."""
    edits: list[TextEdit] = []
    for diagnostic in result:
        assert diagnostic.fix is not None, "expected each finding to carry a fix"
        edits.extend(diagnostic.fix.edits)
    return edits


def _apply_edits(source: bytes, edits: cabc.Iterable[TextEdit]) -> bytes:
    """Return ``source`` with every edit's replacement applied in order."""
    pieces: list[bytes] = []
    cursor = 0
    for edit in edits:
        pieces.extend((
            source[cursor : edit.byte_start],
            edit.replacement.encode("utf-8"),
        ))
        cursor = edit.byte_end
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


#: A small vocabulary makes a repeat across a segment boundary likely.
_SEGMENT_WORDS = ("the", "é", "Ünïcode", "a")


@st.composite
def _segment_pieces(draw: st.DrawFn) -> tuple[tuple[bool, str], ...]:
    """Build alternating plain and emphasized pieces of one paragraph.

    Alternating keeps every plain piece whole: two adjacent plain pieces would
    merge into one projected segment and make the oracle's bookkeeping wrong.

    Returns
    -------
    tuple[tuple[bool, str], ...]
        One ``(is_emphasized, text)`` pair per piece, in source order.
    """
    count = draw(st.integers(min_value=2, max_value=5))
    starts_emphasized = draw(st.booleans())
    pieces: list[tuple[bool, str]] = []
    for index in range(count):
        token_count = draw(st.integers(min_value=1, max_value=3))
        text = " ".join(
            draw(st.sampled_from(_SEGMENT_WORDS)) for _ in range(token_count)
        )
        is_emphasized = starts_emphasized == (index % 2 == 0)
        pieces.append((is_emphasized, text))
    return tuple(pieces)


def _render_segments(
    pieces: tuple[tuple[bool, str], ...],
) -> tuple[str, tuple[tuple[str, int], ...]]:
    """Render the paragraph and return each segment's text and byte start.

    The offsets are derived from the generator that built the source, not from
    the projection under test. A plain piece keeps the separator spaces the
    projection attaches to it: the one after the preceding emphasis, and the
    one before the following emphasis.

    Returns
    -------
    tuple[str, tuple[tuple[str, int], ...]]
        The paragraph with its newline, and each segment's text with the byte
        offset it starts at.
    """
    source = ""
    segments: list[tuple[str, int]] = []
    for index, (is_emphasized, text) in enumerate(pieces):
        follows_emphasis = index > 0 and pieces[index - 1][0] and not is_emphasized
        if follows_emphasis:
            source += " "
        if is_emphasized:
            source += "*"
            segments.append((text, len(source.encode("utf-8"))))
            source += f"{text}*"
            continue
        start = len(source.encode("utf-8")) - (1 if follows_emphasis else 0)
        segment_text = f"{' ' if follows_emphasis else ''}{text}"
        source += text
        if index + 1 < len(pieces) and pieces[index + 1][0]:
            source += " "
            segment_text += " "
        segments.append((segment_text, start))
    return f"{source}\n", tuple(segments)


def _shifted_findings(
    text: str,
    base: int,
) -> tuple[tuple[Token, SourceSpan, SourceSpan], ...]:
    """Return one segment's expected findings shifted into source offsets."""
    return tuple(
        (
            token,
            SourceSpan(span.byte_start + base, span.byte_end + base),
            SourceSpan(edit.byte_start + base, edit.byte_end + base),
        )
        for token, span, edit in expected_findings(text)
    )


def _segment_containing(
    segments: tuple[tuple[str, int], ...],
    span: SourceSpan,
) -> int | None:
    """Return the index of the one segment wholly containing ``span``."""
    return next(
        (
            index
            for index, (text, base) in enumerate(segments)
            if base <= span.byte_start
            and span.byte_end <= base + len(text.encode("utf-8"))
        ),
        None,
    )


@settings(max_examples=120, deadline=None)
@given(pieces=_segment_pieces())
def test_findings_never_cross_a_segment_boundary(
    pieces: tuple[tuple[bool, str], ...],
) -> None:
    """A repeat is found inside one segment, never across the markup between two.

    The generated pieces deliberately reuse a small vocabulary, so the text of
    two adjacent segments often concatenates into a repeat that the source does
    not contain. A rule that joined segments would report it; one that scans a
    segment at a time must not.
    """
    text, segments = _render_segments(pieces)
    source = text.encode("utf-8")
    expected = [
        finding
        for segment_text, base in segments
        for finding in _shifted_findings(segment_text, base)
    ]
    result = LintSetup().run(source)

    assert len(result) == len(expected), (
        f"expected one finding per intra-segment run in {text!r}"
    )
    for diagnostic, (token, span, edit_span) in zip(result, expected, strict=True):
        assert source[span.byte_start : span.byte_end].decode("utf-8") == token.text, (
            "expected the finding's span to address exactly the repeated token"
        )
        assert diagnostic.span == span, (
            "expected the finding to carry the oracle's byte span"
        )
        assert diagnostic.fix is not None, (
            "expected each finding to carry an unsafe edit"
        )
        (edit,) = diagnostic.fix.edits
        assert (edit.byte_start, edit.byte_end) == (
            edit_span.byte_start,
            edit_span.byte_end,
        ), "expected the edit to remove only the run's suffix"
        span_segment = _segment_containing(segments, span)
        edit_segment = _segment_containing(segments, edit_span)
        assert span_segment is not None, (
            "expected the finding to lie inside one source-backed segment"
        )
        assert edit_segment == span_segment, (
            "expected the edit to stay inside the segment it reports"
        )


def test_a_repeat_split_by_emphasis_is_not_reported() -> None:
    """The concatenated segment texts form a repeat that the source does not.

    ``'the '`` and ``'the'`` join to ``'the the'``, so a rule that joined
    segments would report a repeat across the emphasis marker. Scanning one
    segment at a time finds nothing.
    """
    assert LintSetup().run("the *the*\n") == [], (
        "expected emphasis to separate two tokens that would otherwise repeat"
    )
