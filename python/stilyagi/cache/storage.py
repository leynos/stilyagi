"""Descriptor-anchored reads and atomic writes for the owned cache namespace."""

import contextlib
import errno
import os
import pathlib
import secrets
import stat
import typing as typ

from .model import (
    CACHE_NAMESPACE_NAME,
    OWNER_MARKER_BYTES,
    OWNER_MARKER_NAME,
    cache_entry_name,
)

__all__ = ["CacheStorageError", "CacheStore"]

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
            os.close(descriptor)
            descriptor = child
    except (OSError, ValueError) as error:
        if descriptor >= 0:
            os.close(descriptor)
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
    metadata = os.fstat(descriptor)
    if not stat.S_ISDIR(metadata.st_mode):
        _raise_storage_error("cache directory descriptor is not a directory")
    return metadata.st_dev, metadata.st_ino


def _read_all(descriptor: int) -> bytes:
    """Read an already-open regular file without following another path."""
    chunks: list[bytes] = []
    while chunk := os.read(descriptor, _READ_SIZE):
        chunks.append(chunk)
    return b"".join(chunks)


def _write_all(descriptor: int, content: bytes) -> None:
    """Write every byte, handling short writes explicitly."""
    pending = memoryview(content)
    while pending:
        written = os.write(descriptor, pending)
        if written <= 0:
            raise OSError(errno.EIO, "short write while storing cache data")
        pending = pending[written:]


def _read_marker(namespace_fd: int) -> bytes | None:
    """Read the exact ownership marker when it is a regular file."""
    try:
        descriptor = os.open(OWNER_MARKER_NAME, _FILE_FLAGS, dir_fd=namespace_fd)
    except FileNotFoundError:
        return None
    except OSError as error:
        _raise_storage_error(f"cannot safely read cache owner marker: {error}", error)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            return None
        return _read_all(descriptor)
    finally:
        os.close(descriptor)


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
        _write_all(descriptor, OWNER_MARKER_BYTES)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


class CacheStore:
    """Read and atomically replace entries inside one marked cache namespace.

    Parameters
    ----------
    cache_dir
        Configured cache parent, relative to ``invocation_cwd`` when needed.
    invocation_cwd
        The directory from which this CLI invocation began.

    Raises
    ------
    CacheStorageError
        If safe operations are unavailable, traversal is unsafe, or the
        namespace is not marked as owned.
    """

    def __init__(
        self,
        cache_dir: pathlib.Path,
        *,
        invocation_cwd: pathlib.Path,
    ) -> None:
        """Open the configured parent and its exact owned namespace."""
        _require_descriptor_support()
        self._invocation_cwd = invocation_cwd.absolute()
        self._root_path = _absolute_lexical_path(cache_dir, self._invocation_cwd)
        self._root_fd = _open_directory_chain(
            self._root_path,
            create=True,
            trusted_base=self._invocation_cwd,
        )
        self._namespace_fd = -1
        self._closed = False
        try:
            self._root_identity = _directory_identity(self._root_fd)
            self._namespace_fd, created = _open_child_directory(
                self._root_fd,
                CACHE_NAMESPACE_NAME,
            )
            self._namespace_identity = _directory_identity(self._namespace_fd)
            marker = _read_marker(self._namespace_fd)
            if marker is None and created:
                _write_marker(self._namespace_fd)
                marker = _read_marker(self._namespace_fd)
            if marker != OWNER_MARKER_BYTES:
                _raise_storage_error(
                    f"cache namespace {CACHE_NAMESPACE_NAME} is not owned by Stilyagi"
                )
            self._verify_directories()
        except Exception:
            self.close()
            raise

    def __enter__(self) -> CacheStore:
        """Return this open store as a context manager."""
        return self

    def __exit__(self, *_: object) -> None:
        """Close both directory descriptors after the cache operation."""
        self.close()

    def close(self) -> None:
        """Close the namespace and configured-parent descriptors once."""
        if self._closed:
            return
        self._closed = True
        if self._namespace_fd >= 0:
            os.close(self._namespace_fd)
        os.close(self._root_fd)

    def _verify_directories(self) -> None:
        """Reject a replaced root or namespace before touching an entry."""
        current_root = _open_directory_chain(
            self._root_path,
            create=False,
            trusted_base=self._invocation_cwd,
        )
        try:
            if _directory_identity(current_root) != self._root_identity:
                _raise_storage_error("configured cache root was replaced")
        finally:
            os.close(current_root)
        try:
            namespace_metadata = os.stat(
                CACHE_NAMESPACE_NAME,
                dir_fd=self._root_fd,
                follow_symlinks=False,
            )
        except OSError as error:
            _raise_storage_error(f"cache namespace was replaced: {error}", error)
        if (
            not stat.S_ISDIR(namespace_metadata.st_mode)
            or (namespace_metadata.st_dev, namespace_metadata.st_ino)
            != self._namespace_identity
        ):
            _raise_storage_error("cache namespace was replaced")

    def read(self, key: str) -> bytes | None:
        """Read one cache entry, returning ``None`` when it has no entry.

        Parameters
        ----------
        key
            The validated lowercase SHA-256 request key.

        Returns
        -------
        bytes or None
            The stored envelope, or ``None`` when no entry exists.

        Examples
        --------
        >>> # A new, marked store returns None until its first write.
        >>> # See tests/test_cache_storage.py for a real temporary directory.
        """
        entry_name = cache_entry_name(key)
        self._verify_directories()
        try:
            descriptor = os.open(entry_name, _FILE_FLAGS, dir_fd=self._namespace_fd)
        except FileNotFoundError:
            self._verify_directories()
            return None
        except OSError as error:
            _raise_storage_error(f"cannot safely read cache entry: {error}", error)
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                _raise_storage_error("cache entry is not a regular file")
            content = _read_all(descriptor)
            self._verify_directories()
            return content
        finally:
            os.close(descriptor)

    def write(self, key: str, content: bytes) -> None:
        """Atomically replace one cache entry using an exclusive temporary file.

        Parameters
        ----------
        key
            The validated lowercase SHA-256 request key.
        content
            The serialized envelope to store.

        Raises
        ------
        CacheStorageError
            If safe descriptor-relative creation or atomic replacement fails.
        """
        entry_name = cache_entry_name(key)
        self._verify_directories()
        temporary_name = f".tmp-{secrets.token_hex(16)}"
        try:
            descriptor = os.open(
                temporary_name,
                _WRITE_FLAGS,
                mode=0o600,
                dir_fd=self._namespace_fd,
            )
        except OSError as error:
            _raise_storage_error(f"cannot create cache temporary file: {error}", error)
        try:
            try:
                _write_all(descriptor, content)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            self._verify_directories()
            os.rename(
                temporary_name,
                entry_name,
                src_dir_fd=self._namespace_fd,
                dst_dir_fd=self._namespace_fd,
            )
            os.fsync(self._namespace_fd)
            self._verify_directories()
        except CacheStorageError:
            raise
        except OSError as error:
            _raise_storage_error(f"cannot write cache entry atomically: {error}", error)
        finally:
            try:
                os.unlink(temporary_name, dir_fd=self._namespace_fd)
            except FileNotFoundError:
                pass
            except OSError:
                pass
