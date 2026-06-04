"""Shared helpers for maturin build and compatibility tests."""

from __future__ import annotations

import importlib.metadata as im
import importlib.util
import re
import shutil
import subprocess  # noqa: S404 - tests invoke pinned maturin build commands.
import sys
import tomllib
import typing as typ
import zipfile

if typ.TYPE_CHECKING:
    import pathlib

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


def read_maturin_pins(root: pathlib.Path) -> dict[str, str]:
    """Read maturin version pins from the synchronized pyproject locations.

    Raises
    ------
    AssertionError
        If either maturin pin is missing.
    TypeError
        If the relevant TOML fields have an unexpected shape.
    FileNotFoundError
        If ``pyproject.toml`` is absent.
    OSError
        If ``pyproject.toml`` cannot be read.
    tomllib.TOMLDecodeError
        If ``pyproject.toml`` is invalid TOML.
    """
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
    """Read the maturin version pinned for development installs.

    Raises
    ------
    AssertionError
        If the development dependency pin is missing.
    TypeError
        If the relevant TOML fields have an unexpected shape.
    FileNotFoundError
        If ``pyproject.toml`` is absent.
    OSError
        If ``pyproject.toml`` cannot be read.
    tomllib.TOMLDecodeError
        If ``pyproject.toml`` is invalid TOML.
    """
    return read_maturin_pins(root)["[dependency-groups].dev"]


def installed_maturin_version() -> str | None:
    """Return the installed maturin module version when it is importable."""
    if not _maturin_module_available():
        return None
    return im.version("maturin")


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
    """Build a native wheel with the pinned maturin version.

    Raises
    ------
    AssertionError
        If the build does not produce exactly one wheel.
    OSError
        If the output directory cannot be created or inspected.
    subprocess.CalledProcessError
        If the maturin build command exits non-zero.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
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
    """Return a normalized snapshot of wheel metadata and layout.

    Raises
    ------
    AssertionError
        If the wheel metadata is missing expected maturin fields.
    OSError
        If the wheel file cannot be opened or read.
    zipfile.BadZipFile
        If the wheel file is not a valid zip archive.
    """
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
    """Return a TOML object mapping or raise a focused assertion."""
    if not isinstance(value, dict):
        msg = f"Expected TOML table, found {type(value).__name__}"
        raise TypeError(msg)
    return typ.cast("dict[str, object]", value)


def _require_maturin_pin(dependencies: object, location: str) -> str:
    """Extract a maturin pin from dependency strings."""
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
    """Return whether the maturin module can be resolved."""
    try:
        return importlib.util.find_spec("maturin") is not None
    except ImportError:
        return False


def _header_value(headers: dict[str, list[str]], key: str) -> str | None:
    """Return the first header value for the given key, or None if absent."""
    values = headers.get(key)
    if not values:
        return None
    return values[0]


def _parse_metadata(raw_metadata: str) -> dict[str, object]:
    """Parse RFC 2822-style metadata headers into a normalized dict."""
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
    """Normalize platform/version wheel entry names to stable placeholders."""
    if _EXTENSION_MODULE_RE.match(name):
        return "stilyagi/_stilyagi_rs.cpython-<platform>.<ext>"
    if "/sboms/" in name:
        return "stilyagi-<version>.dist-info/sboms/<sbom>.cyclonedx.json"
    for suffix, normalized in _DIST_INFO_SUFFIXES.items():
        if name.endswith(suffix):
            return normalized
    return name


def _locate_dist_info_wheel(entry_names: list[str]) -> str:
    """Return the .dist-info/WHEEL entry name from a wheel archive's namelist.

    Parameters
    ----------
    entry_names:
        All entry names returned by ``zipfile.ZipFile.namelist()``.

    Raises
    ------
    AssertionError
        If no ``.dist-info/WHEEL`` entry is present.
    """
    wheel_name = next(
        (name for name in entry_names if name.endswith(".dist-info/WHEEL")),
        None,
    )
    if wheel_name is None:
        msg = "wheel is missing .dist-info/WHEEL metadata"
        raise AssertionError(msg)
    return wheel_name


def _parse_wheel_header(wheel_payload: str, whl_path: pathlib.Path) -> tuple[str, str]:
    """Extract the maturin generator string and Root-Is-Purelib value.

    Parameters
    ----------
    wheel_payload:
        Decoded text content of the ``.dist-info/WHEEL`` file.
    whl_path:
        Path to the wheel archive; used only in error messages.

    Returns
    -------
    tuple[str, str]
        ``(generator, root_is_purelib)`` extracted from the WHEEL headers.

    Raises
    ------
    AssertionError
        If either field cannot be parsed.
    """
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
