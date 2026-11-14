"""Fault classification for the shared descriptor-relative cache primitives."""

import errno
import os
import pathlib
import typing as typ

if typ.TYPE_CHECKING:
    import collections.abc as cabc

import pytest
from stilyagi.cache import storage_primitives as primitives
from stilyagi.cache.storage_primitives import (
    CacheStorageError,
    StorageFailureCategory,
)


def _raise_oserror(*_args: object, **_kwargs: object) -> typ.NoReturn:
    """Raise one classified descriptor fault for a patched primitive."""
    raise OSError(errno.EIO, "injected descriptor fault")


pytest_plugins = ("tests.support.cache_storage_fixtures",)


def _fifo_path(tmp_path: pathlib.Path) -> pathlib.Path:
    """Create the FIFO that stands in for a non-regular cache file."""
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo)
    return fifo


def _with_descriptor(
    path: pathlib.Path,
    flags: int,
    subject: cabc.Callable[[int], object],
) -> object:
    """Run ``subject`` on a descriptor for ``path``, closing it afterwards."""
    descriptor = os.open(path, flags)
    try:
        return subject(descriptor)
    finally:
        os.close(descriptor)


# The exclusive write target each fault case opens, so the cases cannot drift
# into opening their target with subtly different flags.
_WRITE_FLAGS = os.O_WRONLY | os.O_CREAT | os.O_EXCL


def _expect_storage_error(
    path: pathlib.Path,
    flags: int,
    subject: cabc.Callable[[int], object],
    match: str,
) -> None:
    """Assert ``subject`` classifies its descriptor fault with ``match``."""
    with pytest.raises(CacheStorageError, match=match):
        _with_descriptor(path, flags, subject)


def test_require_descriptor_support_rejects_missing_operations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Refuse cache storage when a required dir-fd operation is absent."""
    monkeypatch.setattr(primitives.os, "supports_dir_fd", set())

    with pytest.raises(CacheStorageError, match="descriptor-relative safe cache"):
        primitives._require_descriptor_support()


def test_require_descriptor_support_accepts_a_complete_platform() -> None:
    """Accept the running platform when every required primitive is present."""
    primitives._require_descriptor_support()


def test_close_descriptor_classifies_a_close_fault(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Report a failed descriptor close as a storage error with its cause."""
    monkeypatch.setattr(primitives.os, "close", _raise_oserror)

    with pytest.raises(CacheStorageError, match="cannot close cache descriptor"):
        primitives._close_descriptor(0)


def test_absolute_lexical_path_resolves_a_relative_invocation_cwd(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Make a relative base absolute against the process directory."""
    monkeypatch.chdir(tmp_path)

    resolved = primitives._absolute_lexical_path(
        pathlib.Path("cache"),
        pathlib.Path(),
    )

    assert resolved == tmp_path / "cache", "a relative base must anchor at the cwd"


def test_absolute_lexical_path_keeps_an_absolute_cache_dir(
    tmp_path: pathlib.Path,
) -> None:
    """Leave an already absolute configured cache directory anchored as given."""
    cache_dir = tmp_path / "cache"

    resolved = primitives._absolute_lexical_path(cache_dir, tmp_path / "elsewhere")

    assert resolved == cache_dir, "an absolute cache dir must not be rebased"


def test_open_chain_component_refuses_a_missing_parent_without_create(
    tmp_path: pathlib.Path,
) -> None:
    """Surface a missing chain component rather than creating it silently."""
    missing = "absent"
    root_fd = os.open(tmp_path, primitives._DIRECTORY_FLAGS)
    try:
        with pytest.raises(FileNotFoundError):
            primitives._open_chain_component(root_fd, missing, create=False)
    finally:
        os.close(root_fd)


def test_open_chain_component_creates_a_missing_directory_once(
    tmp_path: pathlib.Path,
) -> None:
    """Create one absent component and open it, tolerating a racing creator."""
    created = "created"
    root_fd = os.open(tmp_path, primitives._DIRECTORY_FLAGS)
    try:
        descriptor = primitives._open_chain_component(root_fd, created, create=True)
        os.close(descriptor)
    finally:
        os.close(root_fd)

    assert (tmp_path / created).is_dir(), "the requested component must exist"


def test_open_child_directory_reports_a_racing_creator(
    tmp_path: pathlib.Path,
    namespace_fd: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Treat a namespace created by another process as existing, not new."""
    target = tmp_path / "namespace" / "raced"
    original_open = primitives.os.open
    original_mkdir = primitives.os.mkdir
    opened: list[str] = []

    def open_after_a_race(
        name: str,
        flags: int,
        *,
        dir_fd: int | None = None,
    ) -> int:
        """Report the child missing once, then open the created directory."""
        if name == "raced" and not opened:
            opened.append(name)
            raise FileNotFoundError(name)
        return original_open(name, flags, dir_fd=dir_fd)

    def create_elsewhere(name: str, mode: int = 0o700, *, dir_fd: int) -> None:
        """Create the directory for real, then fail as a concurrent creator."""
        original_mkdir(target, mode=mode)
        raise FileExistsError(errno.EEXIST, "already created", name)

    monkeypatch.setattr(primitives.os, "open", open_after_a_race)
    monkeypatch.setattr(primitives.os, "mkdir", create_elsewhere)

    descriptor, created = primitives._open_child_directory(namespace_fd, "raced")
    os.close(descriptor)

    assert not created, "a namespace another process created is not newly owned"
    assert opened == ["raced"], "the first open must observe the missing child"


def test_open_child_directory_classifies_a_failed_reopen(
    namespace_fd: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Report a child that vanishes between creation and reopen."""

    def create_nothing(_name: str, mode: int = 0o700, *, dir_fd: int) -> None:
        """Succeed at creation without leaving a directory to reopen."""
        del mode, dir_fd

    monkeypatch.setattr(primitives.os, "mkdir", create_nothing)

    with pytest.raises(
        CacheStorageError, match="cannot safely open cache namespace"
    ) as failure:
        primitives._open_child_directory(namespace_fd, "vanished")

    assert failure.value.category is StorageFailureCategory.LEASE_UNAVAILABLE, (
        "an unusable namespace is a lease fault, not a spoiled entry"
    )


def test_open_child_directory_classifies_a_forbidden_create(
    namespace_fd: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Report a namespace creation the filesystem refuses."""

    def refuse_create(_name: str, mode: int = 0o700, *, dir_fd: int) -> None:
        """Reject the requested namespace creation."""
        del mode, dir_fd
        raise PermissionError(errno.EACCES, "denied")

    monkeypatch.setattr(primitives.os, "mkdir", refuse_create)
    monkeypatch.setattr(
        primitives.os,
        "supports_dir_fd",
        {*primitives.os.supports_dir_fd, refuse_create},
    )

    with pytest.raises(
        CacheStorageError, match="cannot create cache namespace"
    ) as failure:
        primitives._open_child_directory(namespace_fd, "refused")

    assert failure.value.category is StorageFailureCategory.LEASE_UNAVAILABLE, (
        "a namespace that cannot be created is a lease fault"
    )


def test_open_child_directory_classifies_a_forbidden_open(
    namespace_fd: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Report a child that exists but cannot be opened safely."""

    def refuse_open(_name: str, _flags: int, *, dir_fd: int) -> int:
        """Reject every attempt to open the child directory."""
        del dir_fd
        raise PermissionError(errno.EACCES, "denied")

    monkeypatch.setattr(primitives.os, "open", refuse_open)

    with pytest.raises(
        CacheStorageError, match="cannot safely open cache namespace"
    ) as failure:
        primitives._open_child_directory(namespace_fd, "blocked")

    assert failure.value.category is StorageFailureCategory.LEASE_UNAVAILABLE, (
        "a namespace that cannot be opened is a lease fault"
    )


def test_open_directory_chain_classifies_a_parent_access_fault(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Report a parent directory that cannot be opened as a lease fault."""

    def refuse_open(*_args: object, **_kwargs: object) -> int:
        """Reject every attempt to open a chain component."""
        raise PermissionError(errno.EACCES, "denied")

    monkeypatch.setattr(primitives.os, "open", refuse_open)

    with pytest.raises(
        CacheStorageError, match="cannot safely open cache directory"
    ) as failure:
        primitives._open_directory_chain(tmp_path / "cache", create=True)

    assert failure.value.category is StorageFailureCategory.LEASE_UNAVAILABLE, (
        "an unreachable parent directory is a lease fault, not a spoiled entry"
    )


def test_directory_identity_classifies_an_inspection_fault(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Report a directory whose descriptor cannot be inspected."""
    monkeypatch.setattr(primitives.os, "fstat", _raise_oserror)

    with pytest.raises(CacheStorageError, match="cannot inspect cache directory"):
        primitives._directory_identity(0)


def test_directory_identity_refuses_a_non_directory_descriptor(
    tmp_path: pathlib.Path,
) -> None:
    """Refuse a descriptor that does not describe a directory."""
    regular = tmp_path / "file"
    regular.write_bytes(b"contents")
    descriptor = os.open(regular, os.O_RDONLY)
    try:
        with pytest.raises(CacheStorageError, match="not a directory"):
            primitives._directory_identity(descriptor)
    finally:
        os.close(descriptor)


def test_directory_identity_returns_the_device_and_inode(
    tmp_path: pathlib.Path,
) -> None:
    """Return the stable identity pair for an opened directory."""
    descriptor = os.open(tmp_path, primitives._DIRECTORY_FLAGS)
    metadata = os.fstat(descriptor)
    try:
        identity = primitives._directory_identity(descriptor)
    finally:
        os.close(descriptor)

    assert identity == (metadata.st_dev, metadata.st_ino), (
        "identity must be the descriptor's device and inode"
    )


def test_read_all_classifies_a_read_fault(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Report a read that fails after the descriptor was opened."""
    regular = tmp_path / "file"
    regular.write_bytes(b"contents")
    monkeypatch.setattr(primitives.os, "read", _raise_oserror)

    _expect_storage_error(
        regular, os.O_RDONLY, primitives._read_all, "cannot read cache file"
    )


def test_read_regular_file_returns_none_for_a_fifo(tmp_path: pathlib.Path) -> None:
    """Refuse to read a FIFO as though it were an owned regular file."""
    fifo = _fifo_path(tmp_path)
    descriptor = os.open(fifo, os.O_RDONLY | primitives._O_NONBLOCK)
    try:
        content = primitives._read_regular_file(descriptor, subject="cache entry")
        assert content is None, (
            "a non-regular descriptor must not be read as cache content"
        )
    finally:
        os.close(descriptor)


def test_read_regular_file_classifies_an_inspection_fault(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Report a descriptor whose metadata cannot be read."""
    monkeypatch.setattr(primitives.os, "fstat", _raise_oserror)

    with pytest.raises(CacheStorageError, match="cannot inspect cache entry"):
        primitives._read_regular_file(0, subject="cache entry")


def test_write_all_rejects_a_short_write(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Refuse a write that reports no progress."""
    monkeypatch.setattr(primitives.os, "write", lambda *_args: 0)

    _expect_storage_error(
        tmp_path / "file",
        _WRITE_FLAGS,
        lambda descriptor: primitives._write_all(descriptor, b"contents"),
        "short write",
    )


def test_write_all_classifies_a_write_fault(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Report a write the filesystem rejects."""
    monkeypatch.setattr(primitives.os, "write", _raise_oserror)

    _expect_storage_error(
        tmp_path / "file",
        _WRITE_FLAGS,
        lambda descriptor: primitives._write_all(descriptor, b"contents"),
        "cannot write cache file",
    )
