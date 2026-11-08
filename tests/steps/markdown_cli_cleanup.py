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
    "a project with a populated cache and an outside symlink",
    target_fixture="markdown_inspection_state",
)
def project_with_cache_and_outside_symlink(
    markdown_inspection_state: MarkdownInspectionState,
) -> MarkdownInspectionState:
    """Populate owned cache state and plant a link out of it and into it.

    Two links are planted, because they prove different things. The one in the
    project root is never visited -- cleanup only descends into real
    directories -- so it proves nothing about following links and is kept as a
    plain preservation check. The one inside the owned namespace *is* visited,
    on the entry loop that deletes owned leaves, and that is where a follow
    would reach an outside file. Its target lives outside the project, so any
    byte it loses would have to have been reached through the link.

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
    _plant_link_inside_owned_namespace(markdown_inspection_state, outside_target)
    return markdown_inspection_state


#: A name the ownership classifier does not recognize. A recognizable name
#: would be unlinked and its outside target spared for the wrong reason: the
#: entry would be an owned leaf, not a link the traversal declined to follow.
_NAMESPACE_LINK_NAME = "inside-link.md"


def _plant_link_inside_owned_namespace(
    state: MarkdownInspectionState,
    outside_target: pathlib.Path,
) -> None:
    """Place one file symlink inside the populated namespace, before cleanup."""
    namespace = _root(state) / ".stilyagi_cache" / "stilyagi-v1"
    assert namespace.is_dir(), "expected the check to create the owned namespace"
    link = namespace / _NAMESPACE_LINK_NAME
    try:
        link.symlink_to(outside_target)
    except OSError as error:
        pytest.skip(f"file symlinks are unavailable: {error}")


@when("I clean the project twice")
def clean_project_twice(markdown_inspection_state: MarkdownInspectionState) -> None:
    """Run the actual cleanup command twice from the project working directory."""
    _run_cli(markdown_inspection_state, "clean")
    _run_cli(markdown_inspection_state, "clean")


@then("cleanup removes only cache state and preserves both targets")
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
    # The unrecognized link is preserved, so the namespace keeps its marker and
    # itself: the owned leaf goes, but no namespace is claimed as removed.
    assert "cleaned 1 cache files in 0 namespaces; preserved 1 unknown entries" in (
        first.stdout.decode()
    ), "expected the owned entry removed, the marker kept and the link preserved"
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
    for relative_path, original in markdown_inspection_state["sources"].items():
        assert (
            _root(markdown_inspection_state) / relative_path
        ).read_bytes() == original, f"expected {relative_path} to remain byte-identical"
    outside_target = markdown_inspection_state["outside_target"]
    assert outside_target.read_bytes() == b"outside target stays unchanged\n", (
        "expected cleanup not to follow the outside symlink"
    )
