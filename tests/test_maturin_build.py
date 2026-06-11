"""Unit tests for maturin pin synchronization and wheel build output."""

import pathlib
import shutil
import subprocess  # noqa: S404 - tests invoke pinned, trusted subprocess commands.
import sys
import typing as typ
import zipfile

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


def _resolve_uv() -> str:
    """Return the path to uv, preferring the project-local tool."""
    uv_candidates = [
        "uv",
        str(REPOSITORY_ROOT / ".uv-tools" / "uv"),
        str(REPOSITORY_ROOT / ".venv" / "bin" / "uv"),
    ]
    for candidate in uv_candidates:
        resolved = shutil.which(candidate)
        if resolved is not None:
            return resolved
    msg = "uv is required for wheel installation tests"
    raise RuntimeError(msg)


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


@pytest.mark.timeout(0)
def test_maturin_wheel_executes_correctly(tmp_path: pathlib.Path) -> None:
    """The native wheel can be installed and its extension imported at runtime."""
    if not toolchain_available():
        pytest.skip("Rust toolchain or maturin unavailable.")

    wheel_path = build_native_wheel_artifact(REPOSITORY_ROOT, tmp_path / "wheelhouse")
    install_dir = tmp_path / "install"
    install_dir.mkdir()

    # Install the wheel into an isolated directory so the import does not
    # collide with the editable install already present in the environment.
    uv_path = _resolve_uv()
    subprocess.run(  # noqa: S603 - arguments are trusted paths from this repo
        [
            uv_path,
            "pip",
            "install",
            "--target",
            str(install_dir),
            "--no-deps",
            str(wheel_path),
        ],
        check=True,
    )

    # Probe the extension through a subprocess so sys.path manipulation stays
    # self-contained and cannot accidentally import the editable install.
    import_script = (
        f"import sys; sys.path.insert(0, {str(install_dir)!r}); "
        "import stilyagi._stilyagi_rs; "
        "print(stilyagi._stilyagi_rs.hello()); "
        "print(stilyagi._stilyagi_rs.supported_syntaxes())"
    )
    probe = subprocess.run(  # noqa: S603 - sys.executable and the test-built script are trusted inputs.
        [sys.executable, "-c", import_script],
        capture_output=True,
        check=True,
        cwd=tmp_path,
        text=True,
    )
    lines = probe.stdout.strip().splitlines()
    assert len(lines) == 2, f"Expected 2 output lines, got {lines!r}"
    assert lines[0] == "hello from Rust", f"Unexpected hello output: {lines[0]!r}"
    assert "markdown" in lines[1], f"Unexpected supported_syntaxes output: {lines[1]!r}"


# ---------------------------------------------------------------------------
# Error-path tests for maturin helper functions
# ---------------------------------------------------------------------------


def test_read_maturin_pins_raises_when_pyproject_missing(
    tmp_path: pathlib.Path,
) -> None:
    """read_maturin_pins raises FileNotFoundError when pyproject.toml is absent."""
    with pytest.raises(FileNotFoundError, match=r"pyproject\.toml"):
        read_maturin_pins(tmp_path)


def test_read_maturin_pins_raises_when_dependency_groups_missing(
    tmp_path: pathlib.Path,
) -> None:
    """read_maturin_pins raises KeyError when [dependency-groups] is absent."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[build-system]\nrequires = ["maturin==1.13.3"]\n')
    with pytest.raises(KeyError, match=r"dependency-groups"):
        read_maturin_pins(tmp_path)


def test_read_maturin_pins_raises_when_build_system_missing(
    tmp_path: pathlib.Path,
) -> None:
    """read_maturin_pins raises KeyError when [build-system] is absent."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[dependency-groups]\ndev = ["maturin==1.13.3"]\n')
    with pytest.raises(KeyError, match=r"build-system"):
        read_maturin_pins(tmp_path)


@pytest.mark.parametrize(
    ("toml_content", "exc_type", "match"),
    [
        pytest.param(
            "[dependency-groups]\n"
            'dev = ["pytest==8.4.2"]\n'
            "[build-system]\n"
            'requires = ["setuptools"]\n',
            AssertionError,
            "Could not locate",
            id="no_maturin_pin",
        ),
        pytest.param(
            "[dependency-groups]\n"
            'dev = ["maturin==1.13.3"]\n'
            "[build-system]\n"
            'requires = "maturin==1.13.3"\n',
            TypeError,
            "Expected dependency list",
            id="requires_not_a_list",
        ),
    ],
)
def test_read_maturin_pins_raises(
    tmp_path: pathlib.Path,
    toml_content: str,
    exc_type: type[Exception],
    match: str,
) -> None:
    """read_maturin_pins raises the expected error for malformed pyproject.toml."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(toml_content)
    with pytest.raises(exc_type, match=match):
        read_maturin_pins(tmp_path)


def test_wheel_build_snapshot_raises_on_corrupted_zip(
    tmp_path: pathlib.Path,
) -> None:
    """wheel_build_snapshot raises BadZipFile when the wheel is not a valid zip."""
    corrupted = tmp_path / "not_a_wheel.whl"
    corrupted.write_text("not a zip archive")
    with pytest.raises(zipfile.BadZipFile):
        wheel_build_snapshot(corrupted)


def test_wheel_build_snapshot_raises_when_wheel_metadata_missing(
    tmp_path: pathlib.Path,
) -> None:
    """wheel_build_snapshot raises AssertionError when .dist-info/WHEEL absent."""
    empty_wheel = tmp_path / "empty.whl"
    with zipfile.ZipFile(empty_wheel, "w") as archive:
        archive.writestr("stilyagi/__init__.py", "")
    with pytest.raises(AssertionError, match=r"missing \.dist-info/WHEEL"):
        wheel_build_snapshot(empty_wheel)


def test_wheel_build_snapshot_raises_when_generator_missing(
    tmp_path: pathlib.Path,
) -> None:
    """wheel_build_snapshot raises AssertionError when Generator is absent."""
    malformed = tmp_path / "malformed.whl"
    with zipfile.ZipFile(malformed, "w") as archive:
        archive.writestr(
            "stilyagi-0.1.0.dist-info/WHEEL",
            "Wheel-Version: 1.0\nRoot-Is-Purelib: false\n",
        )
        archive.writestr(
            "stilyagi-0.1.0.dist-info/METADATA",
            "Name: stilyagi\n",
        )
    with pytest.raises(AssertionError, match="Could not parse maturin generator"):
        wheel_build_snapshot(malformed)
