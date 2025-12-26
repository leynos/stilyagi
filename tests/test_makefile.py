"""Unit tests for the stilyagi install helpers."""

from __future__ import annotations

import typing as typ

from stilyagi import stilyagi, stilyagi_install

if typ.TYPE_CHECKING:
    from pathlib import Path

DEFAULT_MANIFEST = stilyagi_install.InstallManifest(
    style_name="concordat",
    vocab_name="concordat",
    min_alert_level="warning",
)


def test_update_makefile_adds_phony_and_target(tmp_path: Path) -> None:
    """Replace any existing vale target and merge .PHONY entries."""
    makefile = tmp_path / "Makefile"
    makefile.write_text(
        """.PHONY: test

vale: ## old target
\t@echo outdated

lint:
\t@echo lint
""",
        encoding="utf-8",
    )

    stilyagi._update_makefile(  # type: ignore[attr-defined]
        makefile, manifest=DEFAULT_MANIFEST
    )

    contents = makefile.read_text(encoding="utf-8")
    assert ".PHONY: test vale" in contents, ".PHONY should include vale"
    assert "vale: ## Check prose" in contents, "vale target should be rewritten"
    assert "\t$(VALE) sync" in contents, "vale target should sync before linting"
    assert "\t$(VALE) --no-global --output line ." in contents, (
        "vale target should lint workspace"
    )
    assert "lint:" in contents, "Other targets should remain intact"


def test_update_makefile_creates_when_missing(tmp_path: Path) -> None:
    """Create Makefile with VALE variable, .PHONY, and target when absent."""
    makefile = tmp_path / "Makefile"
    stilyagi._update_makefile(makefile, manifest=DEFAULT_MANIFEST)  # type: ignore[attr-defined]

    contents = makefile.read_text(encoding="utf-8")
    assert "VALE ?= vale" in contents, "VALE variable should default to vale"
    assert any(line.lstrip().startswith(".PHONY") for line in contents.splitlines()), (
        ".PHONY line should be present"
    )
    assert "vale: ## Check prose" in contents, "vale target should be added"


def test_update_makefile_does_not_duplicate_phony(tmp_path: Path) -> None:
    """Leave existing .PHONY with vale untouched."""
    makefile = tmp_path / "Makefile"
    makefile.write_text(
        ".PHONY: vale test\n\nother: \n\t@echo hi\n",
        encoding="utf-8",
    )

    stilyagi._update_makefile(makefile, manifest=DEFAULT_MANIFEST)  # type: ignore[attr-defined]

    contents = makefile.read_text(encoding="utf-8")
    assert contents.count(".PHONY") == 1, ".PHONY should not be duplicated"
    assert "vale: ## Check prose" in contents, "vale target should remain present"


def test_update_makefile_adds_phony_when_absent(tmp_path: Path) -> None:
    """Insert .PHONY when missing and add vale target."""
    makefile = tmp_path / "Makefile"
    makefile.write_text("lint:\n\t@echo lint\n", encoding="utf-8")

    stilyagi._update_makefile(makefile, manifest=DEFAULT_MANIFEST)  # type: ignore[attr-defined]

    contents = makefile.read_text(encoding="utf-8")
    assert any(line.lstrip().startswith(".PHONY") for line in contents.splitlines()), (
        ".PHONY should be inserted when absent"
    )
    assert "vale: ## Check prose" in contents, (
        "vale target should be added when missing"
    )


def test_update_makefile_includes_post_sync_steps(tmp_path: Path) -> None:
    """Insert manifest-driven steps between sync and lint."""
    makefile = tmp_path / "Makefile"
    manifest = stilyagi_install.InstallManifest(
        style_name="concordat",
        vocab_name="concordat",
        min_alert_level="warning",
        post_sync_steps=(
            "uv run stilyagi update-tengo-map --source one --dest two --type true",
            "uv run stilyagi update-tengo-map --source three --dest four --type =",
        ),
    )

    stilyagi._update_makefile(makefile, manifest=manifest)  # type: ignore[attr-defined]

    contents = makefile.read_text(encoding="utf-8").splitlines()
    assert (
        "\tuv run stilyagi update-tengo-map --source one --dest two --type true"
        in contents
    ), "post sync steps should be added"
    assert (
        "\tuv run stilyagi update-tengo-map --source three --dest four --type ="
        in contents
    ), "multiple steps should be preserved"

    sync_idx = contents.index("\t$(VALE) sync")
    first_step_idx = contents.index(
        "\tuv run stilyagi update-tengo-map --source one --dest two --type true"
    )
    lint_idx = contents.index("\t$(VALE) --no-global --output line .")
    assert sync_idx < first_step_idx < lint_idx, (
        "steps should sit between sync and lint"
    )
