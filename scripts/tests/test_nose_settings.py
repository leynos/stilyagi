"""Tests for parsing the ``[tool.nose]`` settings table.

The detector wrapper reads its pinned version, roots, channels, size floor,
surface, ranking bound, and exclusions from ``pyproject.toml``; these tests
cover that parsing boundary independently of the detector subprocess.
"""

import re
import textwrap
import typing as typ

import pytest
from duplication_gate_test_support import detector

if typ.TYPE_CHECKING:
    from pathlib import Path


def _settings_body(
    *,
    version: str | None = '"0.20.0"',
    roots: str = '["python/stilyagi"]',
    min_size: str = "24",
    surface: str | None = None,
) -> str:
    """Build a `[tool.nose]` table body from the supplied literal values."""
    lines = ["[tool.nose]"]
    if version is not None:
        lines.append(f"version = {version}")
    lines.extend((f"roots = {roots}", 'mode = "syntax"', f"min-size = {min_size}"))
    if surface is not None:
        lines.append(f"surface = {surface}")
    return "\n".join(lines) + "\n"


class TestLoadSettings:
    """`[tool.nose]` settings parsing."""

    def _write(self, tmp_path: Path, body: str) -> Path:
        """Write ``body`` to ``pyproject.toml`` under ``tmp_path``."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(textwrap.dedent(body), encoding="utf-8")
        return pyproject

    def test_loads_the_repository_settings(self, tmp_path: Path) -> None:
        """A complete table produces validated settings."""
        pyproject = self._write(
            tmp_path,
            """\
            [tool.nose]
            version = "0.20.0"
            roots = ["python/stilyagi"]
            mode = "syntax"
            min-size = 24
            surface = "all"
            top = 30
            exclude = ["**/generated/**"]
            """,
        )
        settings = detector.load_settings(pyproject)
        assert settings.roots == ("python/stilyagi",), "Roots must round-trip in order."
        assert settings.exclude == ("**/generated/**",), (
            "Exclude globs must round-trip."
        )
        assert settings.top == 30, "The ranking bound must round-trip."

    def test_top_and_exclude_are_optional(self, tmp_path: Path) -> None:
        """Omitted optional keys fall back to nose's own view size."""
        pyproject = self._write(
            tmp_path,
            """\
            [tool.nose]
            version = "0.20.0"
            roots = ["python/stilyagi"]
            mode = "syntax"
            min-size = 24
            """,
        )
        settings = detector.load_settings(pyproject)
        assert settings.top is None, "An omitted `top` must not bound the view."
        assert settings.surface == "all", "The gate defaults to the widened surface."

    @pytest.mark.parametrize(
        ("body", "diagnostic"),
        [
            (
                _settings_body(version=None),
                "tool.nose.version must be a non-empty string",
            ),
            (
                _settings_body(roots='"python/stilyagi"'),
                "tool.nose.roots must be an array of strings",
            ),
            (
                _settings_body(min_size="0"),
                "tool.nose.min-size must be a positive integer",
            ),
            (
                _settings_body(surface='"everything"'),
                "tool.nose.surface must be 'default' or 'all'",
            ),
        ],
        ids=["missing-version", "string-roots", "zero-min-size", "bad-surface"],
    )
    def test_rejects_malformed_settings(
        self, tmp_path: Path, body: str, diagnostic: str
    ) -> None:
        """Malformed settings raise a configuration error."""
        pyproject = self._write(tmp_path, body)
        with pytest.raises(detector.GateConfigError, match=re.escape(diagnostic)):
            detector.load_settings(pyproject)
