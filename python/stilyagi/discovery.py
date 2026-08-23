"""Deterministic source discovery helpers for the check command.

This internal module finds registered source inputs from command-line targets.
It keeps both the command-line-relative reported path and resolved filesystem
path so later stages can attribute diagnostics without losing stable ordering.

Example
-------
>>> from pathlib import Path
>>> from stilyagi import config
>>> files = discover_files([Path("notes.md")], config.StilyagiConfig())
>>> [item.reported_path for item in files]
['notes.md']
"""

import dataclasses as dc
import logging
import pathlib
import typing as typ

from stilyagi import model

_LOGGER = logging.getLogger(__name__)
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
    "DiscoveryResult",
    "discover_files",
    "discover_files_with_summary",
    "syntax_for_path",
]

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from stilyagi.config import StilyagiConfig


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


@dc.dataclass(frozen=True, slots=True)
class DiscoveryResult:
    """The discovered files and source candidates skipped during one walk.

    Parameters
    ----------
    files:
        Registered source files in deterministic resolved-path order.
    skipped_files:
        Explicit or directory-contained files without a registered extractor,
        plus symlinked directory targets that discovery declined to traverse.
    """

    files: tuple[DiscoveredFile, ...]
    skipped_files: int


def discover_files(
    targets: cabc.Iterable[pathlib.Path | str],
    config: StilyagiConfig,
) -> list[DiscoveredFile]:
    """Return registered source files discovered from the supplied targets.

    Explicit registered files are included. Directory targets recurse
    deterministically, skip known build-noise directories, and do not follow
    symlinked directories.

    Parameters
    ----------
    targets:
        Command-line targets to inspect.
    config:
        Resolved Stilyagi configuration. The discovery layer currently only
        uses it to report that ``respect_gitignore`` is accepted but not yet
        enforced.

    Returns
    -------
    list[DiscoveredFile]
        Registered files sorted by resolved path, with duplicate resolved paths
        collapsed to one entry.

    Examples
    --------
    >>> from pathlib import Path
    >>> from stilyagi import config
    >>> discover_files(
    ...     [Path("notes.md")],
    ...     config.StilyagiConfig(),
    ... )[0].reported_path
    'notes.md'
    """
    return list(discover_files_with_summary(targets, config).files)


def discover_files_with_summary(
    targets: cabc.Iterable[pathlib.Path | str],
    config: StilyagiConfig,
) -> DiscoveryResult:
    """Discover registered source files and report skipped source candidates."""
    if config.respect_gitignore:
        _LOGGER.info("respect-gitignore is accepted but not yet enforced")

    discovered: dict[pathlib.Path, DiscoveredFile] = {}
    skipped_files = 0
    for target in targets:
        target_path = pathlib.Path(target).expanduser()
        candidates, skipped = _candidates_for_target(target_path)
        skipped_files += skipped
        for candidate in candidates:
            _record_candidate(discovered, candidate)

    files = tuple(
        discovered[resolved_path]
        for resolved_path in sorted(discovered, key=lambda path: path.as_posix())
    )
    return DiscoveryResult(files=files, skipped_files=skipped_files)


def _candidates_for_target(
    target_path: pathlib.Path,
) -> tuple[cabc.Iterator[DiscoveredFile | None], int]:
    """Return registered candidates and skipped count for one target."""
    if _is_symlinked_directory(target_path):
        _LOGGER.warning(
            "skipping symlinked directory target: %s",
            target_path.as_posix(),
        )
        return iter(()), 1
    if target_path.is_file():
        discovered_file = _discover_explicit_file(target_path)
        return iter((discovered_file,)), int(discovered_file is None)
    if target_path.is_dir():
        return _discover_directory(target_path)
    _LOGGER.info("ignoring missing or unsupported target: %s", target_path.as_posix())
    return iter(()), 0


def _discover_explicit_file(target_path: pathlib.Path) -> DiscoveredFile | None:
    """Return one explicitly requested file with a registered syntax."""
    syntax = syntax_for_path(target_path)
    if syntax is None:
        _LOGGER.info(
            "ignoring target without a registered extractor: %s",
            target_path.as_posix(),
        )
        return None
    return DiscoveredFile(
        reported_path=target_path.as_posix(),
        resolved_path=target_path.resolve(),
        syntax=syntax,
    )


def _discover_directory(
    target_path: pathlib.Path,
) -> tuple[cabc.Iterator[DiscoveredFile], int]:
    """Return directory source candidates and the count without extractors."""
    reported_base = pathlib.PurePosixPath(target_path.as_posix())
    discovered_files: list[DiscoveredFile] = []
    skipped_files = 0
    for root_path, dirnames, filenames in target_path.walk(follow_symlinks=False):
        _prune_ignored_directories(root_path, dirnames)
        relative_root = pathlib.PurePosixPath(
            root_path.relative_to(target_path).as_posix()
        )
        reported_root = reported_base / relative_root
        for filename in sorted(filenames):
            candidate = root_path / filename
            syntax = syntax_for_path(candidate)
            if syntax is None:
                skipped_files += 1
                continue
            discovered_files.append(
                DiscoveredFile(
                    reported_path=(reported_root / filename).as_posix(),
                    resolved_path=candidate.resolve(),
                    syntax=syntax,
                )
            )
    return iter(discovered_files), skipped_files


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
    """Return the registered syntax selected by a path's final suffix."""
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
