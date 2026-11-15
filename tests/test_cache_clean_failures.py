"""Fault classification for owned-cache cleanup's descriptor traversal."""

import errno
import os
import typing as typ

import pytest
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


class _TraversalFault(typ.NamedTuple):
    """One injected traversal fault and the diagnostic prefix it must produce.

    `spared_calls` lets the root list itself before the fault fires. The root
    must list once for cleanup to find the namespace at all, so faulting every
    call would exercise the root case rather than the namespace one.
    """

    primitive: str
    location: str
    spared_calls: int = 0


@pytest.mark.parametrize(
    "fault",
    [
        pytest.param(
            _TraversalFault("_read_marker", "cache/stilyagi-v1/owner.json"),
            id="marker-read",
        ),
        pytest.param(
            _TraversalFault("_directory_identity", "cache/stilyagi-v1"),
            id="directory-identity",
        ),
        pytest.param(_TraversalFault("_directory_entries", "."), id="root-listing"),
        pytest.param(
            _TraversalFault("_directory_entries", "cache", spared_calls=1),
            id="namespace-listing",
        ),
    ],
)
def test_clean_reports_a_traversal_fault_and_keeps_the_namespace(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: _TraversalFault,
) -> None:
    """Attribute each descriptor fault to its location without deleting anything."""
    namespace = _marked_cache(tmp_path / "cache")
    owned_entry = namespace / cache_entry_name("a" * 64)
    owned_entry.write_bytes(b"owned")
    _inject_after_support_check(
        monkeypatch,
        clean,
        fault.primitive,
        _fault_after(fault.spared_calls, getattr(clean, fault.primitive)),
    )

    result = clean.clean_cache_tree(tmp_path)

    assert any(error.startswith(fault.location) for error in result.errors), (
        "the fault must be attributed to the path it happened at"
    )
    assert namespace.is_dir(), "a namespace with an unreadable part must survive"
    assert owned_entry.read_bytes() == b"owned", (
        "an unverifiable namespace must not authorize deleting its entries"
    )


def _marked_cache(parent: pathlib.Path) -> pathlib.Path:
    """Create one owned namespace under a configured cache parent."""
    namespace = parent / CACHE_NAMESPACE_NAME
    namespace.mkdir(parents=True)
    (namespace / OWNER_MARKER_NAME).write_bytes(OWNER_MARKER_BYTES)
    return namespace


def _fault_after(
    spared_calls: int,
    call_through: cabc.Callable[..., object],
) -> cabc.Callable[..., object]:
    """Return a primitive that serves ``spared_calls`` calls, then raises.

    A zero count refuses immediately. The counted form exists for primitives
    whose first call is legitimate — the root must list itself before cleanup
    can even find the namespace it is meant to fault.

    Returns
    -------
    Callable
        The replacement primitive, ready to be monkeypatched in.
    """
    remaining = [spared_calls]

    def fail(*args: object, **kwargs: object) -> object:
        """Serve the spared calls, then refuse the patched operation."""
        remaining[0] -= 1
        if remaining[0] < 0:
            raise OSError(errno.EIO, "injected")
        return call_through(*args, **kwargs)

    return fail


def _inject_after_support_check(
    monkeypatch: pytest.MonkeyPatch,
    target: object,
    attribute: str,
    replacement: cabc.Callable[..., object],
) -> None:
    """Patch one primitive only once native descriptor support was verified.

    Cleanup validates support before it walks anything, so a patch installed
    too early could be installed before the check that gates traversal. Wrapping
    the check keeps the production ordering intact while still faulting the
    traversal itself.
    """
    original_require = clean._require_safe_cleanup_support

    def require_then_patch() -> None:
        """Validate native support, then install the injected fault."""
        original_require()
        monkeypatch.setattr(target, attribute, replacement)
        monkeypatch.setattr(clean, "_require_safe_cleanup_support", original_require)

    monkeypatch.setattr(clean, "_require_safe_cleanup_support", require_then_patch)


def test_clean_reports_a_non_regular_marker(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Refuse a marker that stopped being a regular file."""
    namespace = _marked_cache(tmp_path / "cache")
    marker = namespace / OWNER_MARKER_NAME
    marker.unlink()
    os.mkfifo(marker)
    _inject_after_support_check(
        monkeypatch, clean, "_read_marker", lambda _fd: OWNER_MARKER_BYTES
    )

    result = clean.clean_cache_tree(tmp_path)

    assert any("not a regular file" in error for error in result.errors), (
        "a marker that is no longer a regular file must be reported"
    )
    assert namespace.is_dir(), "a namespace with a FIFO marker must survive cleanup"


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

    _inject_after_support_check(
        monkeypatch,
        clean,
        "_namespace_has_preserved_entries",
        replace_marker_then_report_empty,
    )

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

    _inject_after_support_check(monkeypatch, clean.os, "fstat", swap_identity)

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

    def refuse_child(path: str, flags: int, *, dir_fd: int | None = None) -> int:
        """Refuse the directory open after the root has been anchored."""
        if path == "child":
            raise PermissionError(errno.EACCES, "denied")
        return original_open(path, flags, dir_fd=dir_fd)

    _inject_after_support_check(monkeypatch, clean.os, "open", refuse_child)

    result = clean.clean_cache_tree(tmp_path)

    assert any("child" in error for error in result.errors), (
        "an unopenable child directory must be attributed to its path"
    )


def test_clean_counts_an_unremovable_owned_file(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep an owned-looking leaf that cannot be removed and report it."""
    namespace = _marked_cache(tmp_path / "cache")
    blocked = cache_entry_name("e" * 64)
    (namespace / blocked).write_bytes(b"owned")
    original_unlink = os.unlink

    def refuse_entry(path: str, *, dir_fd: int | None = None) -> None:
        """Refuse the cache leaf while allowing the marker removal."""
        if path == blocked:
            raise PermissionError(errno.EACCES, "denied")
        original_unlink(path, dir_fd=dir_fd)

    _inject_after_support_check(monkeypatch, clean.os, "unlink", refuse_entry)

    result = clean.clean_cache_tree(tmp_path)

    assert (namespace / blocked).read_bytes() == b"owned", (
        "an undeletable owned leaf must remain in place"
    )
    assert result.errors, "the failed leaf removal must be reported"
