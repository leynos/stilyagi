"""Select documentation summaries and map their characters back to source.

A documentation region's flattened text is not a file transcript. Rust line
comments are joined with synthetic ``softbreak_space`` segments, Python
docstrings keep their source indentation, and either form may carry CR-LF
terminators. This module reduces a region to the physical lines a summary
policy needs and maps one chosen character back to its half-open byte span in
the original source.

Nothing here mutates the region, decodes Python string escapes, or parses
Markdown. It answers three bounded questions — which physical lines exist,
which of them form the first summary, and where one character lives in the
source — and leaves every policy decision to the rule that asked.
"""

import dataclasses as dc
import typing as typ

from stilyagi.model.source import SourceSpan
from stilyagi.rules.builtin.text import utf8_offsets

if typ.TYPE_CHECKING:  # pragma: no cover - typing only
    import collections.abc as cabc

    from stilyagi.model.region import RegionSegment, RegionView

__all__ = [
    "PhysicalLine",
    "SummarySource",
    "has_excluded_markup",
    "starts_with_markup",
]

#: The synthetic reason the extractor records for a flattened line break.
_LINE_BREAK_REASON = "softbreak_space"

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


@dc.dataclass(frozen=True, slots=True)
class PhysicalLine:
    """One physical line's half-open character range in the region text.

    Parameters
    ----------
    start:
        Offset of the line's first character in the reconstructed region text.
    end:
        Offset just past the line's last character. A CR that terminates a
        CR-LF pair is excluded from the range.
    """

    start: int
    end: int


@dc.dataclass(frozen=True, slots=True)
class SummarySource:
    """One region's reconstructed text, segments, and physical lines.

    Parameters
    ----------
    text:
        The region text rebuilt from its segments, in document order.
    segments:
        The segments that produced ``text``, used to map characters to bytes.
    lines:
        Physical content lines, split at LF and at synthetic line breaks.

    Examples
    --------
    >>> from stilyagi.model.region import RegionSegment, RegionView
    >>> region = RegionView(
    ...     "r0", "python_docstring", "python", (), {},
    ...     (RegionSegment(SourceSpan(3, 7), "Doc."),),
    ... )
    >>> source = SummarySource.of(region)
    >>> source.text
    'Doc.'
    >>> source.line_text(source.lines[0])
    'Doc.'
    """

    text: str
    segments: tuple[RegionSegment, ...]
    lines: tuple[PhysicalLine, ...]

    @classmethod
    def of(cls, region: RegionView) -> typ.Self:
        """Build the summary source for one projected region.

        Parameters
        ----------
        region:
            Region whose segments carry the text and its source mapping.

        Returns
        -------
        SummarySource
            The reconstructed text, its segments, and its physical lines.
        """
        text = "".join(segment.text for segment in region.segments)
        return cls(
            text=text,
            segments=region.segments,
            lines=_physical_lines(region.segments, len(text)),
        )

    def line_text(self, line: PhysicalLine) -> str:
        """Return one physical line's text, without its CR-LF terminator.

        Parameters
        ----------
        line:
            A line from :attr:`lines`.

        Returns
        -------
        str
            The line's text. Python Unicode whitespace semantics apply to any
            later ``strip`` the caller performs.
        """
        return self.text[line.start : line.end].removesuffix("\r")

    def is_blank(self, line: PhysicalLine) -> bool:
        """Return whether a line holds only Unicode whitespace.

        Parameters
        ----------
        line:
            A line from :attr:`lines`.

        Returns
        -------
        bool
            ``True`` when the line's text strips to the empty string.
        """
        return not self.line_text(line).strip()

    def first_content_index(self) -> int | None:
        """Return the index of the first nonblank line, or ``None``.

        Returns
        -------
        int | None
            The first line index whose text is not blank.
        """
        return next(
            (index for index, line in enumerate(self.lines) if not self.is_blank(line)),
            None,
        )

    def first_paragraph(self) -> tuple[PhysicalLine, ...]:
        """Return the lines from the first content line up to a blank line.

        Leading blank lines are skipped. A blank line ends the paragraph, and
        so does the end of the region.

        Returns
        -------
        tuple[PhysicalLine, ...]
            The paragraph's lines, empty when the region has no content.
        """
        first = self.first_content_index()
        if first is None:
            return ()
        paragraph: list[PhysicalLine] = []
        for line in self.lines[first:]:
            if self.is_blank(line):
                break
            paragraph.append(line)
        return tuple(paragraph)

    def first_content_line(self) -> tuple[PhysicalLine, ...]:
        """Return the first nonblank line as a one-line tuple.

        Returns
        -------
        tuple[PhysicalLine, ...]
            The first content line, empty when the region has no content.
        """
        first = self.first_content_index()
        return () if first is None else (self.lines[first],)

    def trimmed(self, lines: cabc.Sequence[PhysicalLine]) -> tuple[str, int]:
        """Return a line range's trimmed text and its start character offset.

        The range spans from the first line's start to the last line's end, so
        the separator characters between lines are part of the candidate. A
        later ``strip`` removes only Unicode whitespace at the two ends.

        Parameters
        ----------
        lines:
            A nonempty contiguous line range, such as :meth:`first_paragraph`.

        Returns
        -------
        tuple[str, int]
            The trimmed text and the character offset it starts at. Both are
            empty and ``-1`` when ``lines`` is empty.
        """
        if not lines:
            return "", -1
        raw = self.text[lines[0].start : lines[-1].end]
        stripped = raw.strip()
        leading = len(raw) - len(raw.lstrip())
        return stripped, lines[0].start + leading

    def anchor(self, index: int) -> SourceSpan | None:
        """Map one region-text character to its source byte span.

        Parameters
        ----------
        index:
            Character offset in :attr:`text`.

        Returns
        -------
        SourceSpan | None
            The half-open byte span of that one character, or ``None`` when
            the character is synthetic or outside the reconstructed text.
        """
        cursor = 0
        for segment in self.segments:
            end = cursor + len(segment.text)
            if cursor <= index < end and segment.span is not None:
                offsets = utf8_offsets(segment.text)
                relative = index - cursor
                base = segment.span.byte_start
                return SourceSpan(
                    base + offsets[relative], base + offsets[relative + 1]
                )
            cursor = end
        return None


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


def _physical_lines(
    segments: cabc.Sequence[RegionSegment],
    text_length: int,
) -> tuple[PhysicalLine, ...]:
    """Split the reconstructed text at LF and synthetic line breaks.

    A lone CR and the Unicode line separators do not start a new line. The CR
    of a CR-LF pair belongs to the terminator, so the line range stops before
    it.

    Returns
    -------
    tuple[PhysicalLine, ...]
        At least one line, in text order.
    """
    splitter = _LineSplitter()
    for segment in segments:
        if _is_line_break(segment):
            splitter.break_line(len(segment.text))
        else:
            splitter.append(segment.text)
    return splitter.finish(text_length)


@dc.dataclass(slots=True)
class _LineSplitter:
    """Accumulate physical lines while the region text is walked once.

    The splitter owns the running character cursor and the current line's
    start, so the walk has one branch per segment instead of a conditional
    nested inside a per-character scan.
    """

    lines: list[PhysicalLine] = dc.field(default_factory=list)
    start: int = 0
    cursor: int = 0

    def append(self, text: str) -> None:
        """Append ordinary segment text, ending a line at every LF."""
        for offset, character in enumerate(text):
            if character != "\n":
                continue
            self.lines.append(PhysicalLine(self.start, self.cursor + offset))
            self.start = self.cursor + offset + 1
        self.cursor += len(text)

    def break_line(self, width: int) -> None:
        """End the current line at a synthetic separator of ``width`` units."""
        self.lines.append(PhysicalLine(self.start, self.cursor))
        self.cursor += width
        self.start = self.cursor

    def finish(self, text_length: int) -> tuple[PhysicalLine, ...]:
        """Close the final line and return every line in text order.

        Returns
        -------
        tuple[PhysicalLine, ...]
            At least one line, in text order.
        """
        self.lines.append(PhysicalLine(self.start, text_length))
        return tuple(self.lines)


def _is_line_break(segment: RegionSegment) -> bool:
    """Return whether a segment is the extractor's flattened line break."""
    return segment.span is None and segment.synthetic_reason == _LINE_BREAK_REASON


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
