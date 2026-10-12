r"""Deterministic source discovery helpers for the check command.

This module exposes source-discovery queries and aggregates their structured
results across command-line targets. Filesystem probing and directory walking
live in :mod:`stilyagi.discovery_targets`.

Example
-------
>>> import pathlib
>>> import tempfile
>>> from stilyagi import config
>>> with tempfile.TemporaryDirectory() as directory:
...     note = pathlib.Path(directory) / "notes.md"
...     _ = note.write_text("# Notes", encoding="utf-8")
...     files = discover_files([note], config.StilyagiConfig())
...     files[0].resolved_path.name
'notes.md'
"""

import typing as typ

from stilyagi.discovery_results import (
    DiscoveredFile,
    DiscoveryFailure,
    DiscoveryNotice,
    DiscoveryResult,
    SkippedCandidateCount,
    SkippedCandidateReason,
    _build_discovery_result,
)
from stilyagi.discovery_targets import (
    _discover_target,
    syntax_for_path,
)

__all__ = [
    "DiscoveredFile",
    "DiscoveryFailure",
    "DiscoveryNotice",
    "DiscoveryResult",
    "SkippedCandidateCount",
    "discover_files",
    "discover_files_with_summary",
    "syntax_for_path",
]

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    import pathlib

    from stilyagi.config import StilyagiConfig


def discover_files(
    targets: cabc.Iterable[pathlib.Path | str],
    config: StilyagiConfig,
) -> list[DiscoveredFile]:
    r"""Return registered source files discovered from the supplied targets.

    Explicit registered files are included. Directory targets recurse
    deterministically, skip known build-noise directories, and do not follow
    symlinked directories.

    Parameters
    ----------
    targets:
        Command-line targets to inspect.
    config:
        Resolved Stilyagi configuration. The discovery layer currently only
        uses it to return a notice when ``respect_gitignore`` is accepted but
        not yet enforced.

    Returns
    -------
    list[DiscoveredFile]
        Registered files sorted by resolved path, with duplicate resolved paths
        collapsed to one entry. If path expansion, metadata lookup, path
        resolution or traversal fails, the first retained ``OSError`` or
        ``RuntimeError`` is raised because this files-only wrapper cannot
        represent partial results and failures together.

    Examples
    --------
    >>> import pathlib
    >>> import tempfile
    >>> from stilyagi import config
    >>> with tempfile.TemporaryDirectory() as directory:
    ...     note = pathlib.Path(directory) / "notes.md"
    ...     _ = note.write_text("# Notes", encoding="utf-8")
    ...     files = discover_files([note], config.StilyagiConfig())
    ...     files[0].resolved_path.name
    'notes.md'
    """
    result = discover_files_with_summary(targets, config)
    if result.failures:
        raise result.failures[0].error
    return list(result.files)


def discover_files_with_summary(
    targets: cabc.Iterable[pathlib.Path | str],
    config: StilyagiConfig,
) -> DiscoveryResult:
    r"""Discover registered files and return skips, notices and failures.

    This query performs no logging. Callers own reporting and exit policy.

    Parameters
    ----------
    targets:
        Command-line targets to inspect.
    config:
        Resolved Stilyagi configuration. Discovery currently only uses it to
        return a notice that ``respect_gitignore`` is accepted but not yet
        enforced.

    Returns
    -------
    DiscoveryResult
        Registered files sorted by resolved path, with duplicate resolved
        paths collapsed to one entry, plus the count of skipped candidates,
        bounded notices and structured filesystem errors. Path-expansion,
        metadata-lookup, path-resolution and directory-traversal failures are
        retained with any successfully discovered files; their errors are
        ``OSError`` or ``RuntimeError`` instances. Runtime errors include an
        unresolved home directory during expansion and a symlink loop during
        resolution. A candidate is skipped when it has no registered extractor
        or when it is a symlinked directory target. Skips are counted once per
        distinct file, even when several targets overlap; missing targets are
        ignored and not counted.

    Examples
    --------
    >>> import os
    >>> import tempfile
    >>> from pathlib import Path
    >>> from stilyagi import config
    >>> cwd = os.getcwd()
    >>> tmp = tempfile.TemporaryDirectory()
    >>> os.chdir(tmp.name)
    >>> _ = Path("notes.md").write_text("# Notes\\n", encoding="utf-8")
    >>> _ = Path("data.json").write_text("{}", encoding="utf-8")
    >>> result = discover_files_with_summary([Path(".")], config.StilyagiConfig())
    >>> (result.files[0].reported_path, result.skipped_files)
    ('notes.md', 1)
    >>> os.chdir(cwd)
    >>> tmp.cleanup()
    """
    discovered: dict[pathlib.Path, DiscoveredFile] = {}
    skipped_candidates: dict[SkippedCandidateReason, set[pathlib.Path]] = {}
    notices: list[DiscoveryNotice] = []
    if config.respect_gitignore:
        notices.append(DiscoveryNotice("respect_gitignore_unenforced"))
    notice_set = set(notices)
    failures: list[DiscoveryFailure] = []
    for target in targets:
        target_result = _discover_target(target)
        for reason, candidate_path in target_result.skipped_candidates:
            skipped_candidates.setdefault(reason, set()).add(candidate_path)
        failures.extend(target_result.failures)
        for notice in target_result.notices:
            _record_notice(notices, notice_set, notice)
        for candidate in target_result.files:
            _record_candidate(discovered, candidate)

    return _build_discovery_result(
        discovered,
        skipped_candidates,
        notices,
        failures,
    )


def _record_notice(
    notices: list[DiscoveryNotice],
    notice_set: set[DiscoveryNotice],
    notice: DiscoveryNotice,
) -> None:
    """Append one notice while suppressing repeated target messages."""
    if notice not in notice_set:
        notice_set.add(notice)
        notices.append(notice)


def _record_candidate(
    discovered: dict[pathlib.Path, DiscoveredFile],
    candidate: DiscoveredFile | None,
) -> None:
    """Store one discovered file while keeping the best reported path."""
    if candidate is None:
        return
    existing = discovered.get(candidate.resolved_path)
    if existing is None or candidate.reported_path < existing.reported_path:
        discovered[candidate.resolved_path] = candidate
