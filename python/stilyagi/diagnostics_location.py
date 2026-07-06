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

    try:
        starts = tuple(int(start) for start in line_index)
    except TypeError:
        return (1, 1)
    except ValueError:
        return (1, 1)

    if not starts:
        return (1, 1)

    if starts[0] != 0:
        starts = (0, *starts)

    position = max(0, offset)
    line_number = bisect_right(starts, position) - 1
    if len(starts) > 1 and line_number >= len(starts) - 1:
        line_number = len(starts) - 2
    line_number = max(0, line_number)
    line_start = starts[line_number]
    return (line_number + 1, position - line_start + 1)
