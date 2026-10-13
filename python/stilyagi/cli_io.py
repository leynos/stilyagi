"""Move check bytes across the command boundary without altering them.

Both directions of the CLI's byte traffic live here. `read_stdin_bytes` brings
a stream document in exactly as it is stored, with no newline translation and
no re-encoding; `write_artefact` sends a produced document back out under the
same constraint. Keeping the two halves in one module is what makes the
fidelity claim checkable in a single place: a reader that is faithful and a
writer that is not would still lose bytes, and neither module would look wrong
on its own.

Reading is syntax-aware because decoding is: a Python document declares its
own encoding in a PEP 263 cookie, and one that declares a non-UTF-8 codec is
legal source rather than an unreadable file. Honouring the declaration is part
of reading the bytes faithfully, not a separate concern bolted on afterwards,
so the dispatch lives here beside the byte handling it belongs to.

The failures this boundary reports are *expected* ones -- an unreadable file, a
document that is not decodable as its syntax requires -- and they travel as
`SourceReadError` so a caller decides what they mean for the process. Nothing
here chooses an exit status or counts a metric.
"""

import dataclasses as dc
import io
import pathlib
import sys
import tokenize
import typing as typ

from stilyagi import cli_log, model
from stilyagi.cli_args import PROGRAM_NAME

if typ.TYPE_CHECKING:
    from stilyagi.check_inputs import CheckInput

__all__ = [
    "SourceReadError",
    "SourcedInput",
    "read_source",
    "read_stdin_bytes",
    "report_check_error",
    "stdin_check_input",
    "write_artefact",
]


@dc.dataclass(frozen=True, slots=True)
class SourcedInput:
    """One check input whose bytes and decoded text are both known.

    The read boundary returns this rather than a still-optional
    :class:`~stilyagi.check_inputs.CheckInput`, so a caller cannot receive a
    value that has passed the read but still lacks the text every later stage
    needs. Carrying the bytes as well is what lets the fix planner splice the
    exact sequence its spans were derived from.

    ``syntax`` is carried alongside because the decode depends on it: a
    consumer holding the text cannot tell whether a Python encoding declaration
    was honoured, and a fix plan made from these offsets has to be re-read the
    same way it was read.
    """

    reported_path: str
    resolved_path: pathlib.Path
    syntax: model.Syntax
    source_bytes: bytes
    source_text: str
    from_stdin: bool = False


class SourceReadError(Exception):
    """One check input could not be read, decoded, or assembled.

    The read boundary raises this instead of logging or printing, so callers
    decide how a failed read is surfaced. The message is the human-readable
    reason on its own; the path is carried separately so a caller can attribute
    it without re-parsing the text.
    """

    def __init__(self, path: pathlib.Path, error: Exception) -> None:
        """Record the offending path and the underlying cause.

        Parameters
        ----------
        path:
            The input that could not be read, which callers use to attribute
            the failure without parsing the message.
        error:
            The original `OSError` or `UnicodeDecodeError` that caused the
            failure, retained so a reporter can show the user the real reason.
        """
        self.path = path
        self.error = error
        super().__init__(f"{path.as_posix()}: {error}")


def read_source(check_input: CheckInput) -> SourcedInput:
    r"""Return one input with its source bytes and decoded text populated.

    Reading, decoding, and the supplied-payload fallback all happen here, so
    every check input reaches the pipeline through one byte-faithful path:
    bytes are used exactly as read, with no newline translation, and the
    decoded text is produced from those same bytes.

    Returns
    -------
    SourcedInput
        The input carrying both ``source_bytes`` and ``source_text``, so no
        caller has to re-check either for absence.

    Raises
    ------
    SourceReadError
        The input's path could not be read, its bytes are not decodable as its
        syntax requires, or a supplied ``source_text`` could not be encoded.
        The original OS or decoding error is retained on the exception.

    Examples
    --------
    >>> from stilyagi.check_inputs import CheckInput
    >>> read_source(
    ...     CheckInput(
    ...         reported_path="notes.md",
    ...         resolved_path=pathlib.Path("unused"),
    ...         syntax=model.Syntax.MARKDOWN,
    ...         source_text="# Notes\\n",
    ...     )
    ... ).source_bytes
    b'# Notes\\n'
    """
    try:
        source_bytes, source_text = _supplied_payload(check_input)
        if source_bytes is None:
            source_bytes = check_input.resolved_path.read_bytes()
        if source_text is None:
            source_text = _decode(source_bytes, check_input)
    except (MemoryError, OSError, SyntaxError, UnicodeDecodeError) as exc:
        # `OSError` covers the whole family a read can raise -- missing files,
        # directories, permissions, and the rest. `SyntaxError` is here for the
        # encoding-declaration family: an unknown codec, or a BOM that
        # contradicts the cookie, is raised during tokenize detection and is a
        # read failure like any other.
        raise SourceReadError(check_input.resolved_path, exc) from exc
    return SourcedInput(
        reported_path=check_input.reported_path,
        resolved_path=check_input.resolved_path,
        syntax=check_input.syntax,
        source_bytes=source_bytes,
        source_text=source_text,
        from_stdin=check_input.from_stdin,
    )


def _supplied_payload(check_input: CheckInput) -> tuple[bytes | None, str | None]:
    """Return whatever payload the input already carries.

    A stream input arrives with its bytes, and a re-lint input may carry text
    alone. Encoding supplied text is itself fallible, so the pair is produced
    together rather than left to the caller to assemble.

    Returns
    -------
    tuple[bytes | None, str | None]
        The supplied bytes and text, either of which may still be absent.
    """
    source_bytes = check_input.source_bytes
    source_text = check_input.source_text
    if source_bytes is None and source_text is not None:
        return source_text.encode("utf-8"), source_text
    return source_bytes, source_text


def _decode(source_bytes: bytes, check_input: CheckInput) -> str:
    """Decode one document's bytes the way its registered syntax requires.

    `tokenize.detect_encoding` reads the declaration from the buffer rather
    than from a path, so a stream input -- whose ``resolved_path`` is only a
    reporting name -- decodes through the same detection a file would.

    Returns
    -------
    str
        The decoded source text.
    """
    if check_input.syntax is not model.Syntax.PYTHON_DOCSTRING:
        return source_bytes.decode("utf-8-sig")
    encoding, _ = tokenize.detect_encoding(io.BytesIO(source_bytes).readline)
    return source_bytes.decode(encoding)


def stdin_check_input(
    stdin_filename: str | None,
    syntax: model.Syntax,
) -> CheckInput:
    """Build the check input that consumes standard input.

    The input is flagged as coming from the stream even when
    ``stdin_filename`` names a real file, because `--stdin-filename` is only a
    reporting identity: the bytes under that name were never read from it.

    Parameters
    ----------
    stdin_filename:
        The reporting name for the piped bytes, or ``None`` for ``<stdin>``.
    syntax:
        The registered extractor syntax the caller selected for the stream.

    Returns
    -------
    CheckInput
        The input carrying the piped bytes, flagged ``from_stdin`` so no later
        stage can mistake it for a file it is allowed to overwrite.
    """
    from stilyagi.check_inputs import CheckInput

    reported_path = (
        pathlib.Path(stdin_filename).as_posix() if stdin_filename else "<stdin>"
    )
    resolved_path = (
        pathlib.Path(stdin_filename) if stdin_filename else pathlib.Path("<stdin>")
    )
    return CheckInput(
        reported_path=reported_path,
        resolved_path=resolved_path,
        syntax=syntax,
        source_bytes=read_stdin_bytes(),
        from_stdin=True,
    )


def read_stdin_bytes() -> bytes:
    """Read standard input as bytes, retaining text-stream test compatibility.

    Returns
    -------
    bytes
        The bytes standard input supplied, read from the binary buffer when the
        stream has one and encoded from text otherwise.
    """
    buffer = getattr(sys.stdin, "buffer", None)
    if buffer is not None:
        return typ.cast("typ.BinaryIO", buffer).read()
    return sys.stdin.read().encode("utf-8")


def write_artefact(output: typ.TextIO, payload: bytes) -> None:
    r"""Write one production artefact without letting the stream transcode it.

    D-10 requires byte fidelity, and a text stream cannot supply it: default
    standard output translates ``\n`` to the platform separator, and it encodes
    with whatever the locale selected rather than UTF-8. The read and splice
    stages are byte-faithful, so a lossy final write would be the one place the
    pipeline broke a promise it had kept everywhere else.

    The binary buffer is preferred when the stream has one, which is the exact
    mirror of `read_stdin_bytes` reaching standard input the same way. A stream
    that is itself binary is written directly. Anything else -- an injected
    `StringIO`, which is the documented injection contract -- falls back to
    decoding, so the seam keeps working for callers that supply text.

    Parameters
    ----------
    output:
        The stream to write to. Standard output and pytest's capture both
        expose ``.buffer``; an injected text stream does not.
    payload:
        The exact bytes to write.

    Examples
    --------
    >>> import io
    >>> sink = io.StringIO()
    >>> write_artefact(sink, "café\r\n".encode())
    >>> sink.getvalue() == "café\r\n"
    True
    """
    buffer = getattr(output, "buffer", None)
    if buffer is not None:
        typ.cast("typ.BinaryIO", buffer).write(payload)
        return
    if isinstance(output, typ.BinaryIO):
        output.write(payload)
        return
    output.write(payload.decode("utf-8"))


def report_check_error(path: pathlib.Path | None, error: Exception) -> None:
    """Log one expected command-line failure and return ``None``.

    This is the command boundary's default reporter. It distinguishes the two
    families of expected failure by type rather than by guessing from the
    message: a `SourceReadError` is a file that could not be read or decoded,
    while anything else is an extraction or configuration failure. Both reach
    the user through the command logger, which
    `configure_command_warning_handler` gives a dedicated handler that does not
    propagate, so one emission survives a logging configuration that swallows
    root records.

    Parameters
    ----------
    path:
        The offending path, or ``None`` when the failure has no single file to
        blame, as when discovery or configuration fails before any file is
        known. It is the path *as the user spelled it*, which is the reporting
        identity every user-facing message uses, so a read failure inside a
        discovered directory names the file rather than the absolute path the
        walk happened to build. A `SourceReadError` that arrives without a path
        falls back to the one on the exception itself.
    error:
        The failure to report. A `SourceReadError` carries the underlying OS or
        decoding error, which is what the user needs to see.

    Examples
    --------
    >>> from unittest.mock import patch
    >>> with patch("stilyagi.cli_log.command_logger") as logged:
    ...     warning = logged.return_value.warning
    ...     result = report_check_error(
    ...         pathlib.Path("docs/guide.md"), RuntimeError("extractor failed")
    ...     )
    >>> result is None
    True
    >>> warning.call_args.args
    ('%s', 'stilyagi check: failed to check docs/guide.md: extractor failed')
    """
    if isinstance(error, SourceReadError):
        # The caller's path is the command-line-relative identity every other
        # message uses, so a walk failure names the same file the summary and
        # the diagnostics do. The typed error still carries the path the read
        # actually attempted, which is what a caller holding no display name
        # needs; that is why the two are separate values rather than one.
        blamed = error.path if path is None else path
        # The detail is bound first so the sentence stays one f-string the
        # formatter can wrap. Splitting it across two implicitly concatenated
        # f-strings makes the formatter join them back onto a line the linter
        # then rejects, so the two tools cannot both be satisfied that way.
        detail = f"{blamed.as_posix()}: {error.error}"
        message = f"{PROGRAM_NAME} check: failed to read {detail}"
    elif path is None:
        message = f"{PROGRAM_NAME} check: {error}"
    else:
        message = f"{PROGRAM_NAME} check: failed to check {path.as_posix()}: {error}"
    cli_log.command_logger().warning("%s", message)
