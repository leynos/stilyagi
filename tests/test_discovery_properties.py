"""Property tests for deterministic mixed-source discovery."""

import pathlib
import shutil

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from stilyagi import config, discovery

PATH_COMPONENT = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789_",
    min_size=1,
    max_size=8,
).filter(lambda component: component not in {".", ".."})
REGISTERED_SUFFIX = st.sampled_from((".md", ".markdown", ".py", ".rs"))
UNREGISTERED_SUFFIX = st.sampled_from((".txt", ".json", ".py.txt"))
ANY_SUFFIX = st.one_of(REGISTERED_SUFFIX, UNREGISTERED_SUFFIX)


@st.composite
def relative_source_path_strings(
    draw: st.DrawFn,
) -> str:
    """Draw one relative path with a registered or unregistered final suffix."""
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
    suffix = draw(ANY_SUFFIX)
    return "/".join([*directories, f"{stem}{suffix}"])


# `deadline=None` because each example builds a real directory tree and then
# walks it twice. The elapsed time therefore tracks filesystem and machine load
# rather than the code under test, and the default 200 ms deadline fails under
# a loaded shared runner while the property itself still holds.
@settings(
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    max_examples=48,
    deadline=None,
)
@given(st.lists(relative_source_path_strings(), min_size=1, max_size=8, unique=True))
def test_discovery_is_sorted_independent_of_target_order(
    tmp_path: pathlib.Path,
    relative_paths: list[str],
) -> None:
    """Return each registered final suffix once in one resolved-path order."""
    root = tmp_path / "workspace"
    if root.exists():
        shutil.rmtree(root)
    root.mkdir()

    for relative_path in reversed(relative_paths):
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# title\n", encoding="utf-8")

    direct_targets = [root / relative_path for relative_path in relative_paths]
    files = discovery.discover_files(
        [root, *direct_targets],
        config.StilyagiConfig(),
    )
    reordered_files = discovery.discover_files(
        [*reversed(direct_targets), root],
        config.StilyagiConfig(),
    )

    expected = []
    for relative_path in relative_paths:
        syntax = discovery.syntax_for_path(pathlib.Path(relative_path))
        if syntax is None:
            continue
        expected.append(
            discovery.DiscoveredFile(
                reported_path=(
                    pathlib.PurePosixPath(root.as_posix()) / relative_path
                ).as_posix(),
                resolved_path=(root / relative_path).resolve(),
                syntax=syntax,
            )
        )
    expected.sort(key=lambda file: file.resolved_path.as_posix())

    assert files == expected, "expected files == expected"
    assert reordered_files == expected, "expected reordered_files == expected"
