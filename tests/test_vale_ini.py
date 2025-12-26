"""Unit tests for the stilyagi install helpers."""

from __future__ import annotations

import typing as typ

from stilyagi import stilyagi, stilyagi_install

if typ.TYPE_CHECKING:
    from pathlib import Path


def test_update_vale_ini_merges_existing_values(tmp_path: Path) -> None:
    """Ensure required entries are inserted while preserving existing ones."""
    ini_path = tmp_path / ".vale.ini"
    ini_path.write_text(
        """StylesPath = styles

[legacy]
BasedOnStyles = Vale
""",
        encoding="utf-8",
    )

    stilyagi._update_vale_ini(  # type: ignore[attr-defined]
        ini_path=ini_path,
        packages_url="https://example.test/v9.9.9/concordat-9.9.9.zip",
        manifest=stilyagi_install.InstallManifest(
            style_name="concordat",
            vocab_name="concordat",
            min_alert_level="warning",
        ),
    )

    body = ini_path.read_text(encoding="utf-8")
    assert "Packages = https://example.test/v9.9.9/concordat-9.9.9.zip" in body, (
        "Packages URL should be written"
    )
    assert "MinAlertLevel = warning" in body, "MinAlertLevel should be set"
    assert "Vocab = concordat" in body, "Vocab should match style name"
    assert "StylesPath = styles" in body, "Existing root option should be preserved"
    assert "[legacy]" in body, "Existing sections should be retained"
    assert "BlockIgnores = (?m)^\\[\\^\\d+\\]:" in body, (
        "BlockIgnores pattern should be present"
    )


def test_update_vale_ini_creates_file_and_orders_sections(tmp_path: Path) -> None:
    """Create .vale.ini when missing and order sections deterministically."""
    ini_path = tmp_path / ".vale.ini"
    stilyagi._update_vale_ini(  # type: ignore[attr-defined]
        ini_path=ini_path,
        packages_url="https://example.test/v1.0.0/concordat-1.0.0.zip",
        manifest=stilyagi_install.InstallManifest(
            style_name="concordat",
            vocab_name="concordat",
            min_alert_level="warning",
        ),
    )

    body = ini_path.read_text(encoding="utf-8")
    assert "Packages = https://example.test/v1.0.0/concordat-1.0.0.zip" in body, (
        "Packages URL should be written when creating file"
    )
    assert "MinAlertLevel = warning" in body, "MinAlertLevel should be set"
    assert "Vocab = concordat" in body, "Vocab should match style name"
    section_positions = [
        body.index("[docs/**/*.{md,markdown,mdx}]"),
        body.index("[AGENTS.md]"),
        body.index("[*.{rs,ts,js,sh,py}]"),
        body.index("[README.md]"),
    ]
    assert section_positions == sorted(section_positions), "Sections should be ordered"


def test_update_vale_ini_strips_inline_comments_from_styles_path(
    tmp_path: Path,
) -> None:
    """Inline comments after StylesPath should be stripped."""
    ini_path = tmp_path / ".vale.ini"
    ini_path.write_text(
        "StylesPath = custom-styles  # project specific\n",
        encoding="utf-8",
    )

    stilyagi._update_vale_ini(  # type: ignore[attr-defined]
        ini_path=ini_path,
        packages_url="https://example.test/v1.0.0/concordat-1.0.0.zip",
        manifest=stilyagi_install.InstallManifest(
            style_name="concordat",
            vocab_name="concordat",
            min_alert_level="warning",
        ),
    )

    body = ini_path.read_text(encoding="utf-8")
    assert "StylesPath = custom-styles" in body, "StylesPath value should be preserved"
    assert "# project specific" not in body, "Inline comment should be stripped"
