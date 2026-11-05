"""Ownership-marker contracts for the descriptor-relative cache primitives.

A namespace counts as owned only when it carries the marker with the exact
owned bytes, as a regular file. These tests own that reading and the marker's
creation, including the cases that must *not* prove ownership: an absent
marker, a FIFO in its place, and a creation the filesystem refuses.
"""

import errno
import os
import stat
import typing as typ

import pytest
from stilyagi.cache import storage_primitives as primitives
from stilyagi.cache.model import OWNER_MARKER_BYTES, OWNER_MARKER_NAME
from stilyagi.cache.storage_primitives import CacheStorageError

pytest_plugins = ("tests.support.cache_storage_fixtures",)


def _refusing_open(*_args: object, **_kwargs: object) -> typ.NoReturn:
    """Refuse every marker open, so the create and read paths both fault."""
    raise PermissionError(errno.EACCES, "denied")


def test_read_marker_returns_none_when_the_marker_is_absent(
    namespace_fd: int,
) -> None:
    """Treat an absent ownership marker as unmarked rather than failed."""
    assert primitives._read_marker(namespace_fd) is None, (
        "a missing marker must be distinguishable from an unreadable one"
    )


def test_read_marker_returns_the_marker_bytes(namespace_fd: int) -> None:
    """Return the exact marker contents for an owned namespace."""
    primitives._write_marker(namespace_fd)

    assert primitives._read_marker(namespace_fd) == OWNER_MARKER_BYTES, (
        "the marker must read back byte for byte"
    )


def test_read_marker_classifies_a_denied_open(
    namespace_fd: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Report a marker that exists but cannot be opened safely."""
    monkeypatch.setattr(primitives.os, "open", _refusing_open)

    with pytest.raises(CacheStorageError, match="cannot safely read cache owner"):
        primitives._read_marker(namespace_fd)


def test_read_marker_returns_none_for_a_fifo_marker(
    namespace_fd: int,
) -> None:
    """Refuse to treat a FIFO marker as proof of ownership."""
    os.mkfifo(OWNER_MARKER_NAME, dir_fd=namespace_fd)

    assert primitives._read_marker(namespace_fd) is None, (
        "a non-regular marker must not prove ownership"
    )


def test_write_marker_tolerates_an_existing_marker(namespace_fd: int) -> None:
    """Leave a marker another writer created in place."""
    primitives._write_marker(namespace_fd)

    primitives._write_marker(namespace_fd)

    assert primitives._read_marker(namespace_fd) == OWNER_MARKER_BYTES, (
        "a repeat marker write must not replace the owned marker"
    )


def test_write_marker_classifies_a_refused_creation(
    namespace_fd: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Report a marker the filesystem refuses to create."""
    monkeypatch.setattr(primitives.os, "open", _refusing_open)

    with pytest.raises(CacheStorageError, match="cannot create cache owner marker"):
        primitives._write_marker(namespace_fd)


def test_write_marker_classifies_a_failed_content_write(
    namespace_fd: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Report a marker whose contents cannot be written."""

    def fail_content_write(_descriptor: int, _content: bytes) -> typ.NoReturn:
        """Fail the marker content write after a successful create."""
        raise OSError(errno.EIO, "injected write fault")

    monkeypatch.setattr(primitives, "_write_all", fail_content_write)

    with pytest.raises(CacheStorageError, match="cannot write cache owner marker"):
        primitives._write_marker(namespace_fd)


def test_marker_constants_keep_the_owned_regular_file_shape(
    namespace_fd: int,
) -> None:
    """Confirm the written marker is a regular file with the owned bytes."""
    primitives._write_marker(namespace_fd)

    metadata = os.stat(OWNER_MARKER_NAME, dir_fd=namespace_fd, follow_symlinks=False)

    assert stat.S_ISREG(metadata.st_mode), "the ownership marker must be a regular file"
    assert primitives._read_marker(namespace_fd) == OWNER_MARKER_BYTES, (
        "the marker must carry the owned bytes"
    )
