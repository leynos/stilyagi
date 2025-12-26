"""Unit tests for the stilyagi install helpers."""

from __future__ import annotations

import io
from zipfile import ZipFile

import pytest

from stilyagi import stilyagi_install


def test_load_install_manifest_skips_download_when_env_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Env override bypasses download and returns defaults."""
    download_called = False

    def _download_fail(*_: object, **__: object) -> None:
        nonlocal download_called
        download_called = True
        pytest.fail("download should be skipped when env is set")

    monkeypatch.setenv("STILYAGI_SKIP_MANIFEST_DOWNLOAD", "1")
    monkeypatch.setattr(stilyagi_install, "_download_packages_archive", _download_fail)

    manifest = stilyagi_install._load_install_manifest(  # type: ignore[attr-defined]
        packages_url="https://example.test/archive.zip",
        default_style_name="concordat",
    )

    assert download_called is False
    assert manifest.style_name == "concordat"
    assert manifest.vocab_name == "concordat"
    assert manifest.min_alert_level == "warning"


def test_load_install_manifest_uses_manifest_when_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Manifest embedded in archive is parsed and applied."""
    buffer = io.BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr(
            "concordat-0.0.1/stilyagi.toml",
            """[install]
style_name = "manifest-style"
vocab = "manifest-vocab"
min_alert_level = "error"
""",
        )

    monkeypatch.delenv("STILYAGI_SKIP_MANIFEST_DOWNLOAD", raising=False)
    monkeypatch.setattr(
        stilyagi_install,
        "_download_packages_archive",
        lambda *_args, **_kwargs: buffer.getvalue(),
    )

    manifest = stilyagi_install._load_install_manifest(  # type: ignore[attr-defined]
        packages_url="https://example.test/archive.zip",
        default_style_name="concordat",
    )

    assert manifest.style_name == "manifest-style"
    assert manifest.vocab_name == "manifest-vocab"
    assert manifest.min_alert_level == "error"


def test_load_install_manifest_defaults_when_no_manifest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defaults are used when archive lacks stilyagi.toml."""
    buffer = io.BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("concordat-0.0.1/.vale.ini", "StylesPath = styles\n")

    download_called = False
    extract_called = False

    def _download(*_args: object, **_kwargs: object) -> bytes:
        nonlocal download_called
        download_called = True
        return buffer.getvalue()

    def _extract(_bytes: bytes) -> bytes | None:
        nonlocal extract_called
        extract_called = True
        return None

    monkeypatch.delenv("STILYAGI_SKIP_MANIFEST_DOWNLOAD", raising=False)
    monkeypatch.setattr(stilyagi_install, "_download_packages_archive", _download)
    monkeypatch.setattr(stilyagi_install, "_extract_stilyagi_toml", _extract)

    manifest = stilyagi_install._load_install_manifest(  # type: ignore[attr-defined]
        packages_url="https://example.test/archive.zip",
        default_style_name="concordat",
    )

    assert download_called is True
    assert extract_called is True
    assert manifest.style_name == "concordat"
    assert manifest.vocab_name == "concordat"
    assert manifest.min_alert_level == "warning"


def test_load_install_manifest_falls_back_on_download_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Download errors return the default manifest."""

    def _download_fail(*_args: object, **_kwargs: object) -> bytes:
        raise RuntimeError

    monkeypatch.delenv("STILYAGI_SKIP_MANIFEST_DOWNLOAD", raising=False)
    monkeypatch.setattr(stilyagi_install, "_download_packages_archive", _download_fail)

    manifest = stilyagi_install._load_install_manifest(  # type: ignore[attr-defined]
        packages_url="https://example.test/archive.zip",
        default_style_name="concordat",
    )

    assert manifest.style_name == "concordat"
    assert manifest.vocab_name == "concordat"
    assert manifest.min_alert_level == "warning"
