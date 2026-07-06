"""Map IR byte offsets onto 1-based source locations."""

from __future__ import annotations

import typing as typ
from bisect import bisect_right

if typ.TYPE_CHECKING:
    import collections.abc as cabc


def line_column_from_offset(
    line_index: cabc.Sequence[int] | None,
    offset: int | None,
) -> tuple[int, int]:
    """Return a 1-based line and column for a byte offset.

    Examples
    --------
    >>> line_column_from_offset((0, 6, 12), 7)
    (2, 2)
    >>> line_column_from_offset(None, 7)
    (1, 1)
    """
    if line_index is None or offset is None:
        return (1, 1)

    starts = _normalised_line_starts(line_index)
    if starts is None:
        return (1, 1)

    position = max(0, offset)
    line_number = _line_number_for_position(starts, position)
    return (line_number + 1, position - starts[line_number] + 1)


def _normalised_line_starts(
    line_index: cabc.Sequence[int],
) -> tuple[int, ...] | None:
    """Return validated line starts anchored at offset zero.

    Examples
    --------
    >>> _normalised_line_starts((6, 12))
    (0, 6, 12)
    >>> _normalised_line_starts(()) is None
    True
    """
    try:
        starts = tuple(int(start) for start in line_index)
    except TypeError, ValueError:
        return None

    if not starts:
        return None

    if starts[0] != 0:
        starts = (0, *starts)
    return starts


def _line_number_for_position(starts: tuple[int, ...], position: int) -> int:
    """Return the 0-based line number containing a byte position.

    Examples
    --------
    >>> _line_number_for_position((0, 6, 12), 7)
    1
    >>> _line_number_for_position((0, 6, 12), 99)
    1
    """
    line_number = bisect_right(starts, position) - 1
    if len(starts) > 1 and line_number >= len(starts) - 1:
        line_number = len(starts) - 2
    return max(0, line_number)
