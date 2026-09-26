"""Shared fixtures for the config-resolution test modules.

These helpers write small TOML fixtures and Markdown lint targets used by
both the precedence tests in ``test_config_resolution.py`` and the
resolver-caching tests in ``test_config_resolution_caching.py``. Keeping
them here avoids duplicating the same fixture-writing logic in each module.
"""

import textwrap
import typing as typ

if typ.TYPE_CHECKING:
    import pathlib


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
