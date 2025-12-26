"""Unit tests for the stilyagi install helpers."""

from __future__ import annotations

import dataclasses as dc
import typing as typ

import pytest

from stilyagi import stilyagi_install


@dc.dataclass
class _ExpectedManifest:
    """Expected values for manifest parsing assertions."""

    style: str
    vocab: str
    min_alert: str
    post_sync_steps: tuple[str, ...] = ()


DEFAULT_MANIFEST = stilyagi_install.InstallManifest(
    style_name="concordat",
    vocab_name="concordat",
    min_alert_level="warning",
)


def _assert_default_manifest(manifest: stilyagi_install.InstallManifest) -> None:
    assert manifest.style_name == "concordat"
    assert manifest.vocab_name == "concordat"
    assert manifest.min_alert_level == "warning"
    assert manifest.post_sync_steps == ()


def test_parse_install_manifest_defaults() -> None:
    """Default manifest uses provided style for vocab and alert level."""
    manifest = stilyagi_install._parse_install_manifest(  # type: ignore[attr-defined]
        raw=None,
        default_style_name="concordat",
    )

    _assert_default_manifest(manifest)


@pytest.mark.parametrize(
    (
        "test_id",
        "raw_input",
        "expected",
    ),
    [
        (
            "applies_overrides",
            {
                "install": {
                    "style_name": "custom-style",
                    "vocab": "custom-vocab",
                    "min_alert_level": "error",
                }
            },
            _ExpectedManifest(
                style="custom-style", vocab="custom-vocab", min_alert="error"
            ),
        ),
        (
            "partial_missing_vocab",
            {
                "install": {
                    "style_name": "custom-style",
                    "min_alert_level": "error",
                }
            },
            _ExpectedManifest(
                style="custom-style", vocab="custom-style", min_alert="error"
            ),
        ),
        (
            "partial_missing_min_alert_level",
            {
                "install": {
                    "style_name": "custom-style",
                    "vocab": "custom-vocab",
                }
            },
            _ExpectedManifest(
                style="custom-style", vocab="custom-vocab", min_alert="warning"
            ),
        ),
        (
            "whitespace_only_fields",
            {
                "install": {
                    "style_name": "   ",
                    "vocab": " \t ",
                    "min_alert_level": "  ",
                }
            },
            _ExpectedManifest(
                style="concordat", vocab="concordat", min_alert="warning"
            ),
        ),
        (
            "captures_post_sync_steps",
            {
                "install": {
                    "post_sync_steps": [
                        {
                            "action": "update-tengo-map",
                            "source": " a ",
                            "dest": " b ",
                            "type": "=n",
                        }
                    ]
                }
            },
            _ExpectedManifest(
                style="concordat",
                vocab="concordat",
                min_alert="warning",
                post_sync_steps=(
                    (
                        "uv run stilyagi update-tengo-map --source ' a ' "
                        "--dest ' b ' --type =n"
                    ),
                ),
            ),
        ),
    ],
)
def test_parse_install_manifest_overrides(
    test_id: str,
    raw_input: dict[str, object],
    expected: _ExpectedManifest,
) -> None:
    """Manifest fields are normalised according to provided overrides."""
    manifest = stilyagi_install._parse_install_manifest(  # type: ignore[attr-defined]
        raw=raw_input,
        default_style_name="concordat",
    )

    assert manifest.style_name == expected.style
    assert manifest.vocab_name == expected.vocab
    assert manifest.min_alert_level == expected.min_alert
    assert manifest.post_sync_steps == expected.post_sync_steps


def test_parse_install_manifest_non_mapping_raw_uses_defaults() -> None:
    """Non-dict manifest inputs fall back to defaults."""
    manifest = stilyagi_install._parse_install_manifest(  # type: ignore[attr-defined]
        raw=typ.cast("dict[str, object] | None", "not-a-dict"),
        default_style_name="concordat",
    )

    _assert_default_manifest(manifest)


def test_parse_install_manifest_non_mapping_install_section_uses_defaults() -> None:
    """Non-dict install section triggers defaults."""
    manifest = stilyagi_install._parse_install_manifest(  # type: ignore[attr-defined]
        raw={"install": "not-a-dict"},
        default_style_name="concordat",
    )

    _assert_default_manifest(manifest)


def test_parse_install_manifest_rejects_string_post_sync_step() -> None:
    """String post_sync_steps are rejected as invalid."""
    with pytest.raises(TypeError):
        stilyagi_install._parse_install_manifest(  # type: ignore[attr-defined]
            raw={"install": {"post_sync_steps": " echo me "}},
            default_style_name="concordat",
        )


def test_parse_install_manifest_rejects_non_list_post_sync_steps() -> None:
    """Non-list post_sync_steps raises a clear error."""
    with pytest.raises(TypeError, match=r"list of tables"):
        stilyagi_install._parse_install_manifest(  # type: ignore[attr-defined]
            raw={"install": {"post_sync_steps": 123}},
            default_style_name="concordat",
        )


def test_parse_install_manifest_rejects_non_string_list_entries() -> None:
    """Lists must contain only tables."""
    with pytest.raises(TypeError, match=r"list of tables"):
        stilyagi_install._parse_install_manifest(  # type: ignore[attr-defined]
            raw={"install": {"post_sync_steps": ["ok"]}},
            default_style_name="concordat",
        )


def test_parse_install_manifest_allows_explicit_empty_list() -> None:
    """Empty list normalises to an empty tuple."""
    manifest = stilyagi_install._parse_install_manifest(  # type: ignore[attr-defined]
        raw={"install": {"post_sync_steps": []}},
        default_style_name="concordat",
    )

    assert manifest.post_sync_steps == ()


def test_parse_install_manifest_rejects_unknown_action() -> None:
    """Only update-tengo-map actions are supported."""
    with pytest.raises(ValueError, match=r"update-tengo-map"):
        stilyagi_install._parse_install_manifest(  # type: ignore[attr-defined]
            raw={
                "install": {
                    "post_sync_steps": [
                        {"action": "something-else", "source": "a", "dest": "b"}
                    ]
                }
            },
            default_style_name="concordat",
        )


def test_parse_install_manifest_rejects_invalid_value_type() -> None:
    """Value type must be among the allowed Tengo update options."""
    with pytest.raises(ValueError, match=r"one of"):
        stilyagi_install._parse_install_manifest(  # type: ignore[attr-defined]
            raw={
                "install": {
                    "post_sync_steps": [
                        {
                            "action": "update-tengo-map",
                            "source": "a",
                            "dest": "b",
                            "type": "invalid",
                        }
                    ]
                }
            },
            default_style_name="concordat",
        )
