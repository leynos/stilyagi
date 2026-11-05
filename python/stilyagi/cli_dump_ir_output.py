"""Frame and stream canonical Markdown IR with bounded memory use."""

import codecs
import enum
import io
import typing as typ

_OUTPUT_CHUNK_SIZE = 64 * 1024


class DumpIrSpoolErrorCode(enum.StrEnum):
    """Identify one failure while framing or writing canonical IR bytes."""

    DOCUMENT_TRUNCATED = enum.auto()
    SHORT_JSON_SPOOL_WRITE = enum.auto()
    SHORT_STDOUT_WRITE = enum.auto()


class DumpIrSpoolError(OSError):
    """One bounded temporary-spool failure that prevents complete JSON output."""

    _MESSAGES: typ.ClassVar[dict[DumpIrSpoolErrorCode, str]] = {
        DumpIrSpoolErrorCode.DOCUMENT_TRUNCATED: (
            "canonical document spool ended unexpectedly"
        ),
        DumpIrSpoolErrorCode.SHORT_JSON_SPOOL_WRITE: "short write to JSON spool",
        DumpIrSpoolErrorCode.SHORT_STDOUT_WRITE: "short write to standard output",
    }

    def __init__(self, code: DumpIrSpoolErrorCode) -> None:
        """Render one bounded-spool failure from its stable error code."""
        super().__init__(self._MESSAGES[code])


def _write_json_framing(
    output_spool: typ.IO[bytes],
    document_spool: typ.IO[bytes],
    document_lengths: tuple[int, ...],
) -> None:
    """Frame spooled canonical documents without reserializing their IR."""
    if len(document_lengths) == 1:
        _copy_document_spool(
            document_spool,
            output_spool,
            0,
            document_lengths[0],
        )
        return
    if not document_lengths:
        _write_chunk(output_spool, b"[]\n")
        return
    _write_chunk(output_spool, b"[")
    offset = 0
    for index, length in enumerate(document_lengths):
        if index:
            _write_chunk(output_spool, b",")
        _copy_document_spool(document_spool, output_spool, offset, length)
        offset += length
    _write_chunk(output_spool, b"]\n")


def _copy_document_spool(
    document_spool: typ.IO[bytes],
    output_spool: typ.IO[bytes],
    offset: int,
    length: int,
) -> None:
    """Copy one spooled canonical document in bounded chunks."""
    document_spool.seek(offset)
    remaining = length
    while remaining:
        chunk = document_spool.read(min(_OUTPUT_CHUNK_SIZE, remaining))
        if not chunk:
            raise DumpIrSpoolError(DumpIrSpoolErrorCode.DOCUMENT_TRUNCATED)
        _write_chunk(output_spool, chunk)
        remaining -= len(chunk)


def _write_chunk[WriteContent: (str, bytes)](
    output: typ.IO[WriteContent],
    contents: WriteContent,
    error_code: DumpIrSpoolErrorCode = DumpIrSpoolErrorCode.SHORT_JSON_SPOOL_WRITE,
) -> None:
    """Write a chunk or report an incomplete spool or stdout write."""
    if output.write(contents) != len(contents):
        raise DumpIrSpoolError(error_code)


def _canonical_bytes(document: str) -> bytes:
    """Encode canonical Rust JSON and guarantee its required final newline."""
    encoded = document.encode("utf-8")
    return encoded if encoded.endswith(b"\n") else encoded + b"\n"


def _copy_spool_to_output(
    spool: typ.IO[bytes], output: typ.TextIO | typ.BinaryIO
) -> None:
    """Copy completed bytes to stdout without loading a large spool at once."""
    binary_output = getattr(output, "buffer", None)
    if binary_output is None and not isinstance(output, io.TextIOBase):
        binary_output = output
    if binary_output is not None:
        _copy_binary_chunks(spool, typ.cast("typ.BinaryIO", binary_output))
        return

    text_output = typ.cast("typ.TextIO", output)
    decoder = codecs.getincrementaldecoder("utf-8")()
    while chunk := spool.read(_OUTPUT_CHUNK_SIZE):
        decoded = decoder.decode(chunk)
        if decoded:
            _write_chunk(
                text_output,
                decoded,
                DumpIrSpoolErrorCode.SHORT_STDOUT_WRITE,
            )
    final_text = decoder.decode(b"", final=True)
    if final_text:
        _write_chunk(
            text_output,
            final_text,
            DumpIrSpoolErrorCode.SHORT_STDOUT_WRITE,
        )


def _copy_binary_chunks(spool: typ.IO[bytes], output: typ.BinaryIO) -> None:
    """Stream binary output in bounded chunks and flush it when supported."""
    while chunk := spool.read(_OUTPUT_CHUNK_SIZE):
        _write_chunk(
            output,
            chunk,
            DumpIrSpoolErrorCode.SHORT_STDOUT_WRITE,
        )
    output.flush()
