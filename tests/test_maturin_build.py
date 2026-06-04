"""Unit tests for maturin pin synchronization and wheel build output."""

from __future__ import annotations

import pathlib
import typing as typ

import pytest

from tests.support.maturin import (
    build_native_wheel_artifact,
    installed_maturin_version,
    read_expected_maturin_version,
    read_maturin_pins,
    toolchain_available,
    wheel_build_snapshot,
)

if typ.TYPE_CHECKING:
    from syrupy.assertion import SnapshotAssertion

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_maturin_pins_are_synchronized() -> None:
    """Maturin version pins stay aligned across build-system declarations."""
    pins = read_maturin_pins(REPOSITORY_ROOT)
    assert len(set(pins.values())) == 1, f"Expected one maturin pin, found {pins!r}"


def test_installed_maturin_matches_expected_pin() -> None:
    """The active maturin module matches the pinned development dependency."""
    installed = installed_maturin_version()
    if installed is None:
        pytest.skip("maturin is not installed.")
    expected = read_expected_maturin_version(REPOSITORY_ROOT)
    assert installed == expected, (
        f"Expected maturin {expected}, but {installed} is installed"
    )


# pytest-timeout can interrupt long native builds in the parent process rather
# than the maturin subprocess. Disable the test timeout and let the outer gate
# command's timeout own the build limit.
@pytest.mark.timeout(0)
def test_maturin_wheel_build_snapshot(
    tmp_path: pathlib.Path,
    snapshot: SnapshotAssertion,
) -> None:
    """Native wheel metadata and layout match the expected maturin output."""
    if not toolchain_available():
        pytest.skip("Rust toolchain or maturin unavailable.")

    expected = read_expected_maturin_version(REPOSITORY_ROOT)
    wheel_path = build_native_wheel_artifact(REPOSITORY_ROOT, tmp_path / "wheelhouse")
    snapshot_payload = wheel_build_snapshot(wheel_path)

    assert snapshot_payload["generator"] == expected, (
        f"Expected generator {expected!r}, found {snapshot_payload['generator']!r}"
    )
    assert snapshot_payload == snapshot, (
        "Built wheel metadata, file list, and build settings changed."
    )
