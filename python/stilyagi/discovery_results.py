"""Structured records returned by source discovery.

Keeping files, notices and filesystem failures together lets discovery remain
a query while the command layer owns user-facing logging and exit policy.
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
    """One structured filesystem error encountered during source discovery.

    Failures are retained in the discovery result instead of being logged by
    the query. The command layer reports them and treats their presence as an
    operational failure; files found before or after an error remain available.

    Attributes
    ----------
    path:
        Path whose expansion, metadata lookup, resolution or directory walk
        failed.
    error:
        Original ``OSError`` from a filesystem operation, or ``RuntimeError``
        raised when ``Path.expanduser`` cannot determine the home directory or
        ``Path.resolve`` detects a symlink loop.
    """

    path: pathlib.Path
    error: OSError | RuntimeError


type SkippedCandidateReason = typ.Literal[
    "unregistered_candidate",
    "symlinked_directory_target",
    "unsupported_candidate_type",
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
    """Files, skips, notices and filesystem failures from one discovery pass.

    Parameters
    ----------
    files:
        Registered regular source files in deterministic resolved-path order.
    skipped_files:
        Distinct source candidates without a registered extractor, unsupported
        filesystem types, and symlinked directory targets that discovery
        declined to traverse. A candidate appearing under several overlapping
        targets is counted once.
    skipped_by_reason:
        Distinct skipped candidate counts by the fixed reason vocabulary.
    notices:
        Informational or warning events for the caller to report after the
        query completes. Discovery itself does not log.
    failures:
        Structured path-expansion, metadata, path-resolution or directory-walk
        failures, retained alongside any files discovered before or after each
        failure. Errors are ``OSError`` or ``RuntimeError`` instances; runtime
        errors include an unresolved home directory or a symlink loop.
    """

    files: tuple[DiscoveredFile, ...]
    skipped_files: int
    notices: tuple[DiscoveryNotice, ...] = ()
    failures: tuple[DiscoveryFailure, ...] = ()
    skipped_by_reason: tuple[SkippedCandidateCount, ...] = ()


def _build_discovery_result(
    discovered: dict[pathlib.Path, DiscoveredFile],
    skipped_candidates: dict[SkippedCandidateReason, set[pathlib.Path]],
    notices: list[DiscoveryNotice],
    failures: list[DiscoveryFailure],
) -> DiscoveryResult:
    """Freeze accumulated discovery state into its deterministic result."""
    files = tuple(
        discovered[resolved_path]
        for resolved_path in sorted(discovered, key=lambda path: path.as_posix())
    )
    all_skipped_paths = {
        candidate_path
        for candidate_paths in skipped_candidates.values()
        for candidate_path in candidate_paths
    }
    return DiscoveryResult(
        files=files,
        skipped_files=len(all_skipped_paths),
        skipped_by_reason=tuple(
            SkippedCandidateCount(reason, len(skipped_candidates[reason]))
            for reason in sorted(skipped_candidates)
        ),
        notices=tuple(notices),
        failures=tuple(failures),
    )
