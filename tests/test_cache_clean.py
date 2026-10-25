"""Owned-cache cleanup preserves unknown files and outside targets."""

import os
import pathlib
import shutil

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from stilyagi import cli
from stilyagi.cache import clean
from stilyagi.cache.model import (
    CACHE_NAMESPACE_NAME,
    OWNER_MARKER_BYTES,
    OWNER_MARKER_NAME,
    cache_entry_name,
)


def _marked_cache(parent: pathlib.Path) -> pathlib.Path:
    """Create one owned namespace under a configured cache parent."""
    namespace = parent / CACHE_NAMESPACE_NAME
    namespace.mkdir(parents=True)
    (namespace / OWNER_MARKER_NAME).write_bytes(OWNER_MARKER_BYTES)
    return namespace


def test_clean_removes_owned_files_and_namespace_but_keeps_parent(
    tmp_path: pathlib.Path,
) -> None:
    """Remove entry and temp leaves without deleting the configured parent."""
    cache_parent = tmp_path / "custom-cache"
    cache_parent.mkdir()
    sentinel = cache_parent / "user-data"
    sentinel.write_text("keep", encoding="utf-8")
    namespace = _marked_cache(cache_parent)
    (namespace / cache_entry_name("a" * 64)).write_bytes(b"entry")
    (namespace / f".tmp-{'b' * 32}").write_bytes(b"temporary")

    result = clean.clean_cache_tree(tmp_path)

    assert result.removed_files == 3, "cleanup must remove owned leaves and marker"
    assert result.removed_namespaces == 1, "the emptied owned namespace must be removed"
    assert result.preserved_unknown_entries == 0, (
        "the namespace contains no unknown files"
    )
    assert not namespace.exists(), "the owned namespace must be gone after cleanup"
    assert sentinel.read_text(encoding="utf-8") == "keep", (
        "cleanup must preserve unrelated cache-parent content"
    )
    assert cache_parent.is_dir(), "cleanup must preserve the configured parent"
    assert clean.clean_cache_tree(tmp_path).removed_files == 0, (
        "repeated cleanup must be idempotent"
    )


def test_clean_preserves_unknown_content_and_unmarked_lookalikes(
    tmp_path: pathlib.Path,
) -> None:
    """Keep unknown bytes, markers, and unmarked namespace lookalikes."""
    marked = _marked_cache(tmp_path / "marked-parent")
    (marked / cache_entry_name("c" * 64)).write_bytes(b"owned")
    unknown = marked / "keep-me.bin"
    unknown.write_bytes(b"unknown")
    lookalike = tmp_path / "unmarked-parent" / CACHE_NAMESPACE_NAME
    lookalike.mkdir(parents=True)
    (lookalike / cache_entry_name("d" * 64)).write_bytes(b"not-owned")

    result = clean.clean_cache_tree(tmp_path)

    assert result.removed_files == 1, "only the recognized owned entry is removable"
    assert result.removed_namespaces == 0, "unknown content must keep its namespace"
    assert result.preserved_unknown_entries == 2, (
        "unknown content and owner marker survive"
    )
    assert unknown.read_bytes() == b"unknown", "unknown bytes must remain unchanged"
    assert (marked / OWNER_MARKER_NAME).read_bytes() == OWNER_MARKER_BYTES, (
        "the ownership marker must remain for a non-empty namespace"
    )
    assert lookalike.is_dir(), "an unmarked lookalike is not an owned namespace"
    assert (lookalike / cache_entry_name("d" * 64)).read_bytes() == b"not-owned", (
        "cleanup must preserve files in an unmarked lookalike"
    )


def test_clean_unlinks_cache_symlink_without_touching_its_target(
    tmp_path: pathlib.Path,
) -> None:
    """A recognized symlink is unlinked as a link, never followed."""
    outside = tmp_path.parent / f"{tmp_path.name}-outside-sentinel"
    outside.write_bytes(b"outside")
    namespace = _marked_cache(tmp_path / "cache")
    link = namespace / cache_entry_name("e" * 64)
    link.symlink_to(outside)

    result = clean.clean_cache_tree(tmp_path)

    assert result.removed_files == 2, "cleanup must remove the link and owner marker"
    assert not link.exists(), "the recognized entry link must be unlinked"
    assert not link.is_symlink(), "the recognized cache link must not survive cleanup"
    assert outside.read_bytes() == b"outside", (
        "unlinking a cache link must not touch its target"
    )
    outside.unlink()


def test_clean_visits_ignored_directories_but_prunes_git(
    tmp_path: pathlib.Path,
) -> None:
    """Find caches under ignored names and leave Git metadata untouched."""
    ignored = _marked_cache(tmp_path / ".ignored" / "cache")
    (ignored / cache_entry_name("f" * 64)).write_bytes(b"owned")
    git_cache = _marked_cache(tmp_path / ".git" / "objects" / "cache")
    (git_cache / cache_entry_name("1" * 64)).write_bytes(b"git-owned")

    result = clean.clean_cache_tree(tmp_path)

    assert result.removed_namespaces == 1, "ignored directories must still be searched"
    assert not ignored.exists(), (
        "a marked cache under an ignored directory must be cleaned"
    )
    assert (git_cache / cache_entry_name("1" * 64)).read_bytes() == b"git-owned", (
        "cleanup must prune Git metadata"
    )


def test_clean_skips_directory_symlinks_to_outside_trees(
    tmp_path: pathlib.Path,
) -> None:
    """A linked tree outside cwd is never traversed or changed."""
    outside = tmp_path.parent / f"{tmp_path.name}-outside-tree"
    namespace = _marked_cache(outside / "cache")
    (namespace / cache_entry_name("2" * 64)).write_bytes(b"outside")
    (tmp_path / "linked").symlink_to(outside, target_is_directory=True)

    result = clean.clean_cache_tree(tmp_path)

    assert result.removed_namespaces == 0, "cleanup must not enter linked outside trees"
    assert (namespace / cache_entry_name("2" * 64)).read_bytes() == b"outside", (
        "files reached only through an outside symlink must remain untouched"
    )


def test_clean_reports_namespace_replacement_before_deleting_entries(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep a cache intact when its parent-visible namespace is swapped."""
    cache_parent = tmp_path / "cache"
    namespace = _marked_cache(cache_parent)
    entry = namespace / cache_entry_name("3" * 64)
    entry.write_bytes(b"owned")
    outside = tmp_path / "outside"
    outside.mkdir()
    outside_sentinel = outside / "sentinel"
    outside_sentinel.write_bytes(b"outside")
    original_entries = clean._directory_entries
    namespace_identity = (namespace.stat().st_dev, namespace.stat().st_ino)
    replaced = False

    def replace_before_listing(directory_fd: int) -> tuple[os.DirEntry[str], ...]:
        """Swap the namespace path immediately before inspecting its entries."""
        nonlocal replaced
        metadata = os.fstat(directory_fd)
        if (metadata.st_dev, metadata.st_ino) == namespace_identity and not replaced:
            namespace.rename(cache_parent / "detached")
            namespace.symlink_to(outside, target_is_directory=True)
            replaced = True
        return original_entries(directory_fd)

    monkeypatch.setattr(clean, "_directory_entries", replace_before_listing)

    result = clean.clean_cache_tree(tmp_path)

    assert result.errors, "namespace replacement must be reported"
    assert (cache_parent / "detached" / entry.name).read_bytes() == b"owned", (
        "cleanup must leave the detached original namespace intact"
    )
    assert namespace.is_symlink(), (
        "cleanup must not replace the attacker-installed link"
    )
    assert outside_sentinel.read_bytes() == b"outside", (
        "outside files must remain untouched"
    )


def test_clean_continues_after_one_cache_file_cannot_be_deleted(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Report a failed leaf while cleaning another eligible namespace."""
    first = _marked_cache(tmp_path / "first")
    failed_name = cache_entry_name("4" * 64)
    (first / failed_name).write_bytes(b"blocked")
    second = _marked_cache(tmp_path / "second")
    (second / cache_entry_name("5" * 64)).write_bytes(b"remove")
    original_unlink = os.unlink

    def fail_one_unlink(path: str, *, dir_fd: int | None = None) -> None:
        """Fail one known cache file and pass every other deletion through."""
        if path == failed_name:
            message = "injected deletion failure"
            raise PermissionError(message)
        original_unlink(path, dir_fd=dir_fd)

    original_require = clean._require_safe_cleanup_support

    def require_then_patch_unlink() -> None:
        """Validate native support before installing the injected unlink fault."""
        original_require()
        monkeypatch.setattr(clean.os, "unlink", fail_one_unlink)
        monkeypatch.setattr(clean, "_require_safe_cleanup_support", original_require)

    monkeypatch.setattr(
        clean, "_require_safe_cleanup_support", require_then_patch_unlink
    )

    result = clean.clean_cache_tree(tmp_path)

    assert result.errors, "a failed leaf deletion must be reported"
    assert (first / failed_name).read_bytes() == b"blocked", (
        "the undeletable leaf must remain in place"
    )
    assert not second.exists(), "one deletion error must not stop other cleanup"


def test_clean_refuses_unsupported_descriptor_deletion(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Refuse cleanup when the platform lacks safe dir-fd operations."""
    monkeypatch.setattr(clean.os, "supports_dir_fd", set())

    with pytest.raises(OSError, match="descriptor-relative safe cache cleanup"):
        clean.clean_cache_tree(tmp_path)


@given(unknown_payloads=st.lists(st.binary(max_size=32), max_size=8))
@settings(
    max_examples=20,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_generated_unknown_bytes_survive_repeated_cleanup(
    tmp_path: pathlib.Path,
    unknown_payloads: list[bytes],
) -> None:
    """Preserve every generated unknown byte string across two clean runs."""
    shutil.rmtree(tmp_path)
    namespace = _marked_cache(tmp_path / "cache")
    owned_names = {
        cache_entry_name(f"{index:064x}") for index in range(len(unknown_payloads))
    }
    for owned_name in owned_names:
        (namespace / owned_name).write_bytes(b"owned")
    unknown = {
        f"unknown-{index}.bin": payload
        for index, payload in enumerate(unknown_payloads)
    }
    for filename, payload in unknown.items():
        (namespace / filename).write_bytes(payload)

    first = clean.clean_cache_tree(tmp_path)
    second = clean.clean_cache_tree(tmp_path)

    assert first.removed_files == len(owned_names) + (1 if not unknown else 0), (
        "first cleanup must remove generated owned entries and an empty marker"
    )
    assert first.preserved_unknown_entries == len(unknown), (
        "first cleanup must account for every generated unknown file"
    )
    assert second.removed_files == 0, "second cleanup must find no owned leaves"
    assert second.preserved_unknown_entries == len(unknown), (
        "second cleanup must continue preserving generated unknown files"
    )
    assert {name: (namespace / name).read_bytes() for name in unknown} == unknown, (
        "unknown generated bytes must survive both cleanup runs"
    )


def test_clean_command_needs_no_valid_config(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Run top-level clean without loading a malformed project config."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "stilyagi.toml").write_text("[broken\n", encoding="utf-8")
    namespace = _marked_cache(tmp_path / "custom")
    (namespace / cache_entry_name("6" * 64)).write_bytes(b"owned")

    assert cli.main(["clean"]) == 0, "clean must not require valid project config"

    captured = capsys.readouterr()
    assert not captured.err, "successful clean must not emit an error"
    assert (
        captured.out
        == "cleaned 2 cache files in 1 namespaces; preserved 0 unknown entries\n"
    ), "clean must report removed entries and namespaces"
    assert not namespace.exists(), "the CLI must remove the marked cache namespace"
