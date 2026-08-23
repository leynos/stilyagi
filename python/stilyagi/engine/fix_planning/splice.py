"""Apply validated text edits to their original source bytes."""

import typing as typ

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from stilyagi.fixes import TextEdit


def apply_edits(source_bytes: bytes, edits: cabc.Iterable[TextEdit]) -> bytes:
    """Splice sorted, unique edits into source bytes.

    Callers are responsible for validating edit bounds, UTF-8 boundaries, and
    conflicts. This deliberately narrow kernel only gives the already-admitted
    edits deterministic byte semantics.

    Parameters
    ----------
    source_bytes:
        Original bytes to preserve outside edited spans.
    edits:
        Valid non-overlapping edits in any order. Exact duplicates are merged.

    Returns
    -------
    bytes
        The source bytes after every unique edit has been applied.

    Examples
    --------
    >>> apply_edits(b"one two", (TextEdit(4, 7, "three"),))
    b'one three'
    """
    ordered_edits = tuple(sorted(dict.fromkeys(edits)))
    parts: list[bytes] = []
    cursor = 0
    for edit in ordered_edits:
        parts.extend((
            source_bytes[cursor : edit.byte_start],
            edit.replacement.encode(),
        ))
        cursor = edit.byte_end
    parts.append(source_bytes[cursor:])
    return b"".join(parts)
