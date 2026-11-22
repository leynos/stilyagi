"""Descriptor-anchored ownership rules for persistent cache storage."""

import os
import pathlib
import subprocess  # ruff: ignore[suspicious-subprocess-import] - trusted interpreter and fixed probe script.
import sys

import pytest
from stilyagi.cache import storage
from stilyagi.cache.model import (
    CACHE_NAMESPACE_NAME,
    OWNER_MARKER_BYTES,
    OWNER_MARKER_NAME,
    cache_entry_name,
)
from stilyagi.cache.storage import CacheStorageError, CacheStore

from tests.support.subprocess_env import python_module_environment

_FIFO_READ_PROBE = """
import os
import pathlib
import sys

from stilyagi.cache.model import (
    CACHE_NAMESPACE_NAME,
    OWNER_MARKER_BYTES,
    OWNER_MARKER_NAME,
    cache_entry_name,
)
from stilyagi.cache.storage import CacheStorageError, CacheStore

root = pathlib.Path(sys.argv[1])
kind = sys.argv[2]
namespace = root / "cache" / CACHE_NAMESPACE_NAME
namespace.mkdir(parents=True)
key = "e" * 64

if kind == "marker":
    os.mkfifo(namespace / OWNER_MARKER_NAME)
    try:
        CacheStore(pathlib.Path("cache"), invocation_cwd=root)
    except CacheStorageError:
        pass
    else:
        raise AssertionError("a FIFO owner marker must be refused")
else:
    (namespace / OWNER_MARKER_NAME).write_bytes(OWNER_MARKER_BYTES)
    os.mkfifo(namespace / cache_entry_name(key))
    with CacheStore(pathlib.Path("cache"), invocation_cwd=root) as store:
        try:
            store.read(key)
        except CacheStorageError:
            pass
        else:
            raise AssertionError("a FIFO cache entry must be refused")
"""


def test_store_lookup_creates_nothing_until_the_namespace_is_created(
    tmp_path: pathlib.Path,
) -> None:
    """Leave the filesystem untouched until the namespace create is asked for."""
    store = CacheStore(pathlib.Path("cache"), invocation_cwd=tmp_path)
    key = "a" * 64
    entry_name = cache_entry_name(key)
    cache_parent = tmp_path / "cache"
    namespace = cache_parent / CACHE_NAMESPACE_NAME

    with store:
        assert store.read(key) is None, "an absent namespace has no entries"
        assert not cache_parent.exists(), (
            "a lookup must not create the configured cache parent"
        )
        with pytest.raises(CacheStorageError, match="never created"):
            store.write(key, b'{"value":1}\n')

    assert not cache_parent.exists(), "a lookup-only store must create nothing at all"

    with CacheStore(pathlib.Path("cache"), invocation_cwd=tmp_path) as writer:
        writer.create_namespace()
        writer.write(key, b'{"value":1}\n')
        assert writer.read(key) == b'{"value":1}\n', "published bytes must roundtrip"

    assert (namespace / OWNER_MARKER_NAME).read_bytes() == OWNER_MARKER_BYTES, (
        "a created namespace must contain the exact ownership marker"
    )
    assert sorted(path.name for path in namespace.iterdir()) == [
        entry_name,
        OWNER_MARKER_NAME,
    ], "atomic publication must leave only the marker and final entry"


def test_store_reuses_a_namespace_created_by_a_previous_run(
    tmp_path: pathlib.Path,
) -> None:
    """Adopt an already-marked namespace without recreating or rewriting it."""
    key = "b" * 64
    namespace = tmp_path / "cache" / CACHE_NAMESPACE_NAME

    with CacheStore(pathlib.Path("cache"), invocation_cwd=tmp_path) as creator:
        creator.create_namespace()
        creator.write(key, b"first")

    marker_mtime = (namespace / OWNER_MARKER_NAME).stat().st_mtime_ns
    with CacheStore(pathlib.Path("cache"), invocation_cwd=tmp_path) as reader:
        reader.create_namespace()
        assert reader.read(key) == b"first", "an adopted namespace must serve its entry"

    assert (namespace / OWNER_MARKER_NAME).stat().st_mtime_ns == marker_mtime, (
        "adopting a marked namespace must not rewrite its owner marker"
    )


def test_store_trusts_invocation_root_but_refuses_symlinks_below_it(
    tmp_path: pathlib.Path,
) -> None:
    """Anchor at the chosen cwd while refusing linked cache descendants."""
    project = tmp_path / "project"
    project.mkdir()
    linked_cwd = tmp_path / "project-link"
    linked_cwd.symlink_to(project, target_is_directory=True)

    with CacheStore(pathlib.Path("cache"), invocation_cwd=linked_cwd) as store:
        store.create_namespace()
        store.write("a" * 64, b"owned")
        assert store.read("a" * 64) == b"owned", (
            "a linked invocation path must still support anchored cache I/O"
        )

    outside = tmp_path / "outside"
    outside.mkdir()
    (project / "linked-cache").symlink_to(outside, target_is_directory=True)
    with pytest.raises(CacheStorageError):
        CacheStore(pathlib.Path("linked-cache"), invocation_cwd=linked_cwd)
    assert not (outside / CACHE_NAMESPACE_NAME).exists(), (
        "a symlink beneath the trusted cwd must never create cache contents"
    )


def test_store_refuses_to_adopt_an_unmarked_namespace(
    tmp_path: pathlib.Path,
) -> None:
    """Preserve data when a cache namespace lacks the exact owner marker."""
    namespace = tmp_path / "cache" / CACHE_NAMESPACE_NAME
    namespace.mkdir(parents=True)
    sentinel = namespace / "keep.txt"
    sentinel.write_text("unowned", encoding="utf-8")

    with pytest.raises(CacheStorageError, match="not owned"):
        CacheStore(pathlib.Path("cache"), invocation_cwd=tmp_path)

    assert sentinel.read_text(encoding="utf-8") == "unowned", (
        "refusing an unmarked namespace must preserve its content"
    )


@pytest.mark.parametrize("fifo_kind", ["marker", "entry"])
def test_store_refuses_fifo_files_without_blocking(
    tmp_path: pathlib.Path,
    fifo_kind: str,
) -> None:
    """Reject FIFO markers and entries without waiting for a writer."""
    if not hasattr(os, "mkfifo"):
        pytest.skip("FIFO creation is unavailable on this platform")

    result = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] - fixed probe script, trusted paths, no shell.
        [
            sys.executable,
            "-c",
            _FIFO_READ_PROBE,
            str(tmp_path),
            fifo_kind,
        ],
        env=python_module_environment(),
        capture_output=True,
        check=False,
        timeout=5,
    )

    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")


def test_store_does_not_follow_owner_marker_symlink(
    tmp_path: pathlib.Path,
) -> None:
    """A valid-looking marker target does not establish namespace ownership."""
    outside_marker = tmp_path / "outside-marker"
    outside_marker.write_bytes(OWNER_MARKER_BYTES)
    namespace = tmp_path / "cache" / CACHE_NAMESPACE_NAME
    namespace.mkdir(parents=True)
    (namespace / OWNER_MARKER_NAME).symlink_to(outside_marker)

    with pytest.raises(CacheStorageError, match="owner marker"):
        CacheStore(pathlib.Path("cache"), invocation_cwd=tmp_path)

    assert outside_marker.read_bytes() == OWNER_MARKER_BYTES, (
        "checking a marker symlink must not modify its target"
    )


def test_store_refuses_symlinked_cache_root_without_touching_target(
    tmp_path: pathlib.Path,
) -> None:
    """Refuse a symlink root while preserving its outside target."""
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "sentinel.txt"
    sentinel.write_text("outside", encoding="utf-8")
    linked_root = tmp_path / "linked-cache"
    linked_root.symlink_to(outside, target_is_directory=True)

    with pytest.raises(CacheStorageError):
        CacheStore(linked_root, invocation_cwd=tmp_path)

    assert sentinel.read_text(encoding="utf-8") == "outside", (
        "refusing a symlinked root must leave the target untouched"
    )


def test_store_refuses_symlinked_cache_root_ancestor(
    tmp_path: pathlib.Path,
) -> None:
    """Keep a strict no-follow walk for roots outside the invocation cwd."""
    project = tmp_path / "project"
    project.mkdir()
    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(real_parent, target_is_directory=True)

    with pytest.raises(CacheStorageError):
        CacheStore(linked_parent / "cache", invocation_cwd=project)

    assert not (real_parent / "cache").exists(), (
        "refusing a symlinked ancestor must not create a cache under its target"
    )


def test_store_never_follows_entry_symlink_for_read_or_replace(
    tmp_path: pathlib.Path,
) -> None:
    """Read and replace cache entries without following entry symlinks."""
    outside = tmp_path / "outside.json"
    outside.write_text("outside", encoding="utf-8")
    store = CacheStore(pathlib.Path("cache"), invocation_cwd=tmp_path)
    key = "b" * 64
    namespace = tmp_path / "cache" / CACHE_NAMESPACE_NAME
    store.create_namespace()
    store.close()
    store = CacheStore(pathlib.Path("cache"), invocation_cwd=tmp_path)

    with store:
        entry = namespace / cache_entry_name(key)
        entry.symlink_to(outside)
        with pytest.raises(CacheStorageError):
            store.read(key)
        store.write(key, b"replacement")

    assert outside.read_text(encoding="utf-8") == "outside", (
        "reading and replacing an entry symlink must not touch its target"
    )
    assert entry.read_bytes() == b"replacement", (
        "the symlink entry must be replaced safely"
    )


def test_store_refuses_namespace_replacement_before_writing(
    tmp_path: pathlib.Path,
) -> None:
    """Reject a namespace swapped for a symlink before publishing an entry."""
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "sentinel.txt"
    sentinel.write_text("outside", encoding="utf-8")
    store = CacheStore(pathlib.Path("cache"), invocation_cwd=tmp_path)
    root = tmp_path / "cache"
    namespace = root / CACHE_NAMESPACE_NAME
    moved_namespace = root / "stilyagi-v1-moved"
    store.create_namespace()

    with store:
        namespace.rename(moved_namespace)
        namespace.symlink_to(outside, target_is_directory=True)
        with pytest.raises(CacheStorageError):
            store.write("c" * 64, b"must not be written")

    assert sentinel.read_text(encoding="utf-8") == "outside", (
        "a replaced namespace must not redirect writes outside the cache"
    )
    assert not (moved_namespace / cache_entry_name("c" * 64)).exists(), (
        "no entry must be published after namespace replacement"
    )


def test_failed_atomic_replace_keeps_old_entry_and_removes_temporary_file(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An interrupted publish preserves the previous entry and cleans its temp."""
    store = CacheStore(pathlib.Path("cache"), invocation_cwd=tmp_path)
    key = "d" * 64
    namespace = tmp_path / "cache" / CACHE_NAMESPACE_NAME
    store.create_namespace()

    with store:
        store.write(key, b"old")

        def fail_replace(*_args: object, **_kwargs: object) -> None:
            """Raise at publication after the temporary file is durable."""
            message = "injected replacement failure"
            raise OSError(message)

        monkeypatch.setattr(storage.os, "rename", fail_replace)
        with pytest.raises(CacheStorageError, match="injected replacement failure"):
            store.write(key, b"new")
        assert store.read(key) == b"old", (
            "failed publication must preserve the prior entry"
        )

    assert sorted(path.name for path in namespace.iterdir()) == [
        cache_entry_name(key),
        OWNER_MARKER_NAME,
    ], "failed publication must remove its temporary file"
