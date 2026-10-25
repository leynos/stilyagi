"""Run the read-only command that emits Rust's canonical Markdown IR."""

import codecs
import enum
import io
import pathlib
import sys
import tempfile
import typing as typ

from stilyagi import config, discovery, engine, model
from stilyagi.check_inputs import CheckInput
from stilyagi.check_targets import parse_target_operands
from stilyagi.cli_config import resolve_discovery_config
from stilyagi.cli_io import SourceReadError, read_source, stdin_check_input

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from stilyagi.cli_args import DumpIrOptions


_SPOOL_MEMORY_LIMIT = 1024 * 1024
_OUTPUT_CHUNK_SIZE = 64 * 1024


class DumpIrErrorCode(enum.StrEnum):
    """Identify one expected failure at the dump-ir command boundary."""

    STDIN_FILENAME_REQUIRED = enum.auto()
    STDIN_FILENAME_NOT_MARKDOWN = enum.auto()
    UNSUPPORTED_EXPLICIT_FILE = enum.auto()
    MISSING_TARGET = enum.auto()
    TARGET_NOTICE_MISSING_PATH = enum.auto()
    CANNOT_DISCOVER = enum.auto()
    CANNOT_READ = enum.auto()
    CANNOT_EXTRACT = enum.auto()
    MISSING_IR = enum.auto()


class DumpIrSpoolErrorCode(enum.StrEnum):
    """Identify one failure while framing or writing canonical IR bytes."""

    DOCUMENT_TRUNCATED = enum.auto()
    SHORT_JSON_SPOOL_WRITE = enum.auto()
    SHORT_STDOUT_WRITE = enum.auto()


class DumpIrError(Exception):
    """One expected command failure that must not emit partial JSON."""

    _MESSAGES: typ.ClassVar[dict[DumpIrErrorCode, str]] = {
        DumpIrErrorCode.STDIN_FILENAME_REQUIRED: (
            "standard input requires --stdin-filename"
        ),
        DumpIrErrorCode.STDIN_FILENAME_NOT_MARKDOWN: (
            "--stdin-filename must name Markdown: {}"
        ),
        DumpIrErrorCode.UNSUPPORTED_EXPLICIT_FILE: "unsupported explicit file: {}",
        DumpIrErrorCode.MISSING_TARGET: "target does not exist: {}",
        DumpIrErrorCode.TARGET_NOTICE_MISSING_PATH: (
            "discovery returned a target notice without a path"
        ),
        DumpIrErrorCode.CANNOT_DISCOVER: "cannot discover {}: {}",
        DumpIrErrorCode.CANNOT_READ: "cannot read {}: {}",
        DumpIrErrorCode.CANNOT_EXTRACT: "cannot extract {}: {}",
        DumpIrErrorCode.MISSING_IR: "extractor returned no canonical IR for {}",
    }

    def __init__(self, code: DumpIrErrorCode, *values: object) -> None:
        """Render one contextual error from its stable command message code."""
        super().__init__(self._MESSAGES[code].format(*values))


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


def run_dump_ir(
    options: DumpIrOptions,
    *,
    output: typ.TextIO | typ.BinaryIO | None = None,
    error: typ.TextIO | None = None,
    resolver: config.ConfigResolver | None = None,
) -> int:
    """Discover Markdown inputs and emit their canonical IR as JSON.

    All input reads, extraction results and JSON framing are completed in a
    bounded-memory spool before the command writes standard output. A failed
    input therefore cannot leave a valid-looking partial array in a pipeline.

    Parameters
    ----------
    options:
        Parsed options for one `dump-ir` invocation.
    output, error:
        Optional streams for tests and embedding callers.
    resolver:
        Optional configuration resolver used by the shared discovery query.

    Returns
    -------
    int
        Zero on success or two for an invalid input, configuration, extraction,
        spool, or output failure.

    Examples
    --------
    >>> from stilyagi.cli_args import DumpIrOptions
    >>> run_dump_ir(DumpIrOptions(targets=("README.md",)))  # doctest: +SKIP
    0
    """
    out_stream = output if output is not None else sys.stdout
    error_stream = error if error is not None else sys.stderr
    config_resolver = resolver if resolver is not None else config.ConfigResolver()
    try:
        inputs = _discover_markdown_inputs(options, config_resolver)
        with (
            tempfile.SpooledTemporaryFile(
                max_size=_SPOOL_MEMORY_LIMIT,
                mode="w+b",
            ) as document_spool,
            tempfile.SpooledTemporaryFile(
                max_size=_SPOOL_MEMORY_LIMIT,
                mode="w+b",
            ) as output_spool,
        ):
            document_lengths = _extract_documents(inputs, document_spool)
            _write_json_framing(
                output_spool,
                document_spool,
                document_lengths,
            )
            output_spool.seek(0)
            _copy_spool_to_output(output_spool, out_stream)
    except (DumpIrError, config.ConfigError, OSError, ValueError) as exc:
        error_stream.write(f"stilyagi dump-ir: {exc}\n")
        return 2
    return 0


def _discover_markdown_inputs(
    options: DumpIrOptions,
    resolver: config.ConfigResolver,
) -> tuple[CheckInput, ...]:
    """Reuse the check discovery boundary and retain Markdown inputs only."""
    target_paths, has_stdin = parse_target_operands(options.targets)
    resolved_config = resolve_discovery_config(options, resolver)
    if has_stdin:
        return _stdin_markdown_input(options)

    _reject_non_markdown_explicit_files(target_paths)

    result = discovery.discover_files_with_summary(target_paths, resolved_config)
    if result.failures:
        failure = result.failures[0]
        raise DumpIrError(DumpIrErrorCode.CANNOT_DISCOVER, failure.path, failure.error)
    _raise_target_notices(result.notices)
    return tuple(
        CheckInput.from_discovered(source)
        for source in result.files
        if source.syntax is model.Syntax.MARKDOWN
    )


def _stdin_markdown_input(options: DumpIrOptions) -> tuple[CheckInput, ...]:
    """Validate the stdin filename and return its single Markdown input."""
    if options.stdin_filename is None:
        raise DumpIrError(DumpIrErrorCode.STDIN_FILENAME_REQUIRED)
    stdin_path = pathlib.Path(options.stdin_filename)
    if discovery.syntax_for_path(stdin_path) is not model.Syntax.MARKDOWN:
        raise DumpIrError(
            DumpIrErrorCode.STDIN_FILENAME_NOT_MARKDOWN,
            options.stdin_filename,
        )
    return (stdin_check_input(options.stdin_filename, model.Syntax.MARKDOWN),)


def _reject_non_markdown_explicit_files(
    target_paths: cabc.Iterable[pathlib.Path],
) -> None:
    """Reject explicit existing files without a Markdown extractor."""
    unsupported_targets = tuple(
        path
        for path in target_paths
        if path.is_file()
        and discovery.syntax_for_path(path) is not model.Syntax.MARKDOWN
    )
    if unsupported_targets:
        raise DumpIrError(
            DumpIrErrorCode.UNSUPPORTED_EXPLICIT_FILE,
            unsupported_targets[0],
        )


def _raise_target_notices(
    notices: cabc.Iterable[discovery.DiscoveryNotice],
) -> None:
    """Turn the first missing or unsupported target notice into a command error."""
    notice_errors = (
        ("missing_or_unsupported_target", DumpIrErrorCode.MISSING_TARGET),
        ("unregistered_explicit_file", DumpIrErrorCode.UNSUPPORTED_EXPLICIT_FILE),
    )
    notice_items = tuple(notices)
    for reason, code in notice_errors:
        notice = next((item for item in notice_items if item.reason == reason), None)
        if notice is None:
            continue
        if notice.path is None:
            raise DumpIrError(DumpIrErrorCode.TARGET_NOTICE_MISSING_PATH)
        raise DumpIrError(code, notice.path)


def _extract_documents(
    inputs: cabc.Iterable[CheckInput],
    document_spool: typ.IO[bytes],
) -> tuple[int, ...]:
    """Write each canonical document to a spool and retain its byte length."""
    document_lengths: list[int] = []
    for check_input in inputs:
        try:
            sourced = read_source(check_input)
        except SourceReadError as exc:
            raise DumpIrError(
                DumpIrErrorCode.CANNOT_READ,
                check_input.reported_path,
                exc.error,
            ) from exc
        try:
            result = engine.extract_document_result(
                sourced.source_text,
                model.Syntax.MARKDOWN,
                source_path=sourced.reported_path,
            )
        except (
            engine.BridgeExtractionError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as exc:
            raise DumpIrError(
                DumpIrErrorCode.CANNOT_EXTRACT,
                sourced.reported_path,
                exc,
            ) from exc
        if result.canonical_json is None:
            raise DumpIrError(
                DumpIrErrorCode.MISSING_IR,
                sourced.reported_path,
            )
        canonical_document = _canonical_bytes(result.canonical_json)
        _write_spool(document_spool, canonical_document)
        document_lengths.append(len(canonical_document))
    return tuple(document_lengths)


def _write_json_framing(
    output_spool: typ.IO[bytes],
    document_spool: typ.IO[bytes],
    document_lengths: tuple[int, ...],
) -> None:
    """Frame spooled canonical documents without reserialising their IR."""
    if len(document_lengths) == 1:
        _copy_document_spool(
            document_spool,
            output_spool,
            0,
            document_lengths[0],
        )
        return
    if not document_lengths:
        _write_spool(output_spool, b"[]\n")
        return
    _write_spool(output_spool, b"[")
    offset = 0
    for index, length in enumerate(document_lengths):
        if index:
            _write_spool(output_spool, b",")
        _copy_document_spool(document_spool, output_spool, offset, length)
        offset += length
    _write_spool(output_spool, b"]\n")


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
        _write_spool(output_spool, chunk)
        remaining -= len(chunk)


def _write_spool(spool: typ.IO[bytes], contents: bytes) -> None:
    """Write all bytes to a temporary spool or report an operational failure."""
    if spool.write(contents) != len(contents):
        raise DumpIrSpoolError(DumpIrSpoolErrorCode.SHORT_JSON_SPOOL_WRITE)


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
            text_output.write(decoded)
    final_text = decoder.decode(b"", final=True)
    if final_text:
        text_output.write(final_text)


def _copy_binary_chunks(spool: typ.IO[bytes], output: typ.BinaryIO) -> None:
    """Stream binary output in bounded chunks and flush it when supported."""
    while chunk := spool.read(_OUTPUT_CHUNK_SIZE):
        if output.write(chunk) != len(chunk):
            raise DumpIrSpoolError(DumpIrSpoolErrorCode.SHORT_STDOUT_WRITE)
    output.flush()
