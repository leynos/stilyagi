"""Fault classification for owned-cache cleanup's descriptor traversal."""

import errno
import os
import typing as typ

from stilyagi.cache import clean
from stilyagi.cache.model import (
    CACHE_NAMESPACE_NAME,
    OWNER_MARKER_BYTES,
    OWNER_MARKER_NAME,
    cache_entry_name,
)

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    import pathlib

    import pytest


def _marked_cache(parent: pathlib.Path) -> pathlib.Path:
    """Create one owned namespace under a configured cache parent."""
    namespace = parent / CACHE_NAMESPACE_NAME
    namespace.mkdir(parents=True)
    (namespace / OWNER_MARKER_NAME).write_bytes(OWNER_MARKER_BYTES)
    return namespace


def _fail_with(error: OSError) -> cabc.Callable[..., typ.NoReturn]:
    """Return a replacement primitive that raises ``error``."""

    def fail(*_args: object, **_kwargs: object) -> typ.NoReturn:
        """Refuse the patched descriptor operation."""
        raise error

    return fail


def test_clean_reports_a_marker_read_failure(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Report an unreadable owner marker while leaving the namespace in place."""
    namespace = _marked_cache(tmp_path / "cache")
    (namespace / cache_entry_name("a" * 64)).write_bytes(b"owned")
    original_require = clean._require_safe_cleanup_support

    def require_then_patch() -> None:
        """Validate native support before injecting the marker read fault."""
        original_require()
        monkeypatch.setattr(
            clean, "_read_marker", _fail_with(OSError(errno.EIO, "injected"))
        )
        monkeypatch.setattr(clean, "_require_safe_cleanup_support", original_require)

    monkeypatch.setattr(clean, "_require_safe_cleanup_support", require_then_patch)

    result = clean.clean_cache_tree(tmp_path)

    assert result.errors, "an unreadable marker must be reported"
    assert namespace.is_dir(), "a namespace with an unreadable marker must survive"
    assert (namespace / cache_entry_name("a" * 64)).read_bytes() == b"owned", (
        "unreadable ownership must not authorize deletion"
    )


def test_clean_reports_a_directory_identity_failure(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Report a namespace whose identity cannot be established."""
    namespace = _marked_cache(tmp_path / "cache")
    original_require = clean._require_safe_cleanup_support

    def require_then_patch() -> None:
        """Validate native support before injecting the identity fault."""
        original_require()
        monkeypatch.setattr(
            clean, "_directory_identity", _fail_with(OSError(errno.EIO, "injected"))
        )
        monkeypatch.setattr(clean, "_require_safe_cleanup_support", original_require)

    monkeypatch.setattr(clean, "_require_safe_cleanup_support", require_then_patch)

    result = clean.clean_cache_tree(tmp_path)

    assert result.errors, "an unreadable directory identity must be reported"
    assert namespace.is_dir(), "an unverifiable namespace must survive cleanup"


def test_clean_reports_a_non_regular_marker(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Refuse a marker that stopped being a regular file."""
    namespace = _marked_cache(tmp_path / "cache")
    marker = namespace / OWNER_MARKER_NAME
    marker.unlink()
    os.mkfifo(marker)
    original_require = clean._require_safe_cleanup_support

    def require_then_patch() -> None:
        """Accept the marker read so identity verification must catch the FIFO."""
        original_require()
        monkeypatch.setattr(clean, "_read_marker", lambda _fd: OWNER_MARKER_BYTES)
        monkeypatch.setattr(clean, "_require_safe_cleanup_support", original_require)

    monkeypatch.setattr(clean, "_require_safe_cleanup_support", require_then_patch)

    result = clean.clean_cache_tree(tmp_path)

    assert any("not a regular file" in error for error in result.errors), (
        "a marker that is no longer a regular file must be reported"
    )
    assert namespace.is_dir(), "a namespace with a FIFO marker must survive cleanup"


def test_clean_reports_a_failed_entry_listing(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Report a namespace whose directory entries cannot be read."""
    namespace = _marked_cache(tmp_path / "cache")
    (namespace / cache_entry_name("b" * 64)).write_bytes(b"owned")
    original_require = clean._require_safe_cleanup_support

    def require_then_patch() -> None:
        """Validate native support before refusing the entry listing."""
        original_require()
        monkeypatch.setattr(
            clean, "_directory_entries", _fail_with(OSError(errno.EIO, "injected"))
        )
        monkeypatch.setattr(clean, "_require_safe_cleanup_support", original_require)

    monkeypatch.setattr(clean, "_require_safe_cleanup_support", require_then_patch)

    result = clean.clean_cache_tree(tmp_path)

    assert result.errors, "a failed entry listing must be reported"
    assert namespace.is_dir(), "an unlistable namespace must survive cleanup"


def test_clean_skips_a_directory_named_like_a_cache_entry(
    tmp_path: pathlib.Path,
) -> None:
    """Never unlink a directory that carries a recognized cache entry name."""
    namespace = _marked_cache(tmp_path / "cache")
    lookalike = namespace / cache_entry_name("c" * 64)
    lookalike.mkdir()

    result = clean.clean_cache_tree(tmp_path)

    assert lookalike.is_dir(), "a directory must not be removed as a cache leaf"
    assert result.preserved_unknown_entries >= 1, (
        "the surviving entry-named directory must be counted as preserved"
    )


def test_clean_removes_a_symlinked_cache_entry_without_following_it(
    tmp_path: pathlib.Path,
) -> None:
    """Unlink a cache-entry symlink while leaving its target intact."""
    namespace = _marked_cache(tmp_path / "cache")
    target = tmp_path / "outside-target"
    target.write_bytes(b"outside")
    (namespace / cache_entry_name("d" * 64)).symlink_to(target)

    result = clean.clean_cache_tree(tmp_path)

    assert not result.errors, "a symlink leaf is removable without error"
    assert target.read_bytes() == b"outside", "the symlink target must survive"
    assert not namespace.exists(), "the emptied namespace must be removed"


def test_clean_reports_a_marker_replaced_before_removal(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Refuse namespace removal when the marker was swapped after it was read."""
    namespace = _marked_cache(tmp_path / "cache")
    marker = namespace / OWNER_MARKER_NAME
    original_has_preserved = clean._namespace_has_preserved_entries
    original_require = clean._require_safe_cleanup_support
    replaced = False

    def replace_marker_then_report_empty(owned: clean._OwnedNamespace) -> bool:
        """Swap the marker for a new inode immediately before namespace removal."""
        nonlocal replaced
        should_stop = original_has_preserved(owned)
        if not replaced:
            # Hold the original inode open through a link so the filesystem cannot
            # hand its number to the replacement marker.
            hold = namespace / "marker-hold"
            os.link(marker, hold)
            marker.unlink()
            marker.write_bytes(b"replacement")
            hold.unlink()
            replaced = True
        return should_stop

    def require_then_patch() -> None:
        """Validate native support before replacing the marker in place."""
        original_require()
        monkeypatch.setattr(
            clean, "_namespace_has_preserved_entries", replace_marker_then_report_empty
        )
        monkeypatch.setattr(clean, "_require_safe_cleanup_support", original_require)

    monkeypatch.setattr(clean, "_require_safe_cleanup_support", require_then_patch)

    result = clean.clean_cache_tree(tmp_path)

    assert replaced, "cleanup must reach the marker recheck"
    assert any("marker was replaced" in error for error in result.errors), (
        "a marker swapped for another inode must be reported"
    )
    assert namespace.is_dir(), "the namespace must survive a replaced marker"
    assert marker.read_bytes() == b"replacement", (
        "cleanup must not resurrect an ownership marker over a replacement"
    )


def test_clean_reports_a_directory_changed_during_traversal(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Report a child whose identity changed between stat and open."""
    project = tmp_path / "project"
    project.mkdir()
    (project / "child").mkdir()
    original_fstat = os.fstat
    original_require = clean._require_safe_cleanup_support
    swapped = False

    def swap_identity(_descriptor: int) -> os.stat_result:
        """Report a different inode once to simulate a concurrent replacement."""
        nonlocal swapped
        metadata = original_fstat(_descriptor)
        if not swapped and metadata.st_ino:
            swapped = True
            return os.stat_result((
                metadata.st_mode,
                metadata.st_ino + 1,
                metadata.st_dev,
                metadata.st_nlink,
                metadata.st_uid,
                metadata.st_gid,
                metadata.st_size,
                metadata.st_atime,
                metadata.st_mtime,
                metadata.st_ctime,
            ))
        return metadata

    def require_then_patch() -> None:
        """Validate native support before replacing the identity observation."""
        original_require()
        monkeypatch.setattr(clean.os, "fstat", swap_identity)
        monkeypatch.setattr(clean, "_require_safe_cleanup_support", original_require)

    monkeypatch.setattr(clean, "_require_safe_cleanup_support", require_then_patch)

    result = clean.clean_cache_tree(tmp_path)

    assert any("changed during traversal" in error for error in result.errors), (
        "a child replaced between stat and open must be reported"
    )


def test_clean_reports_a_root_open_failure(tmp_path: pathlib.Path) -> None:
    """Report an unopenable configured root instead of raising."""
    missing = tmp_path / "missing"

    result = clean.clean_cache_tree(missing)

    assert result.errors, "an unopenable root must produce a reported failure"
    assert result.removed_files == 0, "an unopenable root removes nothing"


def test_clean_reports_a_child_directory_open_failure(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Report a traversed directory that cannot be opened safely."""
    project = tmp_path / "project"
    project.mkdir()
    child = project / "child"
    child.mkdir()
    original_open = os.open
    original_require = clean._require_safe_cleanup_support

    def refuse_child(path: str, flags: int, *, dir_fd: int | None = None) -> int:
        """Refuse the directory open after the root has been anchored."""
        if path == "child":
            raise PermissionError(errno.EACCES, "denied")
        return original_open(path, flags, dir_fd=dir_fd)

    def require_then_patch() -> None:
        """Validate native support before refusing the child open."""
        original_require()
        monkeypatch.setattr(clean.os, "open", refuse_child)
        monkeypatch.setattr(clean, "_require_safe_cleanup_support", original_require)

    monkeypatch.setattr(clean, "_require_safe_cleanup_support", require_then_patch)

    result = clean.clean_cache_tree(tmp_path)

    assert any("child" in error for error in result.errors), (
        "an unopenable child directory must be attributed to its path"
    )


def test_clean_reports_a_root_listing_failure(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Report a root whose entries cannot be listed."""
    original_require = clean._require_safe_cleanup_support

    def require_then_patch() -> None:
        """Validate native support before refusing the root listing."""
        original_require()
        monkeypatch.setattr(
            clean, "_directory_entries", _fail_with(OSError(errno.EIO, "injected"))
        )
        monkeypatch.setattr(clean, "_require_safe_cleanup_support", original_require)

    monkeypatch.setattr(clean, "_require_safe_cleanup_support", require_then_patch)

    result = clean.clean_cache_tree(tmp_path)

    assert result.errors, "an unlistable root must be reported"


def test_clean_counts_an_unremovable_owned_file(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep an owned-looking leaf that cannot be removed and report it."""
    namespace = _marked_cache(tmp_path / "cache")
    blocked = cache_entry_name("e" * 64)
    (namespace / blocked).write_bytes(b"owned")
    original_unlink = os.unlink
    original_require = clean._require_safe_cleanup_support

    def refuse_entry(path: str, *, dir_fd: int | None = None) -> None:
        """Refuse the cache leaf while allowing the marker removal."""
        if path == blocked:
            raise PermissionError(errno.EACCES, "denied")
        original_unlink(path, dir_fd=dir_fd)

    def require_then_patch() -> None:
        """Validate native support before refusing the leaf deletion."""
        original_require()
        monkeypatch.setattr(clean.os, "unlink", refuse_entry)
        monkeypatch.setattr(clean, "_require_safe_cleanup_support", original_require)

    monkeypatch.setattr(clean, "_require_safe_cleanup_support", require_then_patch)

    result = clean.clean_cache_tree(tmp_path)

    assert (namespace / blocked).read_bytes() == b"owned", (
        "an undeletable owned leaf must remain in place"
    )
    assert result.errors, "the failed leaf removal must be reported"
