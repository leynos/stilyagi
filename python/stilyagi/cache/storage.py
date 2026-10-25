"""Read and atomically replace entries in the marked cache namespace."""

import os
import secrets
import stat
import typing as typ

from .model import CACHE_NAMESPACE_NAME, OWNER_MARKER_BYTES, cache_entry_name
from .storage_primitives import (
    _FILE_FLAGS,
    _WRITE_FLAGS,
    CacheStorageError,
    _absolute_lexical_path,
    _close_descriptor,
    _directory_identity,
    _open_child_directory,
    _open_directory_chain,
    _raise_storage_error,
    _read_marker,
    _read_regular_file,
    _require_descriptor_support,
    _write_all,
    _write_marker,
)

if typ.TYPE_CHECKING:
    import pathlib

__all__ = ["CacheStorageError", "CacheStore"]


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
        except OSError as error:
            self.close()
            if isinstance(error, CacheStorageError):
                raise
            _raise_storage_error(f"cannot open owned cache storage: {error}", error)
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
        try:
            if self._namespace_fd >= 0:
                _close_descriptor(self._namespace_fd)
        finally:
            _close_descriptor(self._root_fd)

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
            _close_descriptor(current_root)
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
            content = _read_regular_file(descriptor, subject="cache entry")
            if content is None:
                _raise_storage_error("cache entry is not a regular file")
            self._verify_directories()
            return content
        finally:
            _close_descriptor(descriptor)

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
                _close_descriptor(descriptor)
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
