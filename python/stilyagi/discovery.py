r"""Deterministic source discovery helpers for the check command.

This internal module finds registered source inputs from command-line targets.
It keeps both the command-line-relative reported path and resolved filesystem
path so later stages can attribute diagnostics without losing stable ordering.

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

import dataclasses as dc
import os
import pathlib
import typing as typ

from stilyagi import model
from stilyagi.discovery_results import (
    DiscoveredFile,
    DiscoveryFailure,
    DiscoveryNotice,
    DiscoveryResult,
    SkippedCandidateCount,
    SkippedCandidateReason,
    _build_discovery_result,
)

_EXTENSION_SYNTAXES: typ.Final[cabc.Mapping[str, model.Syntax]] = {
    "md": model.Syntax.MARKDOWN,
    "markdown": model.Syntax.MARKDOWN,
    "py": model.Syntax.PYTHON_DOCSTRING,
    "rs": model.Syntax.RUST_DOC_COMMENT,
}
# Keep this aligned with `MD_FILES_FIND` in the Makefile, which defines the
# repository's established build-noise boundary for source walks.
_IGNORED_DIRECTORY_NAMES = frozenset({
    ".git",
    ".eggs",
    ".mypy_cache",
    ".nox",
    ".pytest_cache",
    ".ruff_cache",
    ".stilyagi_cache",
    ".tox",
    ".uv-cache",
    ".uv-tools",
    ".vtcode",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "site-packages",
    "target",
    ".venv",
    ".venv-release-smoke",
})

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

    from stilyagi.config import StilyagiConfig


@dc.dataclass(frozen=True, slots=True)
class _TargetDiscovery:
    """Candidates and operational context collected from one target."""

    files: tuple[DiscoveredFile, ...] = ()
    skipped_candidates: tuple[tuple[SkippedCandidateReason, pathlib.Path], ...] = ()
    notices: tuple[DiscoveryNotice, ...] = ()
    failures: tuple[DiscoveryFailure, ...] = ()


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
        collapsed to one entry. If traversal fails, the first retained
        OSError is raised because this files-only wrapper cannot represent
        partial results and failures together.

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
    r"""Discover registered files and return skips, notices and walk failures.

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
        bounded notices and directory traversal errors. A candidate is skipped
        when it has no registered extractor or when it is a symlinked
        directory target. Skips are counted once per distinct file, even when
        several targets overlap; missing targets are ignored and not counted.
        Traversal failures are retained with any successfully discovered files.

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
        target_path = pathlib.Path(target).expanduser()
        target_result = _candidates_for_target(target_path)
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


def _candidates_for_target(
    target_path: pathlib.Path,
) -> _TargetDiscovery:
    """Return registered candidates and skipped candidate paths for one target."""
    if _is_symlinked_directory(target_path):
        return _TargetDiscovery(
            skipped_candidates=(("symlinked_directory_target", target_path.resolve()),),
            notices=(DiscoveryNotice("symlinked_directory_target", target_path),),
        )
    if target_path.is_file():
        return _discover_file_target(target_path)
    if target_path.is_dir():
        return _discover_directory_target(target_path)
    return _TargetDiscovery(
        notices=(DiscoveryNotice("missing_or_unsupported_target", target_path),),
    )


def _discover_file_target(target_path: pathlib.Path) -> _TargetDiscovery:
    """Classify one explicit file target as registered or skipped."""
    discovered_file = _discover_explicit_file(target_path)
    if discovered_file is not None:
        return _TargetDiscovery(files=(discovered_file,))
    return _TargetDiscovery(
        skipped_candidates=(("unregistered_candidate", target_path.resolve()),),
        notices=(DiscoveryNotice("unregistered_explicit_file", target_path),),
    )


def _discover_directory_target(target_path: pathlib.Path) -> _TargetDiscovery:
    """Skip ignored directory targets before walking any descendants."""
    if target_path.name in _IGNORED_DIRECTORY_NAMES:
        return _TargetDiscovery()
    return _discover_directory(target_path)


def _discover_explicit_file(target_path: pathlib.Path) -> DiscoveredFile | None:
    """Return one explicitly requested file with a registered syntax."""
    syntax = syntax_for_path(target_path)
    if syntax is None:
        return None
    return DiscoveredFile(
        reported_path=target_path.as_posix(),
        resolved_path=target_path.resolve(),
        syntax=syntax,
    )


def _discover_directory(
    target_path: pathlib.Path,
) -> _TargetDiscovery:
    """Return directory source candidates and skipped candidate paths."""
    reported_base = pathlib.PurePosixPath(target_path.as_posix())
    discovered_files: list[DiscoveredFile] = []
    skipped_candidates: dict[SkippedCandidateReason, set[pathlib.Path]] = {}
    failures: list[DiscoveryFailure] = []

    def record_walk_error(error: OSError) -> None:
        """Retain the path and error supplied by ``Path.walk``."""
        failed_path = (
            target_path
            if error.filename is None
            else pathlib.Path(os.fsdecode(error.filename))
        )
        failures.append(DiscoveryFailure(path=failed_path, error=error))

    for root_path, dirnames, filenames in target_path.walk(
        follow_symlinks=False,
        on_error=record_walk_error,
    ):
        _prune_ignored_directories(root_path, dirnames)
        relative_root = pathlib.PurePosixPath(
            root_path.relative_to(target_path).as_posix()
        )
        reported_root = reported_base / relative_root
        for filename in sorted(filenames):
            candidate = root_path / filename
            if _is_symlinked_directory(candidate):
                # Path.walk exposes non-followed directory symlinks as filenames.
                skipped_candidates.setdefault("symlinked_directory_target", set()).add(
                    candidate.resolve()
                )
                continue
            syntax = syntax_for_path(candidate)
            if syntax is None:
                skipped_candidates.setdefault("unregistered_candidate", set()).add(
                    candidate.resolve()
                )
                continue
            discovered_files.append(
                DiscoveredFile(
                    reported_path=(reported_root / filename).as_posix(),
                    resolved_path=candidate.resolve(),
                    syntax=syntax,
                )
            )
    return _TargetDiscovery(
        files=tuple(discovered_files),
        skipped_candidates=tuple(
            (reason, candidate)
            for reason in sorted(skipped_candidates)
            for candidate in sorted(
                skipped_candidates[reason], key=lambda path: path.as_posix()
            )
        ),
        failures=tuple(failures),
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


def _prune_ignored_directories(
    root_path: pathlib.Path,
    dirnames: list[str],
) -> None:
    """Remove noise directories and symlinked directories from ``dirnames``."""
    dirnames[:] = [
        dirname
        for dirname in dirnames
        if not _should_skip_directory(root_path / dirname)
    ]


def _should_skip_directory(directory: pathlib.Path) -> bool:
    """Return ``True`` when a child directory should not be traversed."""
    return directory.name in _IGNORED_DIRECTORY_NAMES or directory.is_symlink()


def _is_symlinked_directory(target_path: pathlib.Path) -> bool:
    """Return ``True`` when the supplied target is a symlinked directory."""
    return target_path.is_symlink() and target_path.is_dir()


def syntax_for_path(path: pathlib.Path) -> model.Syntax | None:
    """Return the registered syntax selected by a path's final suffix.

    Parameters
    ----------
    path:
        Path whose final suffix selects the extractor.

    Returns
    -------
    model.Syntax | None
        The registered syntax, or ``None`` when the final suffix has no
        extractor. Only the final suffix is matched, and the match is
        case-insensitive, so ``notes.py.txt`` resolves through ``.txt`` and
        is not discovered as a Python source.

    Examples
    --------
    >>> from pathlib import Path
    >>> syntax_for_path(Path("src/app.py")).value
    'python_docstring'
    >>> syntax_for_path(Path("src/app.rs")).value
    'rust_doc_comment'
    >>> syntax_for_path(Path("src/not-source.py.txt")) is None
    True
    """
    extension = path.suffix.lower().removeprefix(".")
    return _EXTENSION_SYNTAXES.get(extension)


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
