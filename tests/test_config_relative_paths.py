"""Tests for the config-relative spelling used by per-file ignore globs."""

import pathlib
import typing as typ

from stilyagi.config.paths import config_relative_path

if typ.TYPE_CHECKING:
    import pytest

_DIFFERENT_DRIVES = "different drives"


def test_target_inside_anchor_is_a_plain_relative_path(
    tmp_path: pathlib.Path,
) -> None:
    """A target below the anchor needs no walk-up segments."""
    anchor = tmp_path / "docs"
    anchor.mkdir()
    config_file = anchor / "stilyagi.toml"

    assert config_relative_path(anchor / "a.md", config_file) == "a.md", (
        "expected a target beside the config to be named by its basename"
    )
    assert config_relative_path(anchor / "sub" / "b.md", config_file) == "sub/b.md", (
        "expected a nested target to keep its anchor-relative path"
    )


def test_target_outside_anchor_walks_up(tmp_path: pathlib.Path) -> None:
    """A target in a sibling tree is spelled with ``../`` segments."""
    anchor = tmp_path / "docs"
    anchor.mkdir()
    config_file = anchor / "stilyagi.toml"

    result = config_relative_path(tmp_path / "notes" / "c.md", config_file)

    assert result.startswith("../"), (
        f"expected a target outside the anchor to walk up, got {result}"
    )


def test_without_a_config_file_the_cwd_is_the_anchor(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no governing config the glob anchor is the working directory."""
    anchor = tmp_path / "project"
    anchor.mkdir()
    monkeypatch.chdir(anchor)

    assert config_relative_path(anchor / "d.md", config_file=None) == "d.md", (
        "expected the target's path relative to the working directory"
    )


def test_target_without_a_relative_spelling_falls_back_to_absolute(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A target on another Windows drive cannot be related to the anchor."""
    anchor = tmp_path / "docs"
    anchor.mkdir()
    config_file = anchor / "stilyagi.toml"
    target = tmp_path / "elsewhere" / "e.md"

    def raiser(
        self: pathlib.Path,
        other: pathlib.Path,
        *,
        walk_up: bool = False,
    ) -> pathlib.Path:
        """Match the builtin that pathlib raises for unrelated roots."""
        raise ValueError(_DIFFERENT_DRIVES)

    monkeypatch.setattr(pathlib.Path, "relative_to", raiser)

    assert config_relative_path(target, config_file) == target.resolve().as_posix(), (
        "expected an unrelated anchor to fall back to the absolute POSIX path"
    )
