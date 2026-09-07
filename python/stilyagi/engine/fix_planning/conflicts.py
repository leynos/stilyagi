"""Normalize edit candidates and detect ambiguous source mutations."""

import itertools
import typing as typ

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from stilyagi.fixes import TextEdit


def coalesce_identical(edits: cabc.Iterable[TextEdit]) -> tuple[TextEdit, ...]:
    """Return unique edits in deterministic natural order."""
    return tuple(sorted(dict.fromkeys(edits)))


def first_overlap(edits: cabc.Iterable[TextEdit]) -> tuple[TextEdit, TextEdit] | None:
    """Return the first overlapping or same-offset insertion pair, when present."""
    ordered_edits = tuple(sorted(edits))
    return next(
        (
            (previous, current)
            for previous, current in itertools.pairwise(ordered_edits)
            if previous.byte_end > current.byte_start
            or _same_offset_insertions(previous, current)
        ),
        None,
    )


def _same_offset_insertions(previous: TextEdit, current: TextEdit) -> bool:
    """Return whether two distinct insertions compete at exactly one offset."""
    return (
        previous.byte_start
        == previous.byte_end
        == current.byte_start
        == current.byte_end
        and previous.replacement != current.replacement
    )
