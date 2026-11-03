"""Index resolved suppression spans per code for logarithmic lookups.

A document may alternate disabled sections with findings outside them, so a
plan that scans every directive for every finding costs
``O(findings x directives)``. Grouping each code's spans and ordering them by
start lets one bisection answer a lookup, with a running maximum of the ends
so overlapping spans still resolve correctly.
"""

import bisect
import dataclasses as dc
import itertools
import typing as typ

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from stilyagi.rules.suppression import InlineSuppression, RuleInterval

__all__ = ["SuppressionIndex"]


@dc.dataclass(frozen=True, slots=True)
class SuppressionIndex:
    """Per-code ordered span index with prefix-maximum end offsets.

    Parameters
    ----------
    starts:
        Sorted span starts per rule code.
    max_ends:
        Running maximum of the span ends for each code, matching ``starts``
        position for position.

    Examples
    --------
    >>> SuppressionIndex().covers("MD001", 0)
    False
    """

    starts: dict[str, tuple[int, ...]] = dc.field(default_factory=dict)
    max_ends: dict[str, tuple[int, ...]] = dc.field(default_factory=dict)

    @classmethod
    def build(
        cls,
        intervals: cabc.Iterable[RuleInterval],
        inline: cabc.Iterable[InlineSuppression],
    ) -> SuppressionIndex:
        """Group spans by code and order them for bisection.

        Parameters
        ----------
        intervals:
            Range suppression intervals, in any order.
        inline:
            ``ignore-next`` suppressions, each covering its unit for every
            code it names.

        Returns
        -------
        SuppressionIndex
            An index whose lookups are logarithmic per code.

        Examples
        --------
        >>> from stilyagi.rules.suppression import RuleInterval
        >>> index = SuppressionIndex.build((RuleInterval("MD001", 5, 10),), ())
        >>> index.covers("MD001", 7)
        True
        """
        spans = _spans_by_code(intervals, inline)
        starts: dict[str, tuple[int, ...]] = {}
        max_ends: dict[str, tuple[int, ...]] = {}
        for code, code_spans in spans.items():
            ordered = sorted(code_spans)
            starts[code] = tuple(start for start, _ in ordered)
            max_ends[code] = tuple(
                itertools.accumulate((end for _, end in ordered), max)
            )
        return cls(starts=starts, max_ends=max_ends)

    def covers(self, code: str, start: int) -> bool:
        """Return whether any indexed span for ``code`` covers ``start``.

        Parameters
        ----------
        code:
            Candidate rule code.
        start:
            The finding's primary span start.

        Returns
        -------
        bool
            ``True`` when a half-open span for this code contains ``start``.

        Examples
        --------
        >>> from stilyagi.rules.suppression import RuleInterval
        >>> index = SuppressionIndex.build((RuleInterval("MD001", 5, 10),), ())
        >>> index.covers("MD001", 9)
        True
        >>> index.covers("MD001", 10)
        False
        """
        starts = self.starts.get(code)
        if not starts:
            return False
        position = bisect.bisect_right(starts, start) - 1
        return position >= 0 and self.max_ends[code][position] > start


def _spans_by_code(
    intervals: cabc.Iterable[RuleInterval],
    inline: cabc.Iterable[InlineSuppression],
) -> dict[str, list[tuple[int, int]]]:
    """Collect every resolved span under each code it suppresses."""
    spans: dict[str, list[tuple[int, int]]] = {}
    for interval in intervals:
        spans.setdefault(interval.code, []).append((
            interval.byte_start,
            interval.byte_end,
        ))
    for suppression in inline:
        span = (suppression.unit.byte_start, suppression.unit.byte_end)
        for code in suppression.codes:
            spans.setdefault(code, []).append(span)
    return spans
