"""Remove only marked Stilyagi extraction caches beneath a chosen root."""

import dataclasses as dc
import os
import pathlib
import stat
import typing as typ

from .model import (
    CACHE_NAMESPACE_NAME,
    OWNER_MARKER_BYTES,
    OWNER_MARKER_NAME,
    CacheFileKind,
    classify_cache_filename,
)
from .storage import (
    _DIRECTORY_FLAGS,
    _FILE_FLAGS,
    _directory_identity,
    _open_directory_chain,
    _read_marker,
    _write_marker,
)

__all__ = ["CacheCleanResult", "clean_cache_tree"]


@dc.dataclass(frozen=True, slots=True)
class CacheCleanResult:
    """Summarize owned state removed and failures encountered during cleanup."""

    removed_files: int = 0
    removed_namespaces: int = 0
    preserved_unknown_entries: int = 0
    errors: tuple[str, ...] = ()


@dc.dataclass(slots=True)
class _CleanCounts:
    """Mutable counters used only while one directory tree is traversed."""

    removed_files: int = 0
    removed_namespaces: int = 0
    preserved_unknown_entries: int = 0
    errors: list[str] = dc.field(default_factory=list)

    def result(self) -> CacheCleanResult:
        """Freeze accumulated traversal evidence for the caller."""
        return CacheCleanResult(
            removed_files=self.removed_files,
            removed_namespaces=self.removed_namespaces,
            preserved_unknown_entries=self.preserved_unknown_entries,
            errors=tuple(self.errors),
        )


@dc.dataclass(frozen=True, slots=True)
class _NamespacePath:
    """Anchor one candidate cache namespace to its parent descriptor."""

    parent_fd: int
    name: str
    descriptor: int
    counts: _CleanCounts
    relative_path: pathlib.PurePath


@dc.dataclass(frozen=True, slots=True)
class _OwnedNamespace:
    """Carry identities needed to remove one verified marked namespace."""

    path: _NamespacePath
    directory_identity: tuple[int, int]
    marker_identity: tuple[int, int]


def _raise_cleanup_error(message: str) -> typ.NoReturn:
    """Raise one cleanup failure with its detail prepared by the caller."""
    raise OSError(message)


def _require_safe_cleanup_support() -> None:
    """Refuse platforms without descriptor-relative no-follow deletion."""
    if not _supports_safe_cleanup():
        _raise_cleanup_error("descriptor-relative safe cache cleanup is unavailable")


def _supports_safe_cleanup() -> bool:
    """Check each descriptor and no-follow primitive required for deletion."""
    required = (os.open, os.stat, os.unlink, os.rmdir)
    if not all(operation in os.supports_dir_fd for operation in required):
        return False
    if os.scandir not in os.supports_fd:
        return False
    return all(
        hasattr(os, flag) for flag in ("O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK")
    )


def _same_directory(parent_fd: int, name: str, identity: tuple[int, int]) -> bool:
    """Confirm a namespace name still identifies its initially opened directory."""
    try:
        metadata = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError:
        return False
    return (
        stat.S_ISDIR(metadata.st_mode)
        and (metadata.st_dev, metadata.st_ino) == identity
    )


def _directory_entries(directory_fd: int) -> tuple[os.DirEntry[str], ...]:
    """Read one anchored directory listing without following child links."""
    with os.scandir(directory_fd) as entries:
        return tuple(entries)


def _clean_namespace(namespace: _NamespacePath) -> bool:
    """Remove owned files from an exactly marked namespace, if still anchored."""
    try:
        marker = _read_marker(namespace.descriptor)
    except OSError as error:
        _record_namespace_error(namespace, OWNER_MARKER_NAME, error)
        return True
    if marker != OWNER_MARKER_BYTES:
        namespace.counts.preserved_unknown_entries += 1
        return True

    try:
        directory_identity = _directory_identity(namespace.descriptor)
        marker_identity = _marker_identity(namespace.descriptor)
    except OSError as error:
        _record_namespace_error(namespace, None, error)
        return True
    owned = _OwnedNamespace(namespace, directory_identity, marker_identity)
    _delete_owned_entries(owned)
    if _namespace_has_preserved_entries(owned):
        return True
    return _remove_namespace(owned)


def _record_namespace_error(
    namespace: _NamespacePath,
    child_name: str | None,
    error: OSError,
) -> None:
    """Attach one namespace failure to its user-visible relative path."""
    location = namespace.relative_path
    if child_name is not None:
        location /= child_name
    namespace.counts.errors.append(f"{location}: {error}")


def _marker_identity(namespace_fd: int) -> tuple[int, int]:
    """Return the identity of the exact no-follow ownership marker."""
    marker_fd = os.open(
        OWNER_MARKER_NAME,
        _FILE_FLAGS,
        dir_fd=namespace_fd,
    )
    try:
        marker_metadata = os.fstat(marker_fd)
        if not stat.S_ISREG(marker_metadata.st_mode):
            _raise_cleanup_error("cache owner marker is not a regular file")
        return marker_metadata.st_dev, marker_metadata.st_ino
    finally:
        os.close(marker_fd)


def _delete_owned_entries(namespace: _OwnedNamespace) -> None:
    """Unlink exact owned cache leaves from the anchored namespace."""
    path = namespace.path
    try:
        entries = _directory_entries(path.descriptor)
    except OSError as error:
        _record_namespace_error(path, None, error)
        return
    for entry in entries:
        _delete_owned_entry(namespace, entry.name)


def _delete_owned_entry(namespace: _OwnedNamespace, entry_name: str) -> None:
    """Remove one recognized leaf while its namespace identity still matches."""
    path = namespace.path
    if classify_cache_filename(entry_name) is None:
        return
    if not _same_directory(path.parent_fd, path.name, namespace.directory_identity):
        return
    try:
        metadata = os.stat(
            entry_name,
            dir_fd=path.descriptor,
            follow_symlinks=False,
        )
        if not (stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode)):
            return
        os.unlink(entry_name, dir_fd=path.descriptor)
        path.counts.removed_files += 1
    except OSError as error:
        _record_namespace_error(path, entry_name, error)


def _namespace_has_preserved_entries(namespace: _OwnedNamespace) -> bool:
    """Count unknown or newly written leaves that keep a namespace in place."""
    path = namespace.path
    try:
        remaining = _directory_entries(path.descriptor)
    except OSError as error:
        _record_namespace_error(path, None, error)
        return True
    unrecognized = tuple(
        entry.name
        for entry in remaining
        if entry.name != OWNER_MARKER_NAME
        and not _is_removable_owned_file(path.descriptor, entry.name)
    )
    owned_files_remain = any(
        _is_removable_owned_file(path.descriptor, entry.name) for entry in remaining
    )
    path.counts.preserved_unknown_entries += len(unrecognized)
    if not _same_directory(
        path.parent_fd,
        path.name,
        namespace.directory_identity,
    ):
        path.counts.errors.append(
            f"{path.relative_path}: cache namespace changed during cleanup"
        )
        return True
    return bool(unrecognized or owned_files_remain)


def _remove_namespace(namespace: _OwnedNamespace) -> bool:
    """Remove the marker and namespace only while both identities still match."""
    path = namespace.path
    marker_removed = False
    try:
        current_marker = os.stat(
            OWNER_MARKER_NAME,
            dir_fd=path.descriptor,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISREG(current_marker.st_mode)
            or (current_marker.st_dev, current_marker.st_ino)
            != namespace.marker_identity
        ):
            _raise_cleanup_error("cache owner marker was replaced during cleanup")
        os.unlink(OWNER_MARKER_NAME, dir_fd=path.descriptor)
        marker_removed = True
        if not _same_directory(
            path.parent_fd,
            path.name,
            namespace.directory_identity,
        ):
            _raise_cleanup_error("cache namespace was replaced during cleanup")
        os.rmdir(path.name, dir_fd=path.parent_fd)
    except OSError as error:
        if marker_removed:
            _restore_owner_marker(namespace)
        _record_namespace_error(path, None, error)
        return True
    path.counts.removed_files += 1
    path.counts.removed_namespaces += 1
    return False


def _restore_owner_marker(namespace: _OwnedNamespace) -> None:
    """Restore ownership after failed removal while the same namespace remains."""
    path = namespace.path
    if not _same_directory(path.parent_fd, path.name, namespace.directory_identity):
        return
    try:
        _write_marker(path.descriptor)
        if _read_marker(path.descriptor) != OWNER_MARKER_BYTES:
            _raise_cleanup_error("cache owner marker could not be restored")
    except OSError as error:
        _record_namespace_error(path, OWNER_MARKER_NAME, error)


def _is_removable_owned_file(directory_fd: int, name: str) -> bool:
    """Return whether a recognized name currently points to a removable leaf."""
    if classify_cache_filename(name) not in {CacheFileKind.ENTRY, CacheFileKind.TEMP}:
        return False
    try:
        metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except OSError:
        return False
    return stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode)


def _walk_directory(
    directory_fd: int,
    relative_path: pathlib.PurePath,
    counts: _CleanCounts,
) -> None:
    """Visit real child directories and skip directory symlinks and Git data."""
    try:
        entries = _directory_entries(directory_fd)
    except OSError as error:
        counts.errors.append(f"{relative_path}: {error}")
        return

    for entry in entries:
        if entry.name == ".git":
            continue
        _visit_child_directory(directory_fd, entry, relative_path, counts)


def _visit_child_directory(
    parent_fd: int,
    entry: os.DirEntry[str],
    relative_path: pathlib.PurePath,
    counts: _CleanCounts,
) -> None:
    """Open, identity-check, and visit one real directory entry."""
    child_path = relative_path / entry.name
    try:
        metadata = os.stat(entry.name, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISDIR(metadata.st_mode):
            return
        child_fd = os.open(entry.name, _DIRECTORY_FLAGS, dir_fd=parent_fd)
    except OSError as error:
        counts.errors.append(f"{child_path}: {error}")
        return
    try:
        child_metadata = os.fstat(child_fd)
        if (child_metadata.st_dev, child_metadata.st_ino) != (
            metadata.st_dev,
            metadata.st_ino,
        ):
            counts.errors.append(f"{child_path}: directory changed during traversal")
            return
        if entry.name == CACHE_NAMESPACE_NAME:
            should_recurse = _clean_namespace(
                _NamespacePath(parent_fd, entry.name, child_fd, counts, child_path)
            )
        else:
            should_recurse = True
        if should_recurse:
            _walk_directory(child_fd, child_path, counts)
    finally:
        os.close(child_fd)


def clean_cache_tree(root: pathlib.Path) -> CacheCleanResult:
    """Clean marked caches under ``root`` without traversing directory links.

    The traversal includes ignored directories but prunes every ``.git``
    directory. Unknown files keep their marked namespace and survive cleanup.
    A concurrent writer may recreate entries; this is idempotent best-effort
    cleanup rather than a lock across all cache users.

    Returns
    -------
    CacheCleanResult
        Counts of removed owned entries and failures that did not abort traversal.
    """
    _require_safe_cleanup_support()
    counts = _CleanCounts()
    absolute_root = root.absolute()
    try:
        root_fd = _open_directory_chain(
            absolute_root,
            create=False,
            trusted_base=absolute_root,
        )
    except OSError as error:
        return CacheCleanResult(errors=(f"{absolute_root}: {error}",))
    try:
        _walk_directory(root_fd, pathlib.PurePath(), counts)
    finally:
        os.close(root_fd)
    return counts.result()
