"""Structured records returned by source discovery.

Keeping files, notices and traversal failures together lets discovery remain a
query while the command layer owns user-facing logging and exit policy.
"""

import dataclasses as dc
import typing as typ

if typ.TYPE_CHECKING:
    import pathlib

    from stilyagi import model


@dc.dataclass(frozen=True, slots=True)
class DiscoveredFile:
    """One discovered source file and its selected extractor syntax.

    Parameters
    ----------
    reported_path:
        The command-line-relative POSIX path used for user-facing reporting.
    resolved_path:
        The fully resolved filesystem path used for de-duplication and stable
        ordering.
    syntax:
        The registered extractor syntax selected from the final file suffix.
    """

    reported_path: str
    resolved_path: pathlib.Path
    syntax: model.Syntax


class DiscoveryNotice(typ.NamedTuple):
    """A bounded discovery event for the command layer to report.

    Attributes
    ----------
    reason:
        Fixed event category used to render a stable user-facing message.
    path:
        Target associated with the event, or ``None`` for configuration-wide
        information.
    """

    reason: typ.Literal[
        "respect_gitignore_unenforced",
        "symlinked_directory_target",
        "missing_or_unsupported_target",
        "unregistered_explicit_file",
    ]
    path: pathlib.Path | None = None


class DiscoveryFailure(typ.NamedTuple):
    """One directory traversal error that may leave discovery incomplete.

    Attributes
    ----------
    path:
        Path whose traversal failed, as supplied by ``Path.walk`` when known.
    error:
        The original operating-system error reported by the walk callback.
    """

    path: pathlib.Path
    error: OSError


type SkippedCandidateReason = typ.Literal[
    "unregistered_candidate",
    "symlinked_directory_target",
]


class SkippedCandidateCount(typ.NamedTuple):
    """Count distinct skipped source candidates for one fixed reason.

    Attributes
    ----------
    reason:
        Bounded category shared with the metrics and discovery contracts.
    count:
        Number of distinct candidate paths skipped for this reason.
    """

    reason: SkippedCandidateReason
    count: int


@dc.dataclass(frozen=True, slots=True)
class DiscoveryResult:
    """Files, skips, notices and traversal failures from one discovery pass.

    Parameters
    ----------
    files:
        Registered source files in deterministic resolved-path order.
    skipped_files:
        Distinct source candidates without a registered extractor, plus
        symlinked directory targets that discovery declined to traverse. A
        candidate appearing under several overlapping targets is counted once.
    skipped_by_reason:
        Distinct skipped candidate counts by the fixed reason vocabulary.
    notices:
        Informational or warning events for the caller to report after the
        query completes. Discovery itself does not log.
    failures:
        Directory traversal errors, retained alongside any files discovered
        before or after the failure.
    """

    files: tuple[DiscoveredFile, ...]
    skipped_files: int
    notices: tuple[DiscoveryNotice, ...] = ()
    failures: tuple[DiscoveryFailure, ...] = ()
    skipped_by_reason: tuple[SkippedCandidateCount, ...] = ()
