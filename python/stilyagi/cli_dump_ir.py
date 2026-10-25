"""Run the read-only command that emits Rust's canonical Markdown IR."""

import dataclasses as dc
import enum
import pathlib
import sys
import tempfile
import typing as typ

from stilyagi import config, discovery, engine, model
from stilyagi.cache.extraction import (
    CacheExtractionInput,
    CacheExtractionService,
    CacheServiceConfig,
)
from stilyagi.check_inputs import CheckInput
from stilyagi.check_targets import parse_target_operands
from stilyagi.cli_args import PACKAGE_VERSION
from stilyagi.cli_config import resolve_discovery_config
from stilyagi.cli_dump_ir_output import (
    _canonical_bytes,
    _copy_spool_to_output,
    _write_chunk,
    _write_json_framing,
)
from stilyagi.cli_io import SourceReadError, read_source, stdin_check_input

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from stilyagi.cli_args import DumpIrOptions


_SPOOL_MEMORY_LIMIT = 1024 * 1024


@dc.dataclass(frozen=True, slots=True)
class _ExtractionContext:
    """Hold fixed configuration and cache collaborators for one dump run."""

    options: DumpIrOptions
    resolver: config.ConfigResolver
    cache: CacheExtractionService


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
    extraction_cache = CacheExtractionService(
        CacheServiceConfig(
            invocation_cwd=pathlib.Path.cwd(),
            package_version=PACKAGE_VERSION,
            no_cache=options.no_cache,
        )
    )
    try:
        inputs = _discover_markdown_inputs(options, config_resolver)
        _write_dump_output(
            inputs,
            _ExtractionContext(options, config_resolver, extraction_cache),
            out_stream,
        )
    except (DumpIrError, config.ConfigError, OSError, ValueError) as exc:
        error_stream.write(f"stilyagi dump-ir: {exc}\n")
        return 2
    finally:
        extraction_cache.log_summary()
        extraction_cache.close()
    return 0


def _write_dump_output(
    inputs: cabc.Iterable[CheckInput],
    context: _ExtractionContext,
    output: typ.TextIO | typ.BinaryIO,
) -> None:
    """Spool every document before writing one complete JSON result."""
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
        document_lengths = _extract_documents(inputs, document_spool, context)
        _write_json_framing(output_spool, document_spool, document_lengths)
        output_spool.seek(0)
        _copy_spool_to_output(output_spool, output)


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
    context: _ExtractionContext,
) -> tuple[int, ...]:
    """Write each canonical document to a spool and retain its byte length."""
    document_lengths: list[int] = []
    for check_input in inputs:
        canonical_document = _extract_document(check_input, context)
        _write_chunk(document_spool, canonical_document)
        document_lengths.append(len(canonical_document))
    return tuple(document_lengths)


def _extract_document(
    check_input: CheckInput,
    context: _ExtractionContext,
) -> bytes:
    """Read, cache and serialize one canonical Markdown document."""
    try:
        sourced = read_source(check_input)
    except SourceReadError as exc:
        raise DumpIrError(
            DumpIrErrorCode.CANNOT_READ,
            check_input.reported_path,
            exc.error,
        ) from exc
    try:
        effective_config = context.resolver.resolve_config_for_path(
            sourced.resolved_path,
            cli_overrides=None,
            explicit_config=context.options.explicit_config or None,
            isolated=context.options.isolated,
        )
        result = context.cache.extract(
            CacheExtractionInput(
                source_text=sourced.source_text,
                syntax=model.Syntax.MARKDOWN,
                reported_identity=sourced.reported_path,
                effective_config=effective_config,
                cache_dir=effective_config.cache_dir,
                from_stdin=sourced.from_stdin,
            )
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
    return _canonical_bytes(result.canonical_json)
