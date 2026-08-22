"""Map IR byte offsets onto 1-based source locations."""

import typing as typ
from bisect import bisect_right
from itertools import pairwise

if typ.TYPE_CHECKING:
    import collections.abc as cabc


def line_column_from_offset(
    line_index: cabc.Sequence[int] | None,
    offset: int | None,
) -> tuple[int, int]:
    """Return a 1-based line and column for a byte offset.

    Parameters
    ----------
    line_index:
        Byte offsets of the line starts, or ``None`` when the IR omits line
        metadata. A leading zero is inferred when the sequence does not already
        begin at offset zero.
    offset:
        The 0-based byte offset to locate, or ``None`` when it is unknown.

    Returns
    -------
    tuple[int, int]
        The 1-based ``(line, column)`` position for ``offset``. Falls back to
        ``(1, 1)`` when the line index or offset is missing or malformed.

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

    Returns
    -------
    tuple[int, ...] | None
        Normalised line starts, or ``None`` when the input is empty or invalid.

    Examples
    --------
    >>> _normalised_line_starts((6, 12))
    (0, 6, 12)
    >>> _normalised_line_starts(()) is None
    True
    """
    try:
        starts = tuple(int(start) for start in line_index)
    # Parenthesise the exception tuple for clarity and pre-3.14 portability;
    # ruff format would otherwise strip the parentheses under the 3.14 target.
    except (TypeError, ValueError):  # fmt: skip
        return None

    if not starts:
        return None

    if starts[0] != 0:
        starts = (0, *starts)

    if not _has_valid_line_starts(starts):
        return None

    return starts


def _has_valid_line_starts(starts: tuple[int, ...]) -> bool:
    """Return whether line starts are non-negative and strictly increasing."""
    return all(start >= 0 for start in starts) and all(
        current < following for current, following in pairwise(starts)
    )


def _line_number_for_position(starts: tuple[int, ...], position: int) -> int:
    """Return the 0-based line number containing a byte position.

    Returns
    -------
    int
        The zero-based line number containing the position.

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
