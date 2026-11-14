"""BDD steps for safe Markdown cache cleanup."""

import typing as typ

import pytest
from pytest_bdd import given, then, when

from tests.steps.markdown_cli_inspection import (
    MarkdownInspectionState,
    _last_run,
    _root,
    _run_cli,
    _write_source,
)

if typ.TYPE_CHECKING:
    import pathlib


@given(
    "a project with a populated cache and outside symlinks",
    target_fixture="markdown_inspection_state",
)
def project_with_cache_and_outside_symlink(
    markdown_inspection_state: MarkdownInspectionState,
) -> MarkdownInspectionState:
    """Populate owned cache state and plant links out of it and into it.

    Three links are planted, because they prove different things. The one in
    the project root is never visited -- cleanup only descends into real
    directories -- so it proves nothing about following links and is kept as a
    plain preservation check. Two go inside the owned namespace, where the
    entry loop that deletes owned leaves does visit them; both point outside
    the project, so any byte lost would have to have been reached through a
    link. Their names differ in the one way that matters: the unrecognized one
    is skipped before any unlink is considered, while the recognized one
    reaches the unlink and proves it removes the link rather than its target.

    Returns
    -------
    MarkdownInspectionState
        The same fixture value, now holding a populated cache and the planted
        links.
    """
    source = _write_source(markdown_inspection_state, "docs/notes.md", b"# Notes\n")
    (_root(markdown_inspection_state) / "outside-sentinel.md").write_bytes(
        b"outside stays unchanged\n"
    )
    outside_target = _root(markdown_inspection_state).parent / "outside-target.md"
    outside_target.write_bytes(b"outside target stays unchanged\n")
    outside_link = _root(markdown_inspection_state) / "outside-link.md"
    try:
        outside_link.symlink_to(outside_target)
    except OSError as error:
        pytest.skip(f"file symlinks are unavailable: {error}")
    markdown_inspection_state["outside_target"] = outside_target
    markdown_inspection_state["sources"]["outside-sentinel.md"] = (
        b"outside stays unchanged\n"
    )
    markdown_inspection_state["sources"]["docs/notes.md"] = source.read_bytes()
    _run_cli(markdown_inspection_state, "check", "docs/notes.md")
    completed = _last_run(markdown_inspection_state)
    assert completed.returncode == 0, "expected the cache-populating check to pass"
    _plant_links_inside_owned_namespace(markdown_inspection_state, outside_target)
    return markdown_inspection_state


#: A name the ownership classifier does not recognize. A recognizable name
#: would be unlinked and its outside target spared for the wrong reason: the
#: entry would be an owned leaf, not a link the traversal declined to follow.
_NAMESPACE_LINK_NAME = "inside-link.md"

#: A recognized cache-entry name, so the link reaches the unlink branch. All
#: zeros cannot collide with a real entry, whose key is a source digest.
_RECOGNIZED_LINK_NAME = f"{'0' * 64}.json"


def _plant_links_inside_owned_namespace(
    state: MarkdownInspectionState,
    outside_target: pathlib.Path,
) -> None:
    """Place both file symlinks inside the populated namespace, before cleanup."""
    namespace = _root(state) / ".stilyagi_cache" / "stilyagi-v1"
    assert namespace.is_dir(), "expected the check to create the owned namespace"
    recognized_target = _root(state).parent / "outside-entry-target.json"
    recognized_target.write_bytes(b'{"outside":"entry stays unchanged"}\n')
    state["recognized_link_target"] = recognized_target
    _symlink_or_skip(namespace / _NAMESPACE_LINK_NAME, outside_target)
    _symlink_or_skip(namespace / _RECOGNIZED_LINK_NAME, recognized_target)


def _symlink_or_skip(link: pathlib.Path, target: pathlib.Path) -> None:
    """Create one file symlink, skipping the scenario where links are unsupported."""
    try:
        link.symlink_to(target)
    except OSError as error:
        pytest.skip(f"file symlinks are unavailable: {error}")


@when("I clean the project twice")
def clean_project_twice(markdown_inspection_state: MarkdownInspectionState) -> None:
    """Run the actual cleanup command twice from the project working directory."""
    _run_cli(markdown_inspection_state, "clean")
    _run_cli(markdown_inspection_state, "clean")


@then("cleanup removes only cache state and preserves every outside target")
def cleanup_is_bounded_and_repeatable(
    markdown_inspection_state: MarkdownInspectionState,
) -> None:
    """Verify owned removal, repeatability, link safety and source preservation."""
    runs = markdown_inspection_state["runs"]
    first, second = runs[-2:]
    cache_namespace = (
        _root(markdown_inspection_state) / ".stilyagi_cache" / "stilyagi-v1"
    )

    assert first.returncode == 0, "expected the first cleanup to succeed"
    assert second.returncode == 0, "expected repeated cleanup to succeed"
    # Two owned leaves go: the entry the check wrote and the recognized link.
    # The unrecognized link is preserved, so the namespace keeps its marker and
    # itself: no namespace is claimed as removed.
    assert "cleaned 2 cache files in 0 namespaces; preserved 1 unknown entries" in (
        first.stdout.decode()
    ), "expected both owned leaves removed, the marker kept and the link preserved"
    assert "cleaned 0 cache files in 0 namespaces; preserved 1 unknown entries" in (
        second.stdout.decode()
    ), "expected repeated cleanup to find nothing further to remove"
    assert cache_namespace.is_dir(), (
        "a namespace holding a preserved entry must survive cleanup"
    )
    assert (cache_namespace / "owner.json").is_file(), (
        "a preserved namespace must keep the marker that identifies it"
    )
    assert (cache_namespace / _NAMESPACE_LINK_NAME).is_symlink(), (
        "an unrecognized link inside the namespace must not be unlinked"
    )
    assert not (cache_namespace / _RECOGNIZED_LINK_NAME).is_symlink(), (
        "a recognized link must be unlinked along with the other owned leaves"
    )
    for relative_path, original in markdown_inspection_state["sources"].items():
        assert (
            _root(markdown_inspection_state) / relative_path
        ).read_bytes() == original, f"expected {relative_path} to remain byte-identical"
    outside_target = markdown_inspection_state["outside_target"]
    assert outside_target.read_bytes() == b"outside target stays unchanged\n", (
        "expected cleanup not to follow the outside symlink"
    )
    recognized_target = markdown_inspection_state["recognized_link_target"]
    assert recognized_target.read_bytes() == b'{"outside":"entry stays unchanged"}\n', (
        "expected the unlink of a recognized link to remove the link, not its target"
    )
