"""Markdown discovery helpers for the check command.

This module finds Markdown inputs deterministically from command-line targets.
The public surface keeps both the command-line-relative reported path and the
resolved filesystem path so later stages can attribute diagnostics without
losing stable ordering.

Example
-------
>>> from pathlib import Path
>>> from stilyagi import config
>>> files = discover_markdown_files([Path("docs")], config.StilyagiConfig())
>>> [item.reported_path for item in files]
['docs/guide.md']
"""

from __future__ import annotations

import dataclasses as dc
import logging
import pathlib
import typing as typ

_LOGGER = logging.getLogger(__name__)
_MARKDOWN_SUFFIXES = frozenset({".md", ".markdown"})
_IGNORED_DIRECTORY_NAMES = frozenset({
    ".git",
    "build",
    "dist",
    "node_modules",
    "target",
    ".venv",
})

__all__ = ["DiscoveredFile", "discover_markdown_files"]

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from stilyagi.config import StilyagiConfig


@dc.dataclass(frozen=True, slots=True)
class DiscoveredFile:
    """One discovered Markdown file.

    Parameters
    ----------
    reported_path:
        The command-line-relative POSIX path used for user-facing reporting.
    resolved_path:
        The fully resolved filesystem path used for de-duplication and stable
        ordering.
    """

    reported_path: str
    resolved_path: pathlib.Path


def discover_markdown_files(
    targets: cabc.Iterable[pathlib.Path | str],
    config: StilyagiConfig,
) -> list[DiscoveredFile]:
    """Return Markdown files discovered from the supplied targets.

    Explicit Markdown files are always included. Directory targets recurse
    deterministically, skip known build noise directories, and do not follow
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
        Markdown files sorted by resolved path, with duplicate resolved paths
        collapsed to one entry.

    Examples
    --------
    >>> from pathlib import Path
    >>> from stilyagi import config
    >>> discover_markdown_files(
    ...     [Path("notes.md")],
    ...     config.StilyagiConfig(),
    ... )[0].reported_path
    'notes.md'
    """
    if config.respect_gitignore:
        _LOGGER.info("respect-gitignore is accepted but not yet enforced")

    discovered: dict[pathlib.Path, DiscoveredFile] = {}
    for target in targets:
        target_path = pathlib.Path(target).expanduser()
        for candidate in _candidates_for_target(target_path):
            _record_candidate(discovered, candidate)

    return [
        discovered[resolved_path]
        for resolved_path in sorted(discovered, key=lambda path: path.as_posix())
    ]


def _candidates_for_target(
    target_path: pathlib.Path,
) -> cabc.Iterator[DiscoveredFile | None]:
    """Yield Markdown candidates for one command-line target."""
    if _is_symlinked_directory(target_path):
        _LOGGER.info("skipping symlinked directory target: %s", target_path.as_posix())
        return
    if target_path.is_file():
        yield _discover_explicit_file(target_path)
        return
    if target_path.is_dir():
        yield from _discover_directory(target_path)
        return
    _LOGGER.info("ignoring missing or unsupported target: %s", target_path.as_posix())


def _discover_explicit_file(target_path: pathlib.Path) -> DiscoveredFile | None:
    """Return one explicit file target if it is Markdown."""
    if not _is_markdown_file(target_path):
        _LOGGER.info("ignoring non-Markdown target: %s", target_path.as_posix())
        return None
    return DiscoveredFile(
        reported_path=target_path.as_posix(),
        resolved_path=target_path.resolve(),
    )


def _discover_directory(target_path: pathlib.Path) -> cabc.Iterator[DiscoveredFile]:
    """Yield Markdown files discovered beneath one directory target."""
    reported_base = pathlib.PurePosixPath(target_path.as_posix())
    for root_path, dirnames, filenames in target_path.walk(follow_symlinks=False):
        _prune_ignored_directories(root_path, dirnames)
        relative_root = pathlib.PurePosixPath(
            root_path.relative_to(target_path).as_posix()
        )
        reported_root = reported_base / relative_root
        for filename in sorted(filenames):
            candidate = root_path / filename
            if not _is_markdown_file(candidate):
                continue
            yield DiscoveredFile(
                reported_path=(reported_root / filename).as_posix(),
                resolved_path=candidate.resolve(),
            )


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


def _is_markdown_file(path: pathlib.Path) -> bool:
    """Return ``True`` when ``path`` has a Markdown suffix."""
    return path.suffix.lower() in _MARKDOWN_SUFFIXES


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
