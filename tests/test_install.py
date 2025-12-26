"""Unit tests for the stilyagi install helpers."""

from __future__ import annotations

import typing as typ
from pathlib import Path

from stilyagi import stilyagi_install

if typ.TYPE_CHECKING:
    import pytest


def test_perform_install_honours_manifest_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Installation uses manifest-derived style and alert level."""
    project_root = tmp_path / "consumer"
    project_root.mkdir()

    _, ini_path, makefile_path = stilyagi_install._resolve_install_paths(  # type: ignore[attr-defined]
        cwd=project_root,
        project_root=Path(),
        vale_ini=Path(".vale.ini"),
        makefile=Path("Makefile"),
    )

    manifest = stilyagi_install.InstallManifest(
        style_name="custom-style",
        vocab_name="custom-vocab",
        min_alert_level="error",
        post_sync_steps=("echo prepare custom",),
    )

    monkeypatch.setattr(
        stilyagi_install,
        "_load_install_manifest",
        lambda **_kwargs: manifest,
        raising=True,
    )
    monkeypatch.setattr(
        stilyagi_install,
        "_resolve_release",
        lambda **_kwargs: (
            "2.0.0",
            "v2.0.0",
            "https://example.test/custom-style-2.0.0.zip",
        ),
        raising=True,
    )

    config = stilyagi_install.InstallConfig(
        owner="example",
        repo_name="custom-style",
        style_name="default-style",
        project_root=project_root,
        ini_path=ini_path,
        makefile_path=makefile_path,
    )

    message = stilyagi_install._perform_install(config=config)  # type: ignore[attr-defined]

    body = ini_path.read_text(encoding="utf-8")
    assert "MinAlertLevel = error" in body, "Manifest should set MinAlertLevel"
    assert "Vocab = custom-vocab" in body, "Manifest should override vocab"
    assert "BasedOnStyles = custom-style" in body, (
        "Style name should come from manifest"
    )
    makefile_body = makefile_path.read_text(encoding="utf-8")
    assert "\techo prepare custom" in makefile_body, (
        "Manifest post-sync steps should be written to the Makefile"
    )
    assert "custom-style 2.0.0" in message, (
        "Message should reflect manifest style/version"
    )
    gitignore_body = (project_root / ".gitignore").read_text(encoding="utf-8")
    assert "styles/" in gitignore_body, ".gitignore should include StylesPath"
