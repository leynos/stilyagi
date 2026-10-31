"""Source-coordinate domain types shared by rules and diagnostics.

The engine, the rule boundary, and diagnostic rendering all need to talk about
half-open byte ranges in the original source. Keeping the type in the domain
package stops those layers from depending on the engine for a coordinate value.
"""

import dataclasses as dc

_UTF8_CONTINUATION_MASK = 0b1100_0000
_UTF8_CONTINUATION_PREFIX = 0b1000_0000


def is_utf8_boundary(source_bytes: bytes, offset: int) -> bool:
    """Return whether ``offset`` lies between UTF-8 code points.

    Parameters
    ----------
    source_bytes:
        The encoded source the offset addresses.
    offset:
        Candidate byte offset.

    Returns
    -------
    bool
        ``True`` when the offset is the buffer's start or end, or when the byte
        at that offset does not continue a multi-byte code point.

    Examples
    --------
    >>> is_utf8_boundary("é".encode(), 0)
    True
    >>> is_utf8_boundary("é".encode(), 1)
    False
    >>> is_utf8_boundary(b"", 0)
    True
    """
    if offset == 0 or offset == len(source_bytes):
        return True
    if offset < 0 or offset > len(source_bytes):
        return False
    return source_bytes[offset] & _UTF8_CONTINUATION_MASK != _UTF8_CONTINUATION_PREFIX


@dc.dataclass(frozen=True, slots=True, order=True)
class SourceSpan:
    """A half-open UTF-8 byte range in the original source.

    Parameters
    ----------
    byte_start:
        Inclusive start offset in UTF-8 bytes.
    byte_end:
        Exclusive end offset in UTF-8 bytes. Must not precede ``byte_start``.

    Examples
    --------
    >>> SourceSpan(3, 8)
    SourceSpan(byte_start=3, byte_end=8)
    """

    byte_start: int
    byte_end: int

    def __post_init__(self) -> None:
        """Reject inverted ranges so later slicing cannot silently underflow."""
        if self.byte_start < 0:
            msg = f"byte_start must be non-negative, got {self.byte_start}"
            raise ValueError(msg)
        if self.byte_end < self.byte_start:
            msg = (
                f"byte_end ({self.byte_end}) must not precede "
                f"byte_start ({self.byte_start})"
            )
            raise ValueError(msg)

    def contains(self, other: SourceSpan) -> bool:
        """Return whether ``other`` lies wholly inside this span.

        Parameters
        ----------
        other:
            Candidate span to test.

        Returns
        -------
        bool
            ``True`` when ``other`` is fully enclosed.

        Examples
        --------
        >>> SourceSpan(0, 10).contains(SourceSpan(2, 5))
        True
        >>> SourceSpan(0, 10).contains(SourceSpan(5, 12))
        False
        """
        return self.byte_start <= other.byte_start and other.byte_end <= self.byte_end

    def overlaps(self, other: SourceSpan) -> bool:
        """Return whether two half-open spans share at least one byte.

        Parameters
        ----------
        other:
            Candidate span to test.

        Returns
        -------
        bool
            ``True`` when the spans intersect.

        Examples
        --------
        >>> SourceSpan(0, 4).overlaps(SourceSpan(3, 8))
        True
        >>> SourceSpan(0, 4).overlaps(SourceSpan(4, 8))
        False
        """
        return self.byte_start < other.byte_end and other.byte_start < self.byte_end
