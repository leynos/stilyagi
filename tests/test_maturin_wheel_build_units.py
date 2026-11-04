"""Hold the wheel build and its availability probes to their branches.

``tests/test_maturin_build.py`` builds a wheel when maturin is installed and
skips when it is not, which leaves the skip path and the build's refusal of a
stale out directory to whichever host runs the suite. This module takes both
in hand: `subprocess.run` is replaced with a stand-in that writes a known
wheel, and the availability probes are pointed at a module table that answers
the way a missing or broken installation does.

The reading helpers these tests share with their sibling live in
``tests/test_maturin_wheel_units.py``; this module only imports the build
surface, so the two stay under the file-size ceiling independently.
"""

import importlib.util
import subprocess  # ruff: ignore[suspicious-subprocess-import] - the stand-in replaces the pinned maturin command.
import typing as typ

import pytest

if typ.TYPE_CHECKING:
    import pathlib

from tests.test_maturin_build import (
    _build_native_wheel_artefact,
    _installed_maturin_version,
    _maturin_module_available,
    _release_build_env,
    _resolve_uv,
)


def test_the_release_build_names_rustflags_even_when_the_source_lacks_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty assignment is what keeps `.cargo/config.toml` out of the wheel."""
    monkeypatch.delenv("RUSTFLAGS", raising=False)

    env = _release_build_env()

    assert "RUSTFLAGS" in env, "the flag was not named at all"
    assert not env["RUSTFLAGS"], env["RUSTFLAGS"]


def test_the_release_build_keeps_an_ambient_rustflags_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CI's own `-D warnings` is passed through rather than replaced."""
    monkeypatch.setenv("RUSTFLAGS", "-D warnings")

    assert _release_build_env()["RUSTFLAGS"] == "-D warnings", _release_build_env()


def test_the_build_returns_the_one_wheel_it_wrote(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    """A stale wheel is removed, and the remaining one is the answer."""
    out_dir = tmp_path / "wheelhouse"
    out_dir.mkdir()
    (out_dir / "stale-0.1.0-py3-none-any.whl").write_bytes(b"stale")
    seen: dict[str, typ.Any] = {}

    def build(command: list[str], **kwargs: typ.Any) -> None:  # ruff: ignore[any-type] - mirrors subprocess.run's keyword surface.
        """Write one wheel, as maturin would, and record the call."""
        seen["command"] = command
        seen.update(kwargs)
        (out_dir / "stilyagi-0.2.0-cp314-cp314-x86_64.whl").write_bytes(b"wheel")

    monkeypatch.setattr(subprocess, "run", build)

    built = _build_native_wheel_artefact(tmp_path, out_dir)

    assert built.name == "stilyagi-0.2.0-cp314-cp314-x86_64.whl", built.name
    assert seen["timeout"] == 600, seen["timeout"]
    assert str(out_dir) in seen["command"], seen["command"]


def test_a_build_that_writes_two_wheels_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    """More than one wheel means the out directory was not cleaned."""
    out_dir = tmp_path / "wheelhouse"

    def build(_command: list[str], **_kwargs: typ.Any) -> None:  # ruff: ignore[any-type] - mirrors subprocess.run's keyword surface.
        """Write two wheels, which the helper must refuse."""
        out_dir.mkdir(parents=True, exist_ok=True)
        for name in ("a-0.1.0-py3-none-any.whl", "b-0.1.0-py3-none-any.whl"):
            (out_dir / name).write_bytes(b"")

    monkeypatch.setattr(subprocess, "run", build)

    with pytest.raises(AssertionError, match="Expected exactly one wheel"):
        _build_native_wheel_artefact(tmp_path, out_dir)


def test_the_installed_maturin_version_is_absent_without_the_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without the module there is no version to report."""
    monkeypatch.setattr(
        "tests.test_maturin_build._maturin_module_available", lambda: False
    )

    assert _installed_maturin_version() is None


def test_a_package_lookup_that_finds_nothing_is_an_absence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An uninstalled maturin is a skip condition, not a collection error."""
    from importlib import metadata

    def absent(_name: str) -> str:
        """Refuse the lookup as metadata does for an unknown distribution."""
        raise metadata.PackageNotFoundError(name="maturin")

    monkeypatch.setattr(
        "tests.test_maturin_build._maturin_module_available", lambda: True
    )
    monkeypatch.setattr("tests.test_maturin_build.im.version", absent)

    assert _installed_maturin_version() is None


def test_a_module_lookup_that_raises_is_answered_with_no(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A broken installation is an absence, not a crash during collection."""

    def broken(_name: str) -> None:
        """Raise as a shadowing module would."""
        raise ImportError(_name)

    monkeypatch.setattr(importlib.util, "find_spec", broken)

    assert _maturin_module_available() is False


def test_uv_is_resolved_from_the_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    """The first candidate the shell can find is the one used."""
    monkeypatch.setattr(
        "tests.test_maturin_build.shutil.which",
        lambda candidate: "/usr/bin/uv" if candidate == "uv" else None,
    )

    assert _resolve_uv(tmp_path) == "/usr/bin/uv"


def test_a_host_without_uv_resolves_to_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    """Absence is reported so the caller can skip rather than fail."""
    monkeypatch.setattr("tests.test_maturin_build.shutil.which", lambda _name: None)

    assert _resolve_uv(tmp_path) is None, "a host without uv must resolve to nothing"
