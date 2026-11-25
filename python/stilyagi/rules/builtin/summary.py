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
from stilyagi.rules.builtin.line_split import PhysicalLine, physical_lines
from stilyagi.rules.builtin.text import utf8_offsets

if typ.TYPE_CHECKING:  # pragma: no cover - typing only
    import collections.abc as cabc

    from stilyagi.model.region import RegionSegment, RegionView

__all__ = [
    "PhysicalLine",
    "SummarySource",
]


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

        Examples
        --------
        >>> from stilyagi.model.region import RegionSegment, RegionView
        >>> region = RegionView(
        ...     "r0", "python_docstring", "python", (), {},
        ...     (RegionSegment(SourceSpan(3, 7), "Doc."),),
        ... )
        >>> SummarySource.of(region).text
        'Doc.'
        >>> SummarySource.of(region).lines
        (PhysicalLine(start=0, end=4),)
        """
        text = "".join(segment.text for segment in region.segments)
        return cls(
            text=text,
            segments=region.segments,
            lines=physical_lines(region.segments, len(text)),
        )

    def line_text(self, line: PhysicalLine) -> str:
        r"""Return one physical line's text, without its CR-LF terminator.

        Parameters
        ----------
        line:
            A line from :attr:`lines`.

        Returns
        -------
        str
            The line's text. The CR of a CR-LF pair is already excluded from
            the range, and a lone CR is ordinary text, so nothing is stripped
            here. Python Unicode whitespace semantics apply to any later
            ``strip`` the caller performs.

        Examples
        --------
        >>> from stilyagi.model.region import RegionSegment, RegionView
        >>> region = RegionView(
        ...     "r0", "python_docstring", "python", (), {},
        ...     (RegionSegment(SourceSpan(3, 9), "A.\r\nB."),),
        ... )
        >>> source = SummarySource.of(region)
        >>> [source.line_text(line) for line in source.lines]
        ['A.', 'B.']
        """
        return self.text[line.start : line.end]

    def is_blank(self, line: PhysicalLine) -> bool:
        r"""Return whether a line holds only Unicode whitespace.

        The check is :meth:`line_text` followed by ``strip``, so it shares that
        method's Unicode whitespace semantics and its CR-LF handling.

        Returns
        -------
        bool
            ``True`` when the line's text strips to the empty string.

        Examples
        --------
        >>> from stilyagi.model.region import RegionSegment, RegionView
        >>> region = RegionView(
        ...     "r0", "python_docstring", "python", (), {},
        ...     (RegionSegment(SourceSpan(3, 11), "\n  \nDoc."),),
        ... )
        >>> source = SummarySource.of(region)
        >>> [source.is_blank(line) for line in source.lines]
        [True, True, False]
        """
        return not self.line_text(line).strip()

    def first_content_index(self) -> int | None:
        r"""Return the index of the first nonblank line, or ``None``.

        Returns
        -------
        int | None
            The first line index whose text is not blank.

        Examples
        --------
        >>> from stilyagi.model.region import RegionSegment, RegionView
        >>> region = RegionView(
        ...     "r0", "python_docstring", "python", (), {},
        ...     (RegionSegment(SourceSpan(3, 9), "\n\nDoc."),),
        ... )
        >>> SummarySource.of(region).first_content_index()
        2
        """
        return next(
            (index for index, line in enumerate(self.lines) if not self.is_blank(line)),
            None,
        )

    def first_paragraph(self) -> tuple[PhysicalLine, ...]:
        r"""Return the lines from the first content line up to a blank line.

        Leading blank lines are skipped. A blank line ends the paragraph, and
        so does the end of the region.

        Returns
        -------
        tuple[PhysicalLine, ...]
            The paragraph's lines, empty when the region has no content.

        Examples
        --------
        >>> from stilyagi.model.region import RegionSegment, RegionView
        >>> region = RegionView(
        ...     "r0", "python_docstring", "python", (), {},
        ...     (RegionSegment(SourceSpan(3, 19), "One.\nTwo.\n\nMore."),),
        ... )
        >>> source = SummarySource.of(region)
        >>> [source.line_text(line) for line in source.first_paragraph()]
        ['One.', 'Two.']
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
        r"""Return the first nonblank line as a one-line tuple.

        Returns
        -------
        tuple[PhysicalLine, ...]
            The first content line, empty when the region has no content.

        Examples
        --------
        >>> from stilyagi.model.region import RegionSegment, RegionView
        >>> region = RegionView(
        ...     "r0", "python_docstring", "python", (), {},
        ...     (RegionSegment(SourceSpan(3, 12), "One.\nTwo."),),
        ... )
        >>> source = SummarySource.of(region)
        >>> [source.line_text(line) for line in source.first_content_line()]
        ['One.']
        """
        first = self.first_content_index()
        return () if first is None else (self.lines[first],)

    def trimmed(self, lines: cabc.Sequence[PhysicalLine]) -> tuple[str, int]:
        r"""Return a line range's trimmed text and its start character offset.

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

        Examples
        --------
        >>> from stilyagi.model.region import RegionSegment, RegionView
        >>> region = RegionView(
        ...     "r0", "python_docstring", "python", (), {},
        ...     (RegionSegment(SourceSpan(3, 15), "  One.\nTwo. "),),
        ... )
        >>> source = SummarySource.of(region)
        >>> source.trimmed(source.first_paragraph())
        ('One.\nTwo.', 2)
        >>> source.trimmed(())
        ('', -1)
        """
        if not lines:
            return "", -1
        raw = self.text[lines[0].start : lines[-1].end]
        stripped = raw.strip()
        leading = len(raw) - len(raw.lstrip())
        return stripped, lines[0].start + leading

    def anchor(self, index: int) -> SourceSpan | None:
        r"""Map one region-text character to its source byte span.

        Parameters
        ----------
        index:
            Character offset in :attr:`text`.

        Returns
        -------
        SourceSpan | None
            The half-open byte span of that one character, or ``None`` when
            the character is synthetic or outside the reconstructed text.

        Examples
        --------
        A character index is not a byte offset: the accented character is
        character 1 but starts at byte 11.

        >>> from stilyagi.model.region import RegionSegment, RegionView
        >>> region = RegionView(
        ...     "r0", "python_docstring", "python", (), {},
        ...     (RegionSegment(SourceSpan(10, 13), "a\u00e9"),),
        ... )
        >>> source = SummarySource.of(region)
        >>> source.anchor(1)
        SourceSpan(byte_start=11, byte_end=13)
        >>> source.anchor(5) is None
        True

        A synthetic segment has no source bytes, so it maps to ``None``.

        >>> synthetic = RegionView(
        ...     "r0", "rust_doc_comment", "rust", (), {},
        ...     (RegionSegment(None, "x", synthetic_reason="decoded_text"),),
        ... )
        >>> SummarySource.of(synthetic).anchor(0) is None
        True
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
