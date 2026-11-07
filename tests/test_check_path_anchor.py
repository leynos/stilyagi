"""The glob anchor for a checked file, resolved at the check boundary.

Globs in a configuration are relative to the directory that holds the config
file as it was named. These tests pin that anchor, because resolving the config
file before taking its parent would silently move the anchor to wherever a
symlink points, and a per-file ignore such as ``docs/a.md`` would then stop
matching in the project that wrote it.
"""

import typing as typ

from stilyagi.check_paths import config_relative_path_for

if typ.TYPE_CHECKING:
    import pathlib


def test_a_plain_config_file_anchors_globs_at_its_own_directory(
    tmp_path: pathlib.Path,
) -> None:
    """A target below the config file's directory is named by its basename."""
    config_file = tmp_path / "stilyagi.toml"
    config_file.write_text("", encoding="utf-8")

    result = config_relative_path_for(tmp_path / "docs" / "a.md", config_file)

    assert result == "docs/a.md", (
        f"expected the target below the config directory, got {result}"
    )


def test_a_symlinked_config_file_keeps_the_anchor_in_the_project(
    tmp_path: pathlib.Path,
) -> None:
    """A symlinked config file does not move the anchor to the link target."""
    project = tmp_path / "project"
    elsewhere = tmp_path / "elsewhere"
    project.mkdir()
    elsewhere.mkdir()
    real_config = elsewhere / "stilyagi.toml"
    real_config.write_text("", encoding="utf-8")
    linked_config = project / "stilyagi.toml"
    linked_config.symlink_to(real_config)

    result = config_relative_path_for(project / "docs" / "a.md", linked_config)

    assert result == "docs/a.md", (
        "expected the anchor to stay in the project that names the config "
        f"file, got {result}"
    )
