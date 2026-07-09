"""Malformed-input coverage for maturin wheel compatibility helpers."""

from __future__ import annotations

import typing as typ
import zipfile

import pytest

from tests.test_maturin_build import _read_maturin_pins, _wheel_build_snapshot

if typ.TYPE_CHECKING:
    import pathlib


@pytest.mark.parametrize(
    ("toml_content", "exc_type", "match"),
    [
        (None, FileNotFoundError, r"pyproject\.toml"),
        (
            '[build-system]\nrequires = ["maturin==1.13.3"]\n',
            KeyError,
            r"dependency-groups",
        ),
        ('[dependency-groups]\ndev = ["maturin==1.13.3"]\n', KeyError, r"build-system"),
        (
            (
                "[dependency-groups]\n"
                'dev = ["pytest==8.4.2"]\n'
                "[build-system]\n"
                'requires = ["setuptools"]\n'
            ),
            AssertionError,
            "Could not locate",
        ),
        (
            (
                "[dependency-groups]\n"
                'dev = ["maturin==1.13.3"]\n'
                "[build-system]\n"
                'requires = "maturin==1.13.3"\n'
            ),
            TypeError,
            "Expected dependency list",
        ),
    ],
    ids=["no_file", "no_dev", "no_build", "no_pin", "bad_requires"],
)
def test_read_maturin_pins_raises(
    tmp_path: pathlib.Path,
    toml_content: str | None,
    exc_type: type[Exception],
    match: str,
) -> None:
    """read_maturin_pins raises the expected error for malformed pyproject.toml."""
    if toml_content is not None:
        (tmp_path / "pyproject.toml").write_text(toml_content)
    with pytest.raises(exc_type, match=match):
        _read_maturin_pins(tmp_path)


@pytest.mark.parametrize(
    ("wheel_payload", "metadata_payload", "expected_error"),
    [
        (None, None, (zipfile.BadZipFile, "File is not a zip file")),
        ("", "Name: stilyagi\n", (AssertionError, r"missing \.dist-info/WHEEL")),
        (
            "Wheel-Version: 1.0\nRoot-Is-Purelib: false\n",
            "Name: stilyagi\n",
            (AssertionError, "Could not parse maturin generator"),
        ),
        (
            "Wheel-Version: 1.0\nGenerator: maturin (1.13.3)\nRoot-Is-Purelib: false\n",
            "Name: stilyagi\n",
            (AssertionError, "missing Tag metadata"),
        ),
        (
            (
                "Wheel-Version: 1.0\n"
                "Generator: maturin (1.13.3)\n"
                "Root-Is-Purelib: false\n"
                "Tag: cp314-cp314-linux_x86_64\n"
            ),
            None,
            (AssertionError, r"missing \.dist-info/METADATA"),
        ),
    ],
    ids=["bad_zip", "no_wheel", "no_generator", "no_tag", "no_metadata"],
)
def test_wheel_build_snapshot_raises(
    tmp_path: pathlib.Path,
    wheel_payload: str | None,
    metadata_payload: str | None,
    expected_error: tuple[type[Exception], str],
) -> None:
    """wheel_build_snapshot raises focused errors for malformed wheels."""
    wheel_path = tmp_path / "malformed.whl"
    if wheel_payload is None:
        wheel_path.write_text("not a zip archive")
    else:
        with zipfile.ZipFile(wheel_path, "w") as archive:
            if wheel_payload:
                archive.writestr("stilyagi-0.1.0.dist-info/WHEEL", wheel_payload)
            if metadata_payload is not None:
                archive.writestr("stilyagi-0.1.0.dist-info/METADATA", metadata_payload)
    exc_type, match = expected_error
    with pytest.raises(exc_type, match=match):
        _wheel_build_snapshot(wheel_path)
