"""Descriptor-anchored ownership rules for persistent cache storage."""

import pathlib

import pytest
from stilyagi.cache import storage
from stilyagi.cache.model import (
    CACHE_NAMESPACE_NAME,
    OWNER_MARKER_BYTES,
    OWNER_MARKER_NAME,
    cache_entry_name,
)
from stilyagi.cache.storage import CacheStorageError, CacheStore


def test_store_marks_owned_namespace_and_atomically_roundtrips_entry(
    tmp_path: pathlib.Path,
) -> None:
    """Mark a new namespace and atomically roundtrip one serialized entry."""
    store = CacheStore(pathlib.Path("cache"), invocation_cwd=tmp_path)
    key = "a" * 64
    entry_name = cache_entry_name(key)
    namespace = tmp_path / "cache" / CACHE_NAMESPACE_NAME

    with store:
        assert store.read(key) is None, "a newly created cache entry must be absent"
        store.write(key, b'{"value":1}\n')
        assert store.read(key) == b'{"value":1}\n', "published bytes must roundtrip"

    assert (namespace / OWNER_MARKER_NAME).read_bytes() == OWNER_MARKER_BYTES, (
        "a new namespace must contain the exact ownership marker"
    )
    assert sorted(path.name for path in namespace.iterdir()) == [
        entry_name,
        OWNER_MARKER_NAME,
    ], "atomic publication must leave only the marker and final entry"


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
    """Refuse every linked root component before creating a cache namespace."""
    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(real_parent, target_is_directory=True)

    with pytest.raises(CacheStorageError):
        CacheStore(linked_parent / "cache", invocation_cwd=tmp_path)

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
