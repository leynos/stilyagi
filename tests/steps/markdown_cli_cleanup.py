"""BDD steps for safe Markdown cache cleanup."""

from __future__ import annotations

import pytest
from pytest_bdd import given, then, when

from tests.steps.markdown_cli_inspection import (
    MarkdownInspectionState,
    _last_run,
    _root,
    _run_cli,
    _write_source,
)


@given(
    "a project with a populated cache and an outside symlink",
    target_fixture="markdown_inspection_state",
)
def project_with_cache_and_outside_symlink(
    markdown_inspection_state: MarkdownInspectionState,
) -> MarkdownInspectionState:
    """Populate owned cache state beside a source and an external sentinel."""
    source = _write_source(markdown_inspection_state, "docs/notes.md", b"# Notes\n")
    (_root(markdown_inspection_state) / "outside-sentinel.md").write_bytes(
        b"outside stays unchanged\n"
    )
    outside_target = _root(markdown_inspection_state).parent / "outside-target.md"
    outside_target.write_bytes(b"outside target stays unchanged\n")
    link = _root(markdown_inspection_state) / "outside-link.md"
    try:
        link.symlink_to(outside_target)
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
    return markdown_inspection_state


@when("I clean the project twice")
def clean_project_twice(markdown_inspection_state: MarkdownInspectionState) -> None:
    """Run the actual cleanup command twice from the project working directory."""
    _run_cli(markdown_inspection_state, "clean")
    _run_cli(markdown_inspection_state, "clean")


@then("cleanup removes only cache state and preserves both targets")
def cleanup_is_bounded_and_repeatable(
    markdown_inspection_state: MarkdownInspectionState,
) -> None:
    """Verify owned namespace removal, repeatability and source preservation."""
    runs = markdown_inspection_state["runs"]
    first, second = runs[-2:]
    cache_namespace = (
        _root(markdown_inspection_state) / ".stilyagi_cache" / "stilyagi-v1"
    )

    assert first.returncode == 0, "expected the first cleanup to succeed"
    assert second.returncode == 0, "expected repeated cleanup to succeed"
    assert "cleaned 2 cache files in 1 namespaces" in first.stdout.decode(), (
        "expected the owned entry and marker to be removed"
    )
    assert "cleaned 0 cache files in 0 namespaces" in second.stdout.decode(), (
        "expected repeated cleanup to find no owned namespace"
    )
    assert not cache_namespace.exists(), "expected the owned cache namespace to be gone"
    for relative_path, original in markdown_inspection_state["sources"].items():
        assert (
            _root(markdown_inspection_state) / relative_path
        ).read_bytes() == original, f"expected {relative_path} to remain byte-identical"
    outside_target = markdown_inspection_state["outside_target"]
    assert outside_target.read_bytes() == b"outside target stays unchanged\n", (
        "expected cleanup not to follow the outside symlink"
    )
