"""Filesystem target queries used by the discovery facade.

This internal module classifies explicit targets, walks source directories,
and retains path-level failures without owning cross-target aggregation.
"""

import dataclasses as dc
import enum
import os
import pathlib
import stat
import typing as typ

from stilyagi import model
from stilyagi.discovery_results import (
    DiscoveredFile,
    DiscoveryFailure,
    DiscoveryNotice,
    SkippedCandidateReason,
)

_EXTENSION_SYNTAXES: typ.Final[cabc.Mapping[str, model.Syntax]] = {
    "md": model.Syntax.MARKDOWN,
    "markdown": model.Syntax.MARKDOWN,
    "mdc": model.Syntax.MARKDOWN,
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

if typ.TYPE_CHECKING:
    import collections.abc as cabc


@dc.dataclass(frozen=True, slots=True)
class _TargetDiscovery:
    """Candidates and operational context collected from one target."""

    files: tuple[DiscoveredFile, ...] = ()
    skipped_candidates: tuple[tuple[SkippedCandidateReason, pathlib.Path], ...] = ()
    notices: tuple[DiscoveryNotice, ...] = ()
    failures: tuple[DiscoveryFailure, ...] = ()


class _PathKind(enum.Enum):
    """Filesystem kinds relevant to explicit discovery targets."""

    MISSING = enum.auto()
    FILE = enum.auto()
    DIRECTORY = enum.auto()
    SYMLINK_DIRECTORY = enum.auto()
    UNSUPPORTED = enum.auto()


def _discover_target(target: pathlib.Path | str) -> _TargetDiscovery:
    """Expand one requested target and retain any expansion failure."""
    raw_target_path = pathlib.Path(target)
    try:
        target_path = raw_target_path.expanduser()
    except (OSError, RuntimeError) as error:
        return _TargetDiscovery(
            failures=(DiscoveryFailure(path=raw_target_path, error=error),),
        )
    return _candidates_for_target(target_path)


def _candidates_for_target(
    target_path: pathlib.Path,
) -> _TargetDiscovery:
    """Return registered candidates and skipped candidate paths for one target."""
    try:
        path_kind = _path_kind(target_path)
        if path_kind is _PathKind.SYMLINK_DIRECTORY:
            return _TargetDiscovery(
                skipped_candidates=(
                    ("symlinked_directory_target", target_path.resolve()),
                ),
                notices=(DiscoveryNotice("symlinked_directory_target", target_path),),
            )
        if path_kind is _PathKind.FILE:
            return _discover_file_target(target_path)
        if path_kind is _PathKind.DIRECTORY:
            return _discover_directory_target(target_path)
    except (OSError, RuntimeError) as error:
        return _TargetDiscovery(
            failures=(DiscoveryFailure(path=target_path, error=error),),
        )
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

    def record_discovery_error(
        path: pathlib.Path,
        error: OSError | RuntimeError,
    ) -> None:
        """Retain one path probe, resolution or traversal failure."""
        failures.append(DiscoveryFailure(path=path, error=error))

    def record_walk_error(error: OSError) -> None:
        """Retain the path and error supplied by ``Path.walk``."""
        failed_path = (
            target_path
            if error.filename is None
            else pathlib.Path(os.fsdecode(error.filename))
        )
        record_discovery_error(failed_path, error)

    try:
        for root_path, dirnames, filenames in target_path.walk(
            follow_symlinks=False,
            on_error=record_walk_error,
        ):
            _prune_ignored_directories(root_path, dirnames, record_discovery_error)
            relative_root = pathlib.PurePosixPath(
                root_path.relative_to(target_path).as_posix()
            )
            reported_root = reported_base / relative_root
            for filename in sorted(filenames):
                candidate = root_path / filename
                candidate_result = _discover_directory_candidate(
                    candidate,
                    (reported_root / filename).as_posix(),
                )
                discovered_files.extend(candidate_result.files)
                failures.extend(candidate_result.failures)
                for reason, skipped_path in candidate_result.skipped_candidates:
                    skipped_candidates.setdefault(reason, set()).add(skipped_path)
    except (OSError, RuntimeError) as error:
        record_discovery_error(target_path, error)
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


def _discover_directory_candidate(
    candidate: pathlib.Path,
    reported_path: str,
) -> _TargetDiscovery:
    """Classify one walked file as discovered, skipped or failed."""
    try:
        path_kind = _path_kind(candidate)
        resolved_path = candidate.resolve()
    except (OSError, RuntimeError) as error:
        return _TargetDiscovery(
            failures=(DiscoveryFailure(path=candidate, error=error),),
        )

    if path_kind is _PathKind.SYMLINK_DIRECTORY:
        # Path.walk exposes non-followed directory symlinks as filenames.
        return _TargetDiscovery(
            skipped_candidates=(("symlinked_directory_target", resolved_path),),
        )

    if path_kind is _PathKind.MISSING:
        return _TargetDiscovery()
    if path_kind is not _PathKind.FILE:
        return _TargetDiscovery(
            skipped_candidates=(("unsupported_candidate_type", resolved_path),),
        )

    syntax = syntax_for_path(candidate)
    if syntax is None:
        return _TargetDiscovery(
            skipped_candidates=(("unregistered_candidate", resolved_path),),
        )

    return _TargetDiscovery(
        files=(
            DiscoveredFile(
                reported_path=reported_path,
                resolved_path=resolved_path,
                syntax=syntax,
            ),
        ),
    )


def _prune_ignored_directories(
    root_path: pathlib.Path,
    dirnames: list[str],
    record_error: cabc.Callable[[pathlib.Path, OSError | RuntimeError], None],
) -> None:
    """Remove noise directories and symlinked directories from ``dirnames``."""
    retained_dirnames: list[str] = []
    for dirname in dirnames:
        directory = root_path / dirname
        if dirname in _IGNORED_DIRECTORY_NAMES:
            continue
        try:
            is_symlink = stat.S_ISLNK(directory.lstat().st_mode)
        except OSError as error:
            if not _is_missing_path_error(error):
                record_error(directory, error)
            continue
        if not is_symlink:
            retained_dirnames.append(dirname)
    dirnames[:] = retained_dirnames


def _path_kind(path: pathlib.Path) -> _PathKind:
    """Classify a path with explicit stat errors rather than lossy predicates."""
    try:
        link_mode = path.lstat().st_mode
    except OSError as error:
        if _is_missing_path_error(error):
            return _PathKind.MISSING
        raise

    is_symlink = stat.S_ISLNK(link_mode)
    try:
        target_mode = path.stat().st_mode if is_symlink else link_mode
    except OSError as error:
        if _is_missing_path_error(error):
            return _PathKind.MISSING
        raise

    return _kind_from_modes(target_mode, is_symlink=is_symlink)


def _kind_from_modes(target_mode: int, *, is_symlink: bool) -> _PathKind:
    """Map a target mode and link state to the discovery path kind."""
    if stat.S_ISDIR(target_mode):
        return _PathKind.SYMLINK_DIRECTORY if is_symlink else _PathKind.DIRECTORY
    if stat.S_ISREG(target_mode):
        return _PathKind.FILE
    return _PathKind.UNSUPPORTED


def _is_missing_path_error(error: OSError) -> bool:
    """Return whether an error represents a missing or unusable path prefix."""
    return isinstance(error, (FileNotFoundError, NotADirectoryError))


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
