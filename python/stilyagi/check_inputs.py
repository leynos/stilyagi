"""Check-command input and result shapes shared between CLI stages.

These records are the internal currency of one `stilyagi check` run: discovery
produces :class:`CheckInput` values, and the per-file check loop returns
:class:`FileCheckResult` values that accumulate into a
:class:`DiscoveryOutcome`.

:class:`CheckInput` is the one input record for the whole command. It carries
both the discovered identity -- the reported path, the resolved path, and the
registered syntax -- and the optional pre-read payload a stream input arrives
with. Collapsing those into a single type is what lets one read boundary serve
every input regardless of where it came from, rather than adapting between two
records that describe the same thing.
"""

import dataclasses as dc
import logging
import typing as typ

from stilyagi import cli_log
from stilyagi.cli_args import PROGRAM_NAME

if typ.TYPE_CHECKING:
    import pathlib

    from stilyagi import diagnostics, discovery, model
    from stilyagi.discovery_results import SkippedCandidateCount
    from stilyagi.engine.fix_pipeline import PlannedFile

__all__ = [
    "CheckInput",
    "DiscoveryInputs",
    "DiscoveryOutcome",
    "FileCheckResult",
    "report_discovery_outcomes",
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
    source_bytes:
        Pre-read source bytes, used by standard input. Kept beside the text
        because the fix planner splices bytes and must see the exact sequence
        its offsets were derived from.
    from_stdin:
        Whether the bytes came from the stream rather than from
        :attr:`resolved_path`. `--stdin-filename` makes a stream input name a
        real file on disk, so without this flag a mutating run would resolve
        that name and overwrite the very file the user redirected into the
        command.

    Examples
    --------
    >>> import pathlib
    >>> from stilyagi import model
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
    source_bytes: bytes | None = None
    from_stdin: bool = False

    @classmethod
    def from_discovered(
        cls,
        file: discovery.DiscoveredFile,
        *,
        source_text: str | None = None,
    ) -> typ.Self:
        """Build an input from one file selected by source discovery.

        Parameters
        ----------
        file:
            Discovered path and registered syntax to carry into checking.
        source_text:
            Optional pre-read source. ``None`` keeps the input file-backed so
            the check stage reads it when needed.

        Returns
        -------
        CheckInput
            Input preserving the discovered paths and syntax.

        Examples
        --------
        >>> from pathlib import Path
        >>> from stilyagi import discovery, model
        >>> found = discovery.DiscoveredFile(
        ...     "docs/guide.md", Path("docs/guide.md"), model.Syntax.MARKDOWN
        ... )
        >>> check_input = CheckInput.from_discovered(found)
        >>> (check_input.reported_path, check_input.syntax.value)
        ('docs/guide.md', 'markdown')
        """
        return cls(
            reported_path=file.reported_path,
            resolved_path=file.resolved_path,
            syntax=file.syntax,
            source_text=source_text,
        )


class DiscoveryInputs(typ.NamedTuple):
    """Discovery data handed from target collection to the check command.

    Attributes
    ----------
    inputs:
        File or standard-input checks in deterministic discovery order.
    skipped_files:
        Number of distinct candidates excluded by the discovery policy.
    notices:
        Structured informational and warning events to report outside the
        discovery query.
    failures:
        Structured filesystem discovery failures, including path expansion,
        metadata lookup, path resolution and directory-walk errors. These may
        be ``OSError`` or ``RuntimeError`` instances (for example, an
        unresolved home directory or a symlink loop). They are reported by the
        command layer and make the run an operational failure even when some
        inputs were discovered.
    skipped_by_reason:
        Distinct skipped candidate counts grouped by fixed reason.

    Examples
    --------
    >>> result = DiscoveryInputs(inputs=(), skipped_files=2)
    >>> (result.inputs, result.skipped_files)
    ((), 2)
    """

    inputs: tuple[CheckInput, ...]
    skipped_files: int
    notices: tuple[discovery.DiscoveryNotice, ...] = ()
    failures: tuple[discovery.DiscoveryFailure, ...] = ()
    skipped_by_reason: tuple[SkippedCandidateCount, ...] = ()


class FileCheckResult(typ.NamedTuple):
    """Diagnostics, operational state, and any plan produced for one input.

    Attributes
    ----------
    diagnostics:
        Rule and extraction diagnostics produced for the input.
    had_error:
        Whether reading, extraction or configuration failed operationally.
    was_unreadable:
        Whether the source could not be read or decoded. Extraction and
        configuration failures set ``had_error`` without setting this field.
    planned:
        The file's fix plan, when the run asked for one and planning ran. It
        rides on the check result rather than being produced by a second pass
        so that `--fix` and `--diff` cannot disagree about what a plan is: both
        describe the document this one read produced.

    Examples
    --------
    >>> result = FileCheckResult(diagnostics=[], had_error=False, was_unreadable=False)
    >>> (result.had_error, result.was_unreadable, result.planned)
    (False, False, None)
    """

    diagnostics: list[diagnostics.Diagnostic]
    had_error: bool
    was_unreadable: bool
    planned: PlannedFile | None = None


class DiscoveryOutcome(typ.NamedTuple):
    """Aggregated diagnostics and operational totals for a check run.

    Attributes
    ----------
    diagnostics:
        Diagnostics accumulated across all inputs that could be checked.
    had_error:
        Whether reading, extraction or configuration failed for a checked
        input. ``run_check`` folds structured discovery failures into its final
        exit decision separately.
    unreadable_files:
        Number of inputs whose source could not be read or decoded; discovery
        failures do not increment this file count.

    Examples
    --------
    >>> outcome = DiscoveryOutcome(diagnostics=[], had_error=True, unreadable_files=1)
    >>> (outcome.had_error, outcome.unreadable_files)
    (True, 1)
    """

    diagnostics: list[diagnostics.Diagnostic]
    had_error: bool
    unreadable_files: int


_LOGGER = logging.getLogger(__name__)


def report_discovery_outcomes(discovery_inputs: DiscoveryInputs) -> bool:
    """Report structured discovery events and note incomplete traversal.

    Parameters
    ----------
    discovery_inputs:
        The completed discovery query result transferred to command handling.

    Returns
    -------
    bool
        ``True`` when any filesystem discovery failure was retained, otherwise
        ``False``.

    Examples
    --------
    >>> report_discovery_outcomes(DiscoveryInputs(inputs=(), skipped_files=0))
    False
    """
    for notice in discovery_inputs.notices:
        _report_discovery_notice(notice)

    for failure in discovery_inputs.failures:
        cli_log.command_logger().warning(
            "%s check: failed to discover %s: %s",
            PROGRAM_NAME,
            failure.path.as_posix(),
            failure.error,
        )
    return bool(discovery_inputs.failures)


def _report_discovery_notice(notice: discovery.DiscoveryNotice) -> None:
    """Log one notice according to the command's fixed reporting policy."""
    path = None if notice.path is None else notice.path.as_posix()
    if notice.reason == "respect_gitignore_unenforced":
        _LOGGER.info("respect-gitignore is accepted but not yet enforced")
    elif notice.reason == "symlinked_directory_target" and path is not None:
        cli_log.command_logger().warning("skipping symlinked directory target: %s", path)
    elif notice.reason == "unregistered_explicit_file" and path is not None:
        _LOGGER.info(
            "ignoring target without a registered extractor: %s",
            path,
        )
    elif notice.reason == "missing_or_unsupported_target" and path is not None:
        _LOGGER.info("ignoring missing or unsupported target: %s", path)
