"""Move check bytes across the command boundary without altering them.

Both directions of the CLI's byte traffic live here. `read_source` and
`read_stdin_bytes` bring a document in exactly as it is stored, with no newline
translation and no re-encoding; `write_artefact` sends a produced document back
out under the same constraint. Keeping the two halves in one module is what
makes the fidelity claim checkable in a single place: a reader that is faithful
and a writer that is not would still lose bytes, and neither module would look
wrong on its own.

The failures this boundary reports are *expected* ones -- an unreadable file, a
document that is not UTF-8 -- and `report_check_error` is the command's default
reporter for them. Nothing here chooses an exit status.
"""

import dataclasses as dc
import logging
import pathlib
import sys
import typing as typ

from stilyagi.cli_args import PROGRAM_NAME

__all__ = [
    "CheckInput",
    "SourceReadError",
    "SourcedInput",
    "read_source",
    "read_stdin_bytes",
    "report_check_error",
    "stdin_check_input",
    "write_artefact",
]

_LOGGER = logging.getLogger(__name__)


@dc.dataclass(frozen=True, slots=True)
class CheckInput:
    """One resolved `check` input, from disk or standard input.

    Either payload field may still be absent: discovery produces paths, while
    the stdin path supplies bytes. `read_source` turns one of these into a
    `SourcedInput`, which is the shape the pipeline works with.

    `from_stdin` records where the bytes came from, because `--stdin-filename`
    makes a stream input name a real file on disk. Without this flag the fix
    writer would resolve that name and overwrite the very file the user
    redirected into the command.
    """

    reported_path: str
    resolved_path: pathlib.Path
    source_text: str | None = None
    source_bytes: bytes | None = None
    from_stdin: bool = False


@dc.dataclass(frozen=True, slots=True)
class SourcedInput:
    """One check input whose bytes and decoded text are both known.

    `read_source` returns this rather than an optional-bearing `CheckInput`, so
    a caller cannot receive a value that has passed the read but still lacks
    the text every later stage needs.
    """

    reported_path: str
    resolved_path: pathlib.Path
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

    Reading, decoding, and the supplied-text fallback all happen here, so every
    check input reaches the pipeline through one byte-faithful path: bytes are
    used exactly as read, with no newline translation, and the decoded text is
    produced from those same bytes.

    Returns
    -------
    SourcedInput
        The input carrying both ``source_bytes`` and ``source_text``, so no
        caller has to re-check either for absence.

    Raises
    ------
    SourceReadError
        The input's path could not be read, its bytes are not UTF-8, or a
        supplied ``source_text`` could not be encoded. The original OS or
        decoding error is retained on the exception.

    Examples
    --------
    >>> read_source(
    ...     CheckInput(
    ...         reported_path="notes.md",
    ...         resolved_path=pathlib.Path("unused"),
    ...         source_text="# Notes\\n",
    ...     )
    ... ).source_bytes
    b'# Notes\\n'
    """
    try:
        source_bytes = check_input.source_bytes
        source_text = check_input.source_text
        if source_bytes is None:
            source_bytes = (
                source_text.encode("utf-8")
                if source_text is not None
                else check_input.resolved_path.read_bytes()
            )
        if source_text is None:
            source_text = source_bytes.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        # OSError covers the whole family a read can raise -- missing files,
        # directories, permissions, and the rest -- rather than the four
        # subclasses that were enumerated before.
        raise SourceReadError(check_input.resolved_path, exc) from exc
    return SourcedInput(
        reported_path=check_input.reported_path,
        resolved_path=check_input.resolved_path,
        source_bytes=source_bytes,
        source_text=source_text,
        from_stdin=check_input.from_stdin,
    )


def stdin_check_input(stdin_filename: str | None) -> CheckInput:
    """Build the check input that consumes standard input.

    The input is flagged as coming from the stream even when
    ``stdin_filename`` names a real file, because `--stdin-filename` is only a
    reporting identity: the bytes under that name were never read from it.

    Returns
    -------
    CheckInput
        The input carrying the piped bytes, flagged ``from_stdin`` so no later
        stage can mistake it for a file it is allowed to overwrite.
    """
    reported_path = (
        pathlib.Path(stdin_filename).as_posix() if stdin_filename else "<stdin>"
    )
    resolved_path = (
        pathlib.Path(stdin_filename) if stdin_filename else pathlib.Path("<stdin>")
    )
    return CheckInput(
        reported_path=reported_path,
        resolved_path=resolved_path,
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
    >>> write_artefact(sink, "caf\\u00e9\\r\\n".encode())
    >>> sink.getvalue() == "caf\\u00e9\\r\\n"
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
    """Print and log one expected command-line failure.

    This is the command boundary's default reporter. It distinguishes the two
    families of expected failure by type rather than by guessing from the
    message: a `SourceReadError` is a file that could not be read or decoded,
    while anything else is an extraction or configuration failure. Both are
    logged at warning level and echoed to standard error in the same
    `stilyagi check:` form, so the file errors and the check errors stay
    telling apart in a user's terminal.

    Parameters
    ----------
    path:
        The offending path, or ``None`` when the failure has no single file to
        blame, as when discovery or configuration fails before any file is
        known. A `SourceReadError` is attributed to the path on the exception
        itself, so this argument is not consulted in that case.
    error:
        The failure to report. A `SourceReadError` carries the underlying OS or
        decoding error, which is what the user needs to see.
    """
    if isinstance(error, SourceReadError):
        # The typed error already names its own path, and that one is not
        # None-able, so it is both the more accurate source and the one the
        # type checker can follow.
        message = f"failed to read {error.path.as_posix()}: {error.error}"
    elif path is None:
        message = str(error)
    else:
        message = f"failed to check {path.as_posix()}: {error}"
    _LOGGER.warning("%s", message)
    print(f"{PROGRAM_NAME} check: {message}", file=sys.stderr)
