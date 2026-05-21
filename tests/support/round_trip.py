"""Private helpers for source edit round-trip tests.

This module applies source-backed replacements with UTF-8 byte offsets, keeps
untouched source text intact, and rejects synthetic, overlapping, malformed, or
non-boundary spans. The Python helper mirrors the Rust `stilyagi-test-support`
round-trip contract used by golden fixture tests.
"""

import dataclasses as dc
import itertools

UTF8_CONTINUATION_MASK = 0b1100_0000
UTF8_CONTINUATION_PREFIX = 0b1000_0000


class RoundTripEditError(ValueError):
    """Raised when an edit cannot be safely applied."""


class SyntheticSpanError(RoundTripEditError):
    """Raised when a caller tries to edit synthetic text."""

    def __init__(self, text: str) -> None:
        """Build an error for a synthetic segment label."""
        super().__init__(f"cannot edit synthetic segment {text!r}")


class OverlappingEditError(RoundTripEditError):
    """Raised when source edit spans overlap."""

    def __init__(self, previous: SourceEdit, current: SourceEdit) -> None:
        """Build an error for two overlapping edits."""
        super().__init__(
            f"overlapping edit spans {previous.start}..{previous.end} "
            f"and {current.start}..{current.end}"
        )


@dc.dataclass(frozen=True, slots=True)
class SourceEdit:
    """One source-backed replacement."""

    start: int
    end: int
    replacement: str


@dc.dataclass(frozen=True, slots=True)
class SyntheticEdit:
    """One attempted replacement of synthetic text."""

    text: str
    replacement: str


@dc.dataclass(frozen=True, slots=True)
class RoundTripResult:
    """Result returned by the private edit round-trip helper."""

    before: str
    after: str
    applied_edits: tuple[SourceEdit, ...]


def apply_round_trip_edits(
    source: str,
    edits: tuple[SourceEdit | SyntheticEdit, ...],
) -> RoundTripResult:
    """Apply source-backed edits while preserving untouched source text."""
    source_bytes = source.encode()
    source_edits: list[SourceEdit] = []
    for edit in edits:
        if isinstance(edit, SyntheticEdit):
            raise SyntheticSpanError(edit.text)
        _validate_source_edit(source_bytes, edit)
        source_edits.append(edit)

    ordered_edits = tuple(sorted(source_edits, key=lambda edit: (edit.start, edit.end)))
    _reject_overlaps(ordered_edits)

    cursor = 0
    after_parts: list[bytes] = []
    for edit in ordered_edits:
        after_parts.extend((
            source_bytes[cursor : edit.start],
            edit.replacement.encode(),
        ))
        cursor = edit.end
    after_parts.append(source_bytes[cursor:])
    return RoundTripResult(
        before=source,
        after=b"".join(after_parts).decode(),
        applied_edits=ordered_edits,
    )


def _validate_source_edit(source_bytes: bytes, edit: SourceEdit) -> None:
    """Reject spans outside the UTF-8 byte boundary."""
    is_ordered = 0 <= edit.start <= edit.end
    source_len = len(source_bytes)
    if not is_ordered or edit.end > source_len:
        msg = (
            f"invalid edit span {edit.start}..{edit.end} for source length {source_len}"
        )
        raise RoundTripEditError(msg)
    if not _is_utf8_boundary(source_bytes, edit.start) or not _is_utf8_boundary(
        source_bytes,
        edit.end,
    ):
        msg = f"edit span {edit.start}..{edit.end} cuts a UTF-8 code point"
        raise RoundTripEditError(msg)


def _is_utf8_boundary(source_bytes: bytes, offset: int) -> bool:
    """Return whether an offset falls between UTF-8 code points."""
    return (
        offset == len(source_bytes)
        or (source_bytes[offset] & UTF8_CONTINUATION_MASK) != UTF8_CONTINUATION_PREFIX
    )


def _reject_overlaps(edits: tuple[SourceEdit, ...]) -> None:
    """Reject overlapping source-backed edits."""
    for previous, current in itertools.pairwise(edits):
        if previous.end > current.start:
            raise OverlappingEditError(previous, current)
