"""Check-command input and result shapes shared between CLI stages.

These records are the internal currency of one `stilyagi check` run: discovery
produces :class:`CheckInput` values, and the per-file check loop returns
:class:`FileCheckResult` values that accumulate into a
:class:`DiscoveryOutcome`.
"""

import dataclasses as dc
import logging
import typing as typ

from stilyagi.cli_args import PROGRAM_NAME

if typ.TYPE_CHECKING:
    import pathlib

    from stilyagi import diagnostics, discovery, model

__all__ = [
    "CheckInput",
    "DiscoveryInputs",
    "DiscoveryOutcome",
    "FileCheckResult",
    "report_check_error",
    "report_file_error",
]


@dc.dataclass(frozen=True, slots=True)
class CheckInput:
    """One resolved `check` input, from disk or standard input.

    Parameters
    ----------
    reported_path:
        The command-line-relative path used in every user-facing message.
    resolved_path:
        The filesystem path used to read the source. Standard-input runs use
        the reported name as a placeholder because there is no real file.
    syntax:
        The registered extractor syntax selected for this input.
    source_text:
        Pre-read source text, used by standard input; file-backed inputs
        leave this empty and read :attr:`resolved_path` lazily.

    Examples
    --------
    >>> import pathlib
    >>> CheckInput(
    ...     reported_path="docs/notes.md",
    ...     resolved_path=pathlib.Path("docs/notes.md"),
    ...     syntax=model.Syntax.MARKDOWN,
    ... ).reported_path
    'docs/notes.md'
    """

    reported_path: str
    resolved_path: pathlib.Path
    syntax: model.Syntax
    source_text: str | None = None

    @classmethod
    def from_discovered(
        cls,
        file: discovery.DiscoveredFile,
        *,
        source_text: str | None = None,
    ) -> typ.Self:
        """Convert one discovery result into a file-backed check input."""
        return cls(
            reported_path=file.reported_path,
            resolved_path=file.resolved_path,
            syntax=file.syntax,
            source_text=source_text,
        )


class DiscoveryInputs(typ.NamedTuple):
    """The discovered check inputs plus the skipped candidate count."""

    inputs: tuple[CheckInput, ...]
    skipped_files: int


class FileCheckResult(typ.NamedTuple):
    """The diagnostics and operational outcomes for one checked input."""

    diagnostics: list[diagnostics.Diagnostic]
    had_error: bool
    was_unreadable: bool


class DiscoveryOutcome(typ.NamedTuple):
    """The accumulated diagnostics and operational totals for one run."""

    diagnostics: list[diagnostics.Diagnostic]
    had_error: bool
    unreadable_files: int


_LOGGER = logging.getLogger(__name__)


def report_file_error(path: str, error: Exception) -> None:
    """Log a human-readable file read failure once.

    Parameters
    ----------
    path:
        The command-line-relative path used in every user-facing message.
    error:
        The read failure to explain.
    """
    message = f"{PROGRAM_NAME} check: failed to read {path}: {error}"
    _LOGGER.warning("%s", message)


def report_check_error(path: str | None, error: Exception) -> None:
    """Log a human-readable extraction or config failure once.

    Parameters
    ----------
    path:
        The command-line-relative path of the failing input, or ``None`` when
        the failure applies to the whole run.
    error:
        The operational failure to explain.
    """
    if path is None:
        message = f"{PROGRAM_NAME} check: {error}"
    else:
        message = f"{PROGRAM_NAME} check: failed to check {path}: {error}"
    _LOGGER.warning("%s", message)
