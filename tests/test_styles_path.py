"""Unit tests for the stilyagi install helpers."""

from __future__ import annotations

import typing as typ

import pytest

from stilyagi import stilyagi_install

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    from pathlib import Path


class TestNormaliseStylesPath:
    """Unit tests for _normalise_styles_path."""

    @pytest.mark.parametrize(
        ("styles_path_input", "expected_result", "extra_setup"),
        [
            ("styles", "styles/", None),
            (".vale/styles", ".vale/styles/", None),
            (
                lambda tmp_path, project_root: str(project_root / "custom-styles"),
                "custom-styles/",
                lambda tmp_path, project_root: (project_root / "custom-styles").mkdir(),
            ),
            (
                lambda tmp_path, project_root: str(tmp_path / "external-styles"),
                None,
                lambda tmp_path, project_root: (tmp_path / "external-styles").mkdir(),
            ),
            ("../sibling/styles", None, None),
            ("styles/", "styles/", None),
        ],
        ids=[
            "relative_path_within_project",
            "nested_relative_path",
            "absolute_path_within_project",
            "path_outside_project_returns_none",
            "relative_path_escaping_project_returns_none",
            "trailing_slash_normalised",
        ],
    )
    def test_styles_path_normalisation(
        self,
        tmp_path: Path,
        styles_path_input: str | cabc.Callable[[Path, Path], str],
        expected_result: str | None,
        extra_setup: cabc.Callable[[Path, Path], None] | None,
    ) -> None:
        """Verify styles path normalisation for various scenarios."""
        project_root = tmp_path / "project"
        project_root.mkdir()
        ini_path = project_root / ".vale.ini"

        if extra_setup is not None:
            extra_setup(tmp_path, project_root)

        styles_path = (
            styles_path_input(tmp_path, project_root)
            if callable(styles_path_input)
            else styles_path_input
        )

        result = stilyagi_install._normalise_styles_path(  # type: ignore[attr-defined]
            styles_path=styles_path,
            ini_path=ini_path,
            project_root=project_root,
        )

        assert result == expected_result
