"""Unit tests for the mixed-package build spine."""

import pathlib

import pytest
from stilyagi import model, smoke

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_smoke_helper_exercises_the_public_rust_backed_boundary() -> None:
    """Call the same package smoke helper used by Makefile and CI."""
    document = smoke.smoke_installed_package()

    assert document == model.Document(
        syntax=model.Syntax.MARKDOWN,
        regions=(model.Region(kind="document", text="# Stilyagi smoke"),),
    )


def test_smoke_helper_rejects_a_document_without_regions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reject payloads that do not prove Rust returned source-backed content."""

    def extract_blank_document(
        _source: str,
        syntax: model.Syntax,
    ) -> model.Document:
        return model.Document(syntax=syntax)

    monkeypatch.setattr(smoke.engine, "extract_document", extract_blank_document)

    with pytest.raises(smoke.SmokeCheckError, match="at least one region"):
        smoke.smoke_installed_package()


def test_smoke_helper_rejects_a_document_with_unexpected_syntax(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reject payloads that do not preserve the requested syntax."""

    def extract_wrong_syntax(
        _source: str,
        _syntax: model.Syntax,
    ) -> model.Document:
        return model.Document(
            syntax=model.Syntax.PYTHON_DOCSTRING,
            regions=(model.Region(kind="document", text="# Stilyagi smoke"),),
        )

    monkeypatch.setattr(smoke.engine, "extract_document", extract_wrong_syntax)

    with pytest.raises(smoke.SmokeCheckError, match="unexpected syntax"):
        smoke.smoke_installed_package()


def test_makefile_keeps_build_and_release_on_the_shared_smoke_path() -> None:
    """Keep canonical local workflows wired to the same smoke boundary."""
    makefile = (REPOSITORY_ROOT / "Makefile").read_text(encoding="utf-8")

    assert "\nsmoke:" in makefile
    assert "\nsmoke-release:" in makefile
    assert ".venv/bin/python -m stilyagi.smoke" in makefile
    assert "$(MAKE) smoke" in makefile
    assert "smoke-release" in makefile
    assert "-not -path './.venv-release-smoke/*'" in makefile


def test_ci_workflow_calls_the_canonical_makefile_targets() -> None:
    """Make CI exercise Makefile targets instead of duplicating build logic."""
    workflow = (REPOSITORY_ROOT / ".github" / "workflows" / "smoke.yml").read_text(
        encoding="utf-8"
    )

    for command in (
        "make check-fmt",
        "make lint",
        "make test",
        "make release",
    ):
        assert f"run: {command}" in workflow

    assert "pull_request:" in workflow
    assert "push:" in workflow
    assert "branches:" in workflow
    assert "      - main" in workflow
    assert "mdformat-all" not in workflow
    assert "whitaker-installer" in workflow
