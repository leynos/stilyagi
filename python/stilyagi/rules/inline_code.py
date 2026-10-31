"""Answer inline-code containment with one binary search per segment.

The canonical IR emits inline-code node spans once per document. Scanning the
whole span list for every candidate segment makes a document with many code
spans and many segments quadratic. This index keeps the starts ordered and the
furthest end seen so far at each position, so a containment query costs
``log(len(starts))`` and is independent of how many spans the document has.
"""

import dataclasses as dc
import typing as typ
from bisect import bisect_right

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from stilyagi.model.source import SourceSpan

__all__ = ["InlineCodeIndex"]


@dc.dataclass(frozen=True, slots=True)
class InlineCodeIndex:
    """A sorted index over inline-code spans, tolerant of overlaps.

    Parameters
    ----------
    starts:
        Span starts, ascending. Only ``from_spans`` should build these.
    furthest_ends:
        For each position, the greatest end among spans starting at or before
        that position. This makes an enclosing span discoverable even when it
        is not the most recently started one.

    Examples
    --------
    >>> from stilyagi.model.source import SourceSpan
    >>> index = InlineCodeIndex.from_spans((SourceSpan(9, 17),))
    >>> index.contains(SourceSpan(10, 12))
    True
    >>> index.contains(SourceSpan(17, 18))
    False
    """

    starts: tuple[int, ...] = ()
    furthest_ends: tuple[int, ...] = ()

    @classmethod
    def from_spans(cls, spans: cabc.Iterable[SourceSpan]) -> InlineCodeIndex:
        """Build an index from spans in any order.

        Parameters
        ----------
        spans:
            Inline-code spans, possibly overlapping or unsorted.

        Returns
        -------
        InlineCodeIndex
            An index that answers containment for exactly these spans.

        Examples
        --------
        >>> from stilyagi.model.source import SourceSpan
        >>> index = InlineCodeIndex.from_spans((SourceSpan(5, 9), SourceSpan(2, 4)))
        >>> [index.contains(SourceSpan(start, start + 1)) for start in range(6)]
        [False, False, True, True, False, True]
        """
        ordered = sorted(spans)
        starts: list[int] = []
        furthest_ends: list[int] = []
        furthest = 0
        for span in ordered:
            starts.append(span.byte_start)
            furthest = max(furthest, span.byte_end)
            furthest_ends.append(furthest)
        return cls(tuple(starts), tuple(furthest_ends))

    def contains(self, span: SourceSpan) -> bool:
        """Return whether ``span`` lies wholly inside one indexed span.

        Parameters
        ----------
        span:
            Candidate source-backed span.

        Returns
        -------
        bool
            ``True`` when an inline-code span encloses it.

        Examples
        --------
        >>> from stilyagi.model.source import SourceSpan
        >>> InlineCodeIndex().contains(SourceSpan(0, 1))
        False
        >>> index = InlineCodeIndex.from_spans((SourceSpan(0, 4),))
        >>> index.contains(SourceSpan(0, 4))
        True
        """
        position = bisect_right(self.starts, span.byte_start) - 1
        return position >= 0 and self.furthest_ends[position] >= span.byte_end
