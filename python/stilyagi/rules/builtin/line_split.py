"""Split one region's reconstructed text into physical lines.

Rust documentation comments are flattened with synthetic separators and a
region may carry CR-LF terminators, so "a line" is not simply text between LFs.
This module owns that walk: it splits at LF and at the extractor's recorded
line break, keeps the CR of a CR-LF pair out of the line range, and treats a
lone CR as ordinary text. It is a pure function over segments and owns no
policy.
"""

import dataclasses as dc
import typing as typ

if typ.TYPE_CHECKING:  # pragma: no cover - typing only
    import collections.abc as cabc

    from stilyagi.model.region import RegionSegment

__all__ = ["PhysicalLine", "physical_lines"]

#: The synthetic reason the extractor records for a flattened line break.
LINE_BREAK_REASON = "softbreak_space"


def physical_lines(
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
    """Accumulate physical lines while the region text is walked once."""

    lines: list[PhysicalLine] = dc.field(default_factory=list)
    start: int = 0
    cursor: int = 0
    last_char: str = ""

    def append(self, text: str) -> None:
        """Append ordinary segment text, ending a line at every LF.

        The CR of a CR-LF pair belongs to the terminator, so the line range
        stops before it even when the pair is split across two segments.
        """
        for offset, character in enumerate(text):
            if character != "\n":
                continue
            end = self.cursor + offset
            if self.preceded_by_cr(text, offset):
                end -= 1
            self.lines.append(PhysicalLine(self.start, end))
            self.start = self.cursor + offset + 1
        self.cursor += len(text)
        if text:
            self.last_char = text[-1]

    def preceded_by_cr(self, text: str, offset: int) -> bool:
        """Return whether the LF at ``offset`` follows a CR.

        Returns
        -------
        bool
            ``True`` when the character immediately before the LF is a CR,
            including when the pair is split across two segments.
        """
        return text[offset - 1] == "\r" if offset else self.last_char == "\r"

    def break_line(self, width: int) -> None:
        """End the current line at a synthetic separator of ``width`` units."""
        self.lines.append(PhysicalLine(self.start, self.cursor))
        self.cursor += width
        self.start = self.cursor

    def finish(self, text_length: int) -> tuple[PhysicalLine, ...]:
        """Close the final line and return every line in text order."""
        self.lines.append(PhysicalLine(self.start, text_length))
        return tuple(self.lines)


def _is_line_break(segment: RegionSegment) -> bool:
    """Return whether a segment is the extractor's flattened line break."""
    return segment.span is None and segment.synthetic_reason == LINE_BREAK_REASON


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

    Examples
    --------
    >>> PhysicalLine(0, 4)
    PhysicalLine(start=0, end=4)
    >>> "Doc."[0:4]
    'Doc.'
    """

    start: int
    end: int
