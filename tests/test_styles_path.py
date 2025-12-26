"""Unit tests for the stilyagi install helpers."""

from __future__ import annotations

import typing as typ

from stilyagi import stilyagi_install

if typ.TYPE_CHECKING:
    from pathlib import Path


class TestNormaliseStylesPath:
    """Unit tests for _normalise_styles_path."""

    def test_relative_path_within_project(self, tmp_path: Path) -> None:
        """Relative path inside project root normalises to repo-relative entry."""
        project_root = tmp_path / "project"
        project_root.mkdir()
        ini_path = project_root / ".vale.ini"

        result = stilyagi_install._normalise_styles_path(  # type: ignore[attr-defined]
            styles_path="styles",
            ini_path=ini_path,
            project_root=project_root,
        )

        assert result == "styles/"

    def test_nested_relative_path(self, tmp_path: Path) -> None:
        """Nested relative path is normalised correctly."""
        project_root = tmp_path / "project"
        project_root.mkdir()
        ini_path = project_root / ".vale.ini"

        result = stilyagi_install._normalise_styles_path(  # type: ignore[attr-defined]
            styles_path=".vale/styles",
            ini_path=ini_path,
            project_root=project_root,
        )

        assert result == ".vale/styles/"

    def test_absolute_path_within_project(self, tmp_path: Path) -> None:
        """Absolute path inside project root normalises to repo-relative entry."""
        project_root = tmp_path / "project"
        project_root.mkdir()
        ini_path = project_root / ".vale.ini"
        styles_dir = project_root / "custom-styles"
        styles_dir.mkdir()

        result = stilyagi_install._normalise_styles_path(  # type: ignore[attr-defined]
            styles_path=str(styles_dir),
            ini_path=ini_path,
            project_root=project_root,
        )

        assert result == "custom-styles/"

    def test_path_outside_project_returns_none(self, tmp_path: Path) -> None:
        """Path outside project root returns None to skip gitignore update."""
        project_root = tmp_path / "project"
        project_root.mkdir()
        external_styles = tmp_path / "external-styles"
        external_styles.mkdir()
        ini_path = project_root / ".vale.ini"

        result = stilyagi_install._normalise_styles_path(  # type: ignore[attr-defined]
            styles_path=str(external_styles),
            ini_path=ini_path,
            project_root=project_root,
        )

        assert result is None

    def test_relative_path_escaping_project_returns_none(self, tmp_path: Path) -> None:
        """Relative path that escapes project root returns None."""
        project_root = tmp_path / "project"
        project_root.mkdir()
        ini_path = project_root / ".vale.ini"

        result = stilyagi_install._normalise_styles_path(  # type: ignore[attr-defined]
            styles_path="../sibling/styles",
            ini_path=ini_path,
            project_root=project_root,
        )

        assert result is None

    def test_trailing_slash_normalised(self, tmp_path: Path) -> None:
        """Trailing slash in input is normalised to single slash."""
        project_root = tmp_path / "project"
        project_root.mkdir()
        ini_path = project_root / ".vale.ini"

        result = stilyagi_install._normalise_styles_path(  # type: ignore[attr-defined]
            styles_path="styles/",
            ini_path=ini_path,
            project_root=project_root,
        )

        assert result == "styles/"
