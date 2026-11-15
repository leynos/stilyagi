"""Read and atomically replace entries in the marked cache namespace."""

import contextlib
import os
import secrets
import stat
import typing as typ

from .model import CACHE_NAMESPACE_NAME, OWNER_MARKER_BYTES, cache_entry_name
from .storage_failure import StorageFailureCategory, storage_outcome
from .storage_primitives import (
    _FILE_FLAGS,
    _WRITE_FLAGS,
    CacheStorageError,
    _absolute_lexical_path,
    _close_descriptor,
    _directory_identity,
    _open_child_directory,
    _open_directory_chain,
    _open_existing_child_directory,
    _raise_storage_error,
    _read_marker,
    _read_regular_file,
    _require_descriptor_support,
    _write_all,
    _write_marker,
)

if typ.TYPE_CHECKING:
    import pathlib

__all__ = ["CacheStorageError", "CacheStore", "storage_outcome"]


class CacheStore:
    """Read entries from, and publish entries into, one marked namespace.

    Construction is a pure query: it opens the configured parent and the
    namespace when they already exist, and holds nothing when they do not.
    Creating either directory is a separate, explicit command,
    :meth:`create_namespace`, so a lookup cannot publish an ownership marker
    or a configured parent merely by running.

    Parameters
    ----------
    cache_dir
        Configured cache parent, relative to ``invocation_cwd`` when needed.
    invocation_cwd
        The directory from which this CLI invocation began.

    Raises
    ------
    CacheStorageError
        If safe operations are unavailable, traversal is unsafe, or an
        existing namespace is not marked as owned.
    """

    def __init__(
        self,
        cache_dir: pathlib.Path,
        *,
        invocation_cwd: pathlib.Path,
    ) -> None:
        """Open the namespace read-only when it already exists."""
        _require_descriptor_support()
        self._invocation_cwd = invocation_cwd.absolute()
        self._root_path = _absolute_lexical_path(cache_dir, self._invocation_cwd)
        self._root_fd = -1
        self._namespace_fd = -1
        self._closed = False
        try:
            self._open_existing()
        except OSError as error:
            self.close()
            if isinstance(error, CacheStorageError):
                raise
            _raise_storage_error(
                f"cannot open owned cache storage: {error}",
                error,
                category=StorageFailureCategory.LEASE_UNAVAILABLE,
            )
        except Exception:
            self.close()
            raise

    def _open_existing(self) -> None:
        """Adopt the namespace only when it already exists and is marked.

        An absent parent or namespace simply means this store adopts nothing:
        it is a store over a cache that has never been used. Every other
        failure still propagates, because a path that cannot be proved safe is
        a refusal and not an absence. Reading a symlinked root as "no cache
        yet" would hand a later publication the very redirect the no-follow
        walk exists to reject.

        Raises
        ------
        CacheStorageError
            If the root or namespace exists but cannot be proved safe, or is
            not marked as owned by Stilyagi.
        """
        try:
            self._root_fd = _open_directory_chain(
                self._root_path,
                create=False,
                trusted_base=self._invocation_cwd,
            )
        except CacheStorageError as error:
            if isinstance(error.__cause__, FileNotFoundError):
                return
            raise
        self._root_identity = _directory_identity(self._root_fd)
        try:
            self._namespace_fd = _open_existing_child_directory(
                self._root_fd,
                CACHE_NAMESPACE_NAME,
            )
        except FileNotFoundError:
            return
        self._namespace_identity = _directory_identity(self._namespace_fd)
        self._require_owned_marker()
        self._verify_directories()

    def _require_owned_marker(self) -> None:
        """Refuse a namespace whose marker is absent or inexact."""
        if _read_marker(self._namespace_fd) != OWNER_MARKER_BYTES:
            _raise_storage_error(
                f"cache namespace {CACHE_NAMESPACE_NAME} is not owned by Stilyagi",
                category=StorageFailureCategory.OWNERSHIP_REFUSED,
            )

    def create_namespace(self) -> None:
        """Create the configured parent, namespace and marker when absent.

        This is the only route by which a store brings storage into being.
        It is idempotent, and it re-derives the held identities afterwards so
        a store built over an absent namespace can then publish entries.
        A creation, ownership or verification refusal surfaces as a
        :class:`CacheStorageError` raised by the helpers this delegates to.

        Examples
        --------
        >>> # A cold store holds no descriptors until this call creates them.
        >>> # See tests/test_cache_storage.py for a real temporary directory.
        """
        if self._namespace_fd >= 0:
            self._verify_directories()
            return
        if self._root_fd < 0:
            self._root_fd = _open_directory_chain(
                self._root_path,
                create=True,
                trusted_base=self._invocation_cwd,
            )
            self._root_identity = _directory_identity(self._root_fd)
        self._namespace_fd, created = _open_child_directory(
            self._root_fd,
            CACHE_NAMESPACE_NAME,
        )
        self._namespace_identity = _directory_identity(self._namespace_fd)
        try:
            if created:
                _write_marker(self._namespace_fd)
            self._require_owned_marker()
            self._verify_directories()
        except BaseException:
            _close_descriptor(self._namespace_fd)
            self._namespace_fd = -1
            raise

    def __enter__(self) -> CacheStore:
        """Return this open store as a context manager."""
        return self

    def __exit__(self, *_: object) -> None:
        """Close both directory descriptors after the cache operation."""
        self.close()

    def close(self) -> None:
        """Close the namespace and configured-parent descriptors once.

        A store that adopted no namespace still holds the configured parent
        when it exists, and holds nothing at all when it does not, so each
        descriptor is closed only when it was opened.
        """
        if self._closed:
            return
        self._closed = True
        try:
            if self._namespace_fd >= 0:
                _close_descriptor(self._namespace_fd)
        finally:
            if self._root_fd >= 0:
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
                _raise_storage_error(
                    "configured cache root was replaced",
                    category=StorageFailureCategory.NAMESPACE_REPLACED,
                )
        finally:
            _close_descriptor(current_root)
        try:
            namespace_metadata = os.stat(
                CACHE_NAMESPACE_NAME,
                dir_fd=self._root_fd,
                follow_symlinks=False,
            )
        except OSError as error:
            _raise_storage_error(
                f"cache namespace was replaced: {error}",
                error,
                category=StorageFailureCategory.NAMESPACE_REPLACED,
            )
        if (
            not stat.S_ISDIR(namespace_metadata.st_mode)
            or (namespace_metadata.st_dev, namespace_metadata.st_ino)
            != self._namespace_identity
        ):
            _raise_storage_error(
                "cache namespace was replaced",
                category=StorageFailureCategory.NAMESPACE_REPLACED,
            )

    def read(self, key: str) -> bytes | None:
        """Read one cache entry, returning ``None`` when it has no entry.

        Parameters
        ----------
        key
            The validated lowercase SHA-256 request key.

        Returns
        -------
        bytes or None
            The stored envelope, or ``None`` when no entry exists. A store
            that adopted no namespace has no entries, so it reports ``None``
            without touching the filesystem.

        Examples
        --------
        >>> # A new, marked store returns None until its first write.
        >>> # See tests/test_cache_storage.py for a real temporary directory.
        """
        if self._namespace_fd < 0:
            return None
        entry_name = cache_entry_name(key)
        self._verify_directories()
        try:
            descriptor = os.open(entry_name, _FILE_FLAGS, dir_fd=self._namespace_fd)
        except FileNotFoundError:
            self._verify_directories()
            return None
        except OSError as error:
            _raise_storage_error(
                f"cannot safely read cache entry: {error}",
                error,
                category=StorageFailureCategory.ENTRY_INVALID,
            )
        try:
            content = _read_regular_file(descriptor, subject="cache entry")
            if content is None:
                _raise_storage_error(
                    "cache entry is not a regular file",
                    category=StorageFailureCategory.ENTRY_INVALID,
                )
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
            The serialized envelope to store. A store that created no
            namespace refuses to write; every other failure in the
            descriptor-relative create, flush or rename surfaces as a
            :class:`CacheStorageError` raised by the helpers this delegates to.
        """
        if self._namespace_fd < 0:
            _raise_storage_error(
                "cannot write to a cache namespace that was never created",
                category=StorageFailureCategory.LEASE_UNAVAILABLE,
            )
        entry_name = cache_entry_name(key)
        self._verify_directories()
        temporary_name = f".tmp-{secrets.token_hex(16)}"
        try:
            self._publish_temporary(temporary_name, entry_name, content)
        finally:
            # A temporary file that outlived its publication is litter, not a
            # fault: the entry itself is already durable or already reported.
            with contextlib.suppress(OSError):
                os.unlink(temporary_name, dir_fd=self._namespace_fd)

    def _publish_temporary(
        self,
        temporary_name: str,
        entry_name: str,
        content: bytes,
    ) -> None:
        """Write, flush and rename one temporary file onto its final name.

        The rename is what makes the replacement atomic: a reader sees either
        the whole previous entry or the whole new one, never a partial write.

        Raises
        ------
        CacheStorageError
            If the temporary file cannot be created, written, flushed, or
            renamed onto its final name.
        """
        try:
            descriptor = os.open(
                temporary_name,
                _WRITE_FLAGS,
                mode=0o600,
                dir_fd=self._namespace_fd,
            )
        except OSError as error:
            _raise_storage_error(
                f"cannot create cache temporary file: {error}",
                error,
                category=StorageFailureCategory.RESTORE_FAILED,
            )
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
            _raise_storage_error(
                f"cannot write cache entry atomically: {error}",
                error,
                category=StorageFailureCategory.RESTORE_FAILED,
            )
