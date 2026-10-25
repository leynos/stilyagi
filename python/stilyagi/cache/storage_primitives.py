"""Share descriptor-relative filesystem primitives across cache adapters.

These helpers enforce no-follow traversal and classify operating-system faults.
Keep them limited to anchored cache storage operations shared by storage and
cleanup; policy for individual cache requests belongs in those adapters.
"""

import contextlib
import os
import pathlib
import stat
import typing as typ

from .model import (
    OWNER_MARKER_BYTES,
    OWNER_MARKER_NAME,
)

__all__ = ["CacheStorageError"]

_O_DIRECTORY = getattr(os, "O_DIRECTORY", 0)
_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_O_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
_O_NONBLOCK = getattr(os, "O_NONBLOCK", 0)
_DIRECTORY_FLAGS = os.O_RDONLY | _O_DIRECTORY | _O_NOFOLLOW | _O_CLOEXEC
_FILE_FLAGS = os.O_RDONLY | _O_NOFOLLOW | _O_CLOEXEC | _O_NONBLOCK
_WRITE_FLAGS = os.O_WRONLY | os.O_CREAT | os.O_EXCL | _O_NOFOLLOW | _O_CLOEXEC
_READ_SIZE = 1024 * 1024


class CacheStorageError(OSError):
    """A cache operation could not prove that it stayed in owned storage."""


def _raise_storage_error(
    message: str,
    cause: Exception | None = None,
) -> typ.NoReturn:
    """Raise a storage failure after its operation-specific detail is prepared."""
    if cause is None:
        raise CacheStorageError(message)
    raise CacheStorageError(message) from cause


def _require_descriptor_support() -> None:
    """Refuse cache use when required no-follow descriptor operations are absent."""
    required = (os.open, os.mkdir, os.stat, os.unlink, os.rename)
    if not all(operation in os.supports_dir_fd for operation in required) or not all(
        hasattr(os, flag)
        for flag in ("O_DIRECTORY", "O_NOFOLLOW", "O_CLOEXEC", "O_NONBLOCK")
    ):
        _raise_storage_error("descriptor-relative safe cache operations unavailable")


def _close_descriptor(descriptor: int) -> None:
    """Close one descriptor while keeping operating-system errors classified."""
    try:
        os.close(descriptor)
    except OSError as error:
        _raise_storage_error(f"cannot close cache descriptor: {error}", error)


def _absolute_lexical_path(
    cache_dir: pathlib.Path,
    invocation_cwd: pathlib.Path,
) -> pathlib.Path:
    """Make a configured path absolute without resolving symlink components."""
    base = invocation_cwd
    if not base.is_absolute():
        base = pathlib.Path.cwd() / base
    candidate = cache_dir if cache_dir.is_absolute() else base / cache_dir
    return candidate.absolute()


def _open_chain_start(
    path: pathlib.Path,
    trusted_base: pathlib.Path | None,
) -> tuple[int, tuple[str, ...]]:
    """Anchor at a selected base when possible; otherwise start at the root."""
    absolute_path = path.absolute()
    base_path = trusted_base.absolute() if trusted_base is not None else None
    if base_path is not None and absolute_path.is_relative_to(base_path):
        descriptor = os.open(base_path, _DIRECTORY_FLAGS & ~_O_NOFOLLOW)
        return descriptor, absolute_path.relative_to(base_path).parts
    descriptor = os.open(absolute_path.anchor, _DIRECTORY_FLAGS)
    return descriptor, absolute_path.parts[1:]


def _open_chain_component(parent_fd: int, component: str, *, create: bool) -> int:
    """Open one no-follow directory component, creating it when requested."""
    try:
        return os.open(component, _DIRECTORY_FLAGS, dir_fd=parent_fd)
    except FileNotFoundError:
        if not create:
            raise
        with contextlib.suppress(FileExistsError):
            os.mkdir(component, mode=0o700, dir_fd=parent_fd)
        return os.open(component, _DIRECTORY_FLAGS, dir_fd=parent_fd)


def _open_directory_chain(
    path: pathlib.Path,
    *,
    create: bool,
    trusted_base: pathlib.Path | None = None,
) -> int:
    """Open a no-follow chain, following the selected base only once.

    Returns
    -------
    int
        Open descriptor for the final directory in the chain.

    """
    descriptor = -1
    try:
        descriptor, components = _open_chain_start(path, trusted_base)
        for component in components:
            child = _open_chain_component(descriptor, component, create=create)
            _close_descriptor(descriptor)
            descriptor = child
    except (OSError, ValueError) as error:
        if descriptor >= 0:
            _close_descriptor(descriptor)
        _raise_storage_error(
            f"cannot safely open cache directory {path}: {error}", error
        )
    else:
        return descriptor


def _open_child_directory(parent_fd: int, name: str) -> tuple[int, bool]:
    """Open or create one child directory and report whether it was created."""
    try:
        descriptor = os.open(name, _DIRECTORY_FLAGS, dir_fd=parent_fd)
    except FileNotFoundError:
        try:
            os.mkdir(name, mode=0o700, dir_fd=parent_fd)
            created = True
        except FileExistsError:
            created = False
        except OSError as error:
            _raise_storage_error(
                f"cannot create cache namespace {name}: {error}", error
            )
        try:
            descriptor = os.open(name, _DIRECTORY_FLAGS, dir_fd=parent_fd)
        except OSError as error:
            _raise_storage_error(
                f"cannot safely open cache namespace {name}: {error}",
                error,
            )
    except OSError as error:
        _raise_storage_error(
            f"cannot safely open cache namespace {name}: {error}", error
        )
    else:
        return descriptor, False
    return descriptor, created


def _directory_identity(descriptor: int) -> tuple[int, int]:
    """Return the stable device and inode pair for an opened directory."""
    try:
        metadata = os.fstat(descriptor)
    except OSError as error:
        _raise_storage_error(f"cannot inspect cache directory: {error}", error)
    if not stat.S_ISDIR(metadata.st_mode):
        _raise_storage_error("cache directory descriptor is not a directory")
    return metadata.st_dev, metadata.st_ino


def _read_all(descriptor: int) -> bytes:
    """Read an already-open regular file without following another path."""
    chunks: list[bytes] = []
    try:
        while chunk := os.read(descriptor, _READ_SIZE):
            chunks.append(chunk)
    except OSError as error:
        _raise_storage_error(f"cannot read cache file: {error}", error)
    return b"".join(chunks)


def _read_regular_file(descriptor: int, *, subject: str) -> bytes | None:
    """Read a regular file descriptor, returning None for other file types."""
    try:
        metadata = os.fstat(descriptor)
    except OSError as error:
        _raise_storage_error(f"cannot inspect {subject}: {error}", error)
    if not stat.S_ISREG(metadata.st_mode):
        return None
    return _read_all(descriptor)


def _write_all(descriptor: int, content: bytes) -> None:
    """Write every byte, handling short writes explicitly."""
    pending = memoryview(content)
    try:
        while pending:
            written = os.write(descriptor, pending)
            if written <= 0:
                _raise_storage_error("short write while storing cache data")
            pending = pending[written:]
    except OSError as error:
        _raise_storage_error(f"cannot write cache file: {error}", error)


def _read_marker(namespace_fd: int) -> bytes | None:
    """Read the exact ownership marker when it is a regular file."""
    try:
        descriptor = os.open(OWNER_MARKER_NAME, _FILE_FLAGS, dir_fd=namespace_fd)
    except FileNotFoundError:
        return None
    except OSError as error:
        _raise_storage_error(f"cannot safely read cache owner marker: {error}", error)
    try:
        return _read_regular_file(descriptor, subject="cache owner marker")
    finally:
        _close_descriptor(descriptor)


def _write_marker(namespace_fd: int) -> None:
    """Create the ownership marker without replacing an existing path."""
    try:
        descriptor = os.open(
            OWNER_MARKER_NAME,
            _WRITE_FLAGS,
            mode=0o600,
            dir_fd=namespace_fd,
        )
    except FileExistsError:
        return
    except OSError as error:
        _raise_storage_error(f"cannot create cache owner marker: {error}", error)
    try:
        try:
            _write_all(descriptor, OWNER_MARKER_BYTES)
            os.fsync(descriptor)
        except OSError as error:
            _raise_storage_error(f"cannot write cache owner marker: {error}", error)
    finally:
        _close_descriptor(descriptor)
