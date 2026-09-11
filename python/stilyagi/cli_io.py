"""Read byte-faithful check inputs and report command-line file failures."""

import dataclasses as dc
import logging
import sys
import typing as typ

from stilyagi.cli_args import PROGRAM_NAME

if typ.TYPE_CHECKING:
    import pathlib

_LOGGER = logging.getLogger(__name__)


@dc.dataclass(frozen=True, slots=True)
class CheckInput:
    """One resolved `check` input, from disk or standard input."""

    reported_path: str
    resolved_path: pathlib.Path
    source_text: str | None = None
    source_bytes: bytes | None = None


def read_source(check_input: CheckInput) -> CheckInput | None:
    """Return one input with its source bytes and decoded text populated."""
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
    except (
        FileNotFoundError,
        IsADirectoryError,
        PermissionError,
        UnicodeDecodeError,
    ) as exc:
        report_file_error(check_input.resolved_path, exc)
        return None
    return dc.replace(
        check_input,
        source_bytes=source_bytes,
        source_text=source_text,
    )


def report_file_error(path: pathlib.Path, error: Exception) -> None:
    """Print and log a human-readable file read failure."""
    message = f"failed to read {path.as_posix()}: {error}"
    _LOGGER.warning("%s", message)
    print(f"{PROGRAM_NAME} check: {message}", file=sys.stderr)


def report_check_error(path: pathlib.Path | None, error: Exception) -> None:
    """Print and log a human-readable extraction or configuration failure."""
    if path is None:
        message = str(error)
    else:
        message = f"failed to check {path.as_posix()}: {error}"
    _LOGGER.warning("%s", message)
    print(f"{PROGRAM_NAME} check: {message}", file=sys.stderr)
