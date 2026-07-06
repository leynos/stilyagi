"""Property tests for deterministic Markdown discovery."""

from __future__ import annotations

import pathlib
import shutil
import typing as typ

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from stilyagi import config, discovery

if typ.TYPE_CHECKING:
    import collections.abc as cabc

PATH_COMPONENT = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789_",
    min_size=1,
    max_size=8,
).filter(lambda component: component not in {".", ".."})
MARKDOWN_SUFFIX = st.sampled_from((".md", ".markdown"))


@st.composite
def relative_markdown_path_strings(
    draw: cabc.Callable[[st.SearchStrategy[object]], object],
) -> str:
    """Draw one relative Markdown path string."""
    directories = draw(
        st.lists(
            PATH_COMPONENT.filter(
                lambda component: (
                    component
                    not in {".git", "build", "dist", "node_modules", "target", ".venv"}
                )
            ),
            min_size=0,
            max_size=3,
        ),
    )
    stem = draw(PATH_COMPONENT)
    suffix = draw(MARKDOWN_SUFFIX)
    return "/".join([*directories, f"{stem}{suffix}"])


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture], max_examples=48)
@given(st.lists(relative_markdown_path_strings(), min_size=1, max_size=8, unique=True))
def test_discovery_is_sorted_and_preserves_reported_paths(
    tmp_path: pathlib.Path,
    relative_paths: list[str],
) -> None:
    """Always return the same resolved order and POSIX reported paths."""
    root = tmp_path / "workspace"
    if root.exists():
        shutil.rmtree(root)
    root.mkdir()

    for relative_path in reversed(relative_paths):
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# title\n", encoding="utf-8")

    files = discovery.discover_markdown_files([root], config.StilyagiConfig())

    expected = [
        discovery.DiscoveredFile(
            reported_path=(
                pathlib.PurePosixPath(root.as_posix()) / relative_path
            ).as_posix(),
            resolved_path=(root / relative_path).resolve(),
        )
        for relative_path in relative_paths
    ]
    expected.sort(key=lambda file: file.resolved_path.as_posix())

    assert files == expected
