"""Unit tests for maturin pin synchronization and wheel build output."""

import importlib.metadata as im
import importlib.util
import pathlib
import re
import shutil
import subprocess  # noqa: S404 - tests invoke pinned, trusted subprocess commands.
import sys
import tomllib
import typing as typ
import zipfile

import pytest

if typ.TYPE_CHECKING:
    from syrupy.assertion import SnapshotAssertion

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[1]
_MATURIN_PIN_RE = re.compile(r"^maturin==(\d+\.\d+\.\d+)$")
_GENERATOR_RE = re.compile(r"^Generator:\s*maturin\s*\(([^)]+)\)\s*$", re.MULTILINE)
_EXTENSION_MODULE_RE = re.compile(
    r"^stilyagi/_stilyagi_rs\.cpython-[^/]+\.(?:so|pyd)$",
)
_DIST_INFO_SUFFIXES: dict[str, str] = {
    ".dist-info/RECORD": "stilyagi-<version>.dist-info/RECORD",
    ".dist-info/METADATA": "stilyagi-<version>.dist-info/METADATA",
    ".dist-info/WHEEL": "stilyagi-<version>.dist-info/WHEEL",
    ".dist-info/licenses/LICENSE": "stilyagi-<version>.dist-info/licenses/LICENSE",
}


def _resolve_uv(root: pathlib.Path) -> str:
    uv_candidates = [
        "uv",
        str(root / ".uv-tools" / "uv"),
        str(root / ".venv" / "bin" / "uv"),
    ]
    for candidate in uv_candidates:
        resolved = shutil.which(candidate)
        if resolved is not None:
            return resolved
    msg = "uv is required for wheel installation tests"
    raise RuntimeError(msg)


def read_maturin_pins(root: pathlib.Path) -> dict[str, str]:
    """Read maturin version pins from the synchronized pyproject locations."""
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    dependency_groups = _object_mapping(pyproject["dependency-groups"])
    build_system = _object_mapping(pyproject["build-system"])

    return {
        "[dependency-groups].dev": _require_maturin_pin(
            dependency_groups["dev"],
            "[dependency-groups].dev",
        ),
        "[build-system].requires": _require_maturin_pin(
            build_system["requires"],
            "[build-system].requires",
        ),
    }


def read_expected_maturin_version(root: pathlib.Path) -> str:
    """Read the maturin version pinned for development installs."""
    return read_maturin_pins(root)["[dependency-groups].dev"]


def installed_maturin_version() -> str | None:
    """Return the installed maturin module version when it is importable."""
    if not _maturin_module_available():
        return None
    try:
        return im.version("maturin")
    except im.PackageNotFoundError:
        return None


def toolchain_available() -> bool:
    """Return whether Rust and maturin are available for native wheel builds."""
    return (
        shutil.which("cargo") is not None
        and shutil.which("rustc") is not None
        and _maturin_module_available()
    )


def build_native_wheel_artifact(
    root: pathlib.Path, out_dir: pathlib.Path
) -> pathlib.Path:
    """Build a native wheel with the pinned maturin version."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale_wheel in out_dir.glob("*.whl"):
        stale_wheel.unlink()
    command = [
        sys.executable,
        "-m",
        "maturin",
        "build",
        "--release",
        "--interpreter",
        sys.executable,
        "--out",
        str(out_dir),
        "--manifest-path",
        str(root / "crates" / "stilyagi-pyext" / "Cargo.toml"),
    ]
    subprocess.run(  # noqa: S603 - command list uses trusted paths and pinned maturin
        command,
        check=True,
        cwd=root,
    )
    wheels = sorted(out_dir.glob("*.whl"))
    if len(wheels) != 1:
        msg = f"Expected exactly one wheel in {out_dir}, found {wheels!r}"
        raise AssertionError(msg)
    return wheels[0]


def wheel_build_snapshot(whl_path: pathlib.Path) -> dict[str, object]:
    """Return a normalized snapshot of wheel metadata and layout."""
    with zipfile.ZipFile(whl_path) as archive:
        entry_names = archive.namelist()
        wheel_name = _locate_dist_info_wheel(entry_names)
        metadata_name = wheel_name.replace("/WHEEL", "/METADATA")
        wheel_payload = archive.read(wheel_name).decode("utf-8")
        metadata_payload = archive.read(metadata_name).decode("utf-8")
    generator, root_is_purelib = _parse_wheel_header(wheel_payload, whl_path)
    return {
        "generator": generator,
        "metadata": _parse_metadata(metadata_payload),
        "wheel": {
            "root_is_purelib": root_is_purelib,
            "tag": "<platform-tag>",
        },
        "entries": sorted(_normalize_wheel_entry(name) for name in entry_names),
    }


def _object_mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        msg = f"Expected TOML table, found {type(value).__name__}"
        raise TypeError(msg)
    return typ.cast("dict[str, object]", value)


def _require_maturin_pin(dependencies: object, location: str) -> str:
    if not isinstance(dependencies, list):
        msg = f"Expected dependency list at {location}"
        raise TypeError(msg)
    for dependency in dependencies:
        if not isinstance(dependency, str):
            continue
        match = _MATURIN_PIN_RE.match(dependency)
        if match is not None:
            return match.group(1)
    msg = f"Could not locate exact maturin dependency pin in {location}"
    raise AssertionError(msg)


def _maturin_module_available() -> bool:
    try:
        return importlib.util.find_spec("maturin") is not None
    except ImportError:
        return False


def _header_value(headers: dict[str, list[str]], key: str) -> str | None:
    values = headers.get(key)
    if not values:
        return None
    return values[0]


def _parse_metadata(raw_metadata: str) -> dict[str, object]:
    headers: dict[str, list[str]] = {}
    current_key: str | None = None
    for line in raw_metadata.splitlines():
        if line.startswith((" ", "\t")) and current_key is not None:
            headers[current_key][-1] = f"{headers[current_key][-1]} {line.strip()}"
            continue
        if ":" not in line:
            break
        key, value = line.split(":", 1)
        current_key = key.strip()
        headers.setdefault(current_key, []).append(value.strip())

    return {
        "name": _header_value(headers, "Name"),
        "version": _header_value(headers, "Version"),
        "requires_python": _header_value(headers, "Requires-Python"),
        "requires_dist": sorted(headers.get("Requires-Dist", [])),
        "classifiers": sorted(headers.get("Classifier", [])),
    }


def _normalize_wheel_entry(name: str) -> str:
    if _EXTENSION_MODULE_RE.match(name):
        return "stilyagi/_stilyagi_rs.cpython-<platform>.<ext>"
    if "/sboms/" in name:
        return "stilyagi-<version>.dist-info/sboms/<sbom>.cyclonedx.json"
    for suffix, normalized in _DIST_INFO_SUFFIXES.items():
        if name.endswith(suffix):
            return normalized
    return name


def _locate_dist_info_wheel(entry_names: list[str]) -> str:
    wheel_name = next(
        (name for name in entry_names if name.endswith(".dist-info/WHEEL")),
        None,
    )
    if wheel_name is None:
        msg = "wheel is missing .dist-info/WHEEL metadata"
        raise AssertionError(msg)
    return wheel_name


def _parse_wheel_header(wheel_payload: str, whl_path: pathlib.Path) -> tuple[str, str]:
    generator_match = _GENERATOR_RE.search(wheel_payload)
    if generator_match is None:
        msg = f"Could not parse maturin generator from WHEEL metadata: {whl_path}"
        raise AssertionError(msg)
    root_is_purelib = next(
        (
            line.removeprefix("Root-Is-Purelib: ")
            for line in wheel_payload.splitlines()
            if line.startswith("Root-Is-Purelib:")
        ),
        None,
    )
    if root_is_purelib is None:
        msg = "wheel is missing Root-Is-Purelib metadata"
        raise AssertionError(msg)
    return generator_match.group(1), root_is_purelib


@pytest.fixture(scope="module")
def built_wheel(tmp_path_factory: pytest.TempPathFactory) -> pathlib.Path:
    """Build the native maturin wheel once for module-level compatibility tests."""
    if not toolchain_available():
        pytest.skip("Rust toolchain or maturin unavailable.")
    wheelhouse = tmp_path_factory.mktemp("wheelhouse")
    return build_native_wheel_artifact(REPOSITORY_ROOT, wheelhouse)


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


@pytest.mark.timeout(0)
def test_maturin_wheel_build_snapshot(
    built_wheel: pathlib.Path,
    snapshot: SnapshotAssertion,
) -> None:
    """Native wheel metadata and layout match the expected maturin output."""
    expected = read_expected_maturin_version(REPOSITORY_ROOT)
    snapshot_payload = wheel_build_snapshot(built_wheel)
    assert snapshot_payload["generator"] == expected, (
        f"Expected generator {expected!r}, found {snapshot_payload['generator']!r}"
    )
    assert snapshot_payload == snapshot, (
        "Built wheel metadata, file list, and build settings changed."
    )


@pytest.mark.timeout(0)
def test_maturin_wheel_executes_correctly(
    tmp_path: pathlib.Path,
    built_wheel: pathlib.Path,
) -> None:
    """The native wheel can be installed and its extension imported at runtime."""
    install_dir = tmp_path / "install"
    install_dir.mkdir()

    uv_path = _resolve_uv(REPOSITORY_ROOT)
    subprocess.run(  # noqa: S603 - arguments are trusted paths from this repo
        [
            uv_path,
            "pip",
            "install",
            "--target",
            str(install_dir),
            "--no-deps",
            str(built_wheel),
        ],
        check=True,
    )

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
        read_maturin_pins(tmp_path)


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
    ],
    ids=["corrupted_zip", "missing_wheel_file", "missing_generator"],
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
        wheel_build_snapshot(wheel_path)
