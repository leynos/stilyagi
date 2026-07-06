"""Tests for nearest-config resolution and CLI precedence."""

from __future__ import annotations

import pathlib
import textwrap

import pytest
from stilyagi import config


def _write_config(path: pathlib.Path, body: str) -> None:
    """Write a TOML config file with a trailing newline."""
    path.write_text(textwrap.dedent(body).strip() + "\n", encoding="utf-8")


def _write_discovered_cache_dir(tmp_path: pathlib.Path, cache_dir: str) -> None:
    """Write a discoverable pyproject config that sets one cache-dir."""
    _write_config(
        tmp_path / "pyproject.toml",
        f"""
        [tool.stilyagi]
        cache-dir = "{cache_dir}"
        """,
    )


def _make_markdown_target(directory: pathlib.Path) -> pathlib.Path:
    """Create one Markdown target file for config resolution."""
    target = directory / "note.md"
    target.write_text("# note\n", encoding="utf-8")
    return target


def test_nearest_config_wins_without_ancestor_merging(tmp_path: pathlib.Path) -> None:
    """The nearest config should win, without inheriting unrelated ancestors."""
    _write_config(
        tmp_path / "pyproject.toml",
        """
        [tool.stilyagi]
        cache-dir = ".root"

        [tool.stilyagi.lint]
        preview = true
        """,
    )

    nested = tmp_path / "docs"
    nested.mkdir()
    _write_config(
        nested / "stilyagi.toml",
        """
        cache-dir = ".child"
        """,
    )

    target = _make_markdown_target(nested)

    resolved = config.resolve_config_for_path(
        target,
        cli_overrides=None,
        explicit_config=None,
        isolated=False,
    )

    assert resolved.cache_dir == pathlib.Path(".child")
    assert resolved.lint.preview is False


def test_extend_chain_composes_in_order(tmp_path: pathlib.Path) -> None:
    """Explicit `extend` chains should layer in the declared order."""
    base_one = tmp_path / "base-one.toml"
    _write_config(
        base_one,
        """
        cache-dir = ".base-one"

        [lint]
        preview = true
        """,
    )

    base_two = tmp_path / "base=two.toml"
    _write_config(
        base_two,
        """
        cache-dir = ".base-two"

        [lint]
        preview = false
        """,
    )

    child_dir = tmp_path / "child"
    child_dir.mkdir()
    _write_config(
        child_dir / "stilyagi.toml",
        f"""
        extend = ["{base_one}", "{base_two}"]
        """,
    )

    target = child_dir / "file.md"
    target.write_text("# note\n", encoding="utf-8")

    resolved = config.resolve_config_for_path(
        target,
        cli_overrides=None,
        explicit_config=None,
        isolated=False,
    )

    assert resolved.cache_dir == pathlib.Path(".base-two")
    assert resolved.lint.preview is False


def test_extend_cycle_raises_a_typed_error(tmp_path: pathlib.Path) -> None:
    """Cycle detection should fail with the typed config error."""
    first = tmp_path / "first.toml"
    second = tmp_path / "second.toml"
    _write_config(
        first,
        f"""
        extend = "{second}"
        """,
    )
    _write_config(
        second,
        f"""
        extend = "{first}"
        """,
    )

    target = _make_markdown_target(tmp_path)

    with pytest.raises(config.InvalidConfigError, match=r"extend.*cycle detected"):
        config.resolve_config_for_path(
            target,
            cli_overrides=None,
            explicit_config=[first],
            isolated=True,
        )


def test_isolated_bypasses_discovery(tmp_path: pathlib.Path) -> None:
    """`--isolated` should ignore discovered config files and keep overrides."""
    _write_discovered_cache_dir(tmp_path, ".discovered")

    target = _make_markdown_target(tmp_path)

    resolved = config.resolve_config_for_path(
        target,
        cli_overrides={"cache-dir": ".cli"},
        explicit_config=None,
        isolated=True,
    )

    assert resolved.cache_dir == pathlib.Path(".cli")
    assert resolved.lint.preview is False


def test_explicit_config_path_and_inline_override_precedence(
    tmp_path: pathlib.Path,
) -> None:
    """Inline `--config` fragments should outrank named config files."""
    _write_discovered_cache_dir(tmp_path, ".discovered")

    named_config = tmp_path / "named=override.toml"
    _write_config(
        named_config,
        """
        cache-dir = ".file"
        """,
    )

    target = _make_markdown_target(tmp_path)

    resolved = config.resolve_config_for_path(
        target,
        cli_overrides=None,
        explicit_config=['cache-dir = ".inline"', str(named_config)],
        isolated=False,
    )

    assert resolved.cache_dir == pathlib.Path(".inline")


def test_cli_overrides_win_over_every_config_source(
    tmp_path: pathlib.Path,
) -> None:
    """Dedicated CLI flags should take precedence over every config source."""
    _write_discovered_cache_dir(tmp_path, ".discovered")

    explicit_config = tmp_path / "explicit.toml"
    _write_config(
        explicit_config,
        """
        cache-dir = ".explicit"
        """,
    )

    target = _make_markdown_target(tmp_path)

    resolved = config.resolve_config_for_path(
        target,
        cli_overrides={"cache-dir": ".cli"},
        explicit_config=[explicit_config, 'cache-dir = ".inline"'],
        isolated=False,
    )

    assert resolved.cache_dir == pathlib.Path(".cli")


@pytest.mark.parametrize(
    ("filename", "content", "match"),
    [
        pytest.param("missing.toml", None, r"missing\.toml.*config", id="missing"),
        pytest.param("broken.toml", "[lint\n", r"broken\.toml.*toml", id="malformed"),
    ],
)
def test_bad_explicit_config_raises_a_typed_error(
    tmp_path: pathlib.Path,
    filename: str,
    content: str | None,
    match: str,
) -> None:
    """Missing or malformed explicit config files should fail typed."""
    explicit_config = tmp_path / filename
    if content is not None:
        explicit_config.write_text(content, encoding="utf-8")

    target = _make_markdown_target(tmp_path)

    with pytest.raises(config.InvalidConfigError, match=match):
        config.resolve_config_for_path(
            target,
            cli_overrides=None,
            explicit_config=[str(explicit_config)],
            isolated=True,
        )
