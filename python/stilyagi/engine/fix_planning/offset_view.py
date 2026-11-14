"""Reconcile the byte view IR offsets address with the bytes read from disk.

The extraction reader decodes Markdown with ``utf-8-sig``, so a leading
byte-order mark is gone before the extractor ever sees it. Every offset in the
resulting IR therefore counts from the first byte *after* that mark, while the
source bytes the planner validates against still carry it. Splitting the mark
off once, and putting it back on the way out, is what keeps those two views
from disagreeing by three bytes on every buffer-marked file.
"""

import dataclasses as dc

__all__ = ["OffsetView"]

#: The UTF-8 byte-order mark, which the reader strips before extraction.
_BOM = b"\xef\xbb\xbf"


@dc.dataclass(frozen=True, slots=True)
class OffsetView:
    r"""The byte sequence IR offsets address, plus the marker they address past.

    Extraction receives decoded text, and the reader decodes Markdown with
    ``utf-8-sig``, so a leading byte-order mark is gone before the extractor
    ever sees it. Every offset in the resulting IR therefore counts from the
    first byte after that mark, while ``source_bytes`` still carries it. The
    two views differ by the mark's width, and validating one against the other
    refuses every edit in the file.

    Splitting the mark off once gives planning a single view to work in, and
    :meth:`restore` puts it back on the way out, so the bytes written to disk
    still begin exactly as the bytes read from it did.

    Examples
    --------
    >>> view = OffsetView.of(b"\xef\xbb\xbf# Hi\n")
    >>> view.body
    b'# Hi\n'
    >>> view.restore(b"# Bye\n")
    b'\xef\xbb\xbf# Bye\n'
    """

    bom: bytes
    body: bytes

    @classmethod
    def of(cls, source_bytes: bytes) -> OffsetView:
        """Split a leading UTF-8 byte-order mark from the addressed bytes.

        Returns
        -------
        OffsetView
            The mark, empty when the source has none, and the bytes the IR
            offsets address.
        """
        if source_bytes.startswith(_BOM):
            return cls(_BOM, source_bytes[len(_BOM) :])
        return cls(b"", source_bytes)

    def restore(self, body: bytes) -> bytes:
        """Re-prepend the original mark to a replacement of :attr:`body`.

        Returns
        -------
        bytes
            The bytes to write, which begin with the same mark the source did.
        """
        return self.bom + body
