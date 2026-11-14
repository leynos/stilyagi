"""Hold the sdist helpers to the archive they read and the build they refuse.

``tests/test_maturin_sdist.py`` builds one sdist and asserts the repository's
own files are inside it. Those assertions are worth having, but they only ever
see the archive maturin built on this tree: the reader that strips the
``stilyagi-<version>/`` prefix, the declared-version lookup, and the refusal of
a build that writes more than one archive never execute, so a helper that
returned an unprefixed name or a build that left a stale archive would pass the
contract unnoticed.

This module exercises those helpers in process. The archive is a real
``tar.gz`` written here, and the build is driven by a `subprocess.run`
stand-in; nothing here needs a Rust toolchain, which is what lets the contract
module keep its availability skips while this one always runs.
"""

import io
import pathlib
import subprocess  # ruff: ignore[suspicious-subprocess-import] - the stand-in replaces the pinned maturin command.
import tarfile
import typing as typ

import pytest

from tests.test_maturin_sdist import (
    _build_sdist,
    _members,
    declared_version,
)

if typ.TYPE_CHECKING:
    import collections.abc as cabc

#: The repository root that `declared_version` is pointed at, named here rather
#: than imported so the reader sees which tree is measured.
_REPOSITORY_ROOT: typ.Final = pathlib.Path(__file__).resolve().parents[1]


def _write_sdist(
    path: pathlib.Path,
    members: cabc.Iterable[str],
    *,
    root: str = "stilyagi-0.2.0",
    writes_root_entry: bool = False,
) -> pathlib.Path:
    """Write a ``.tar.gz`` at `path` holding `members` under `root`.

    Returns
    -------
    pathlib.Path
        The archive's path, so a caller can chain the call into ``_members``.
    """
    # ``writes_root_entry`` adds the archive's own directory entry, whose name
    # carries no separator once ``root`` is stripped. A real sdist carries it,
    # and it is the entry the ``"/" in name`` filter must drop.
    with tarfile.open(path, "w:gz") as bundle:
        if writes_root_entry:
            bundle.addfile(tarfile.TarInfo(root))
        for member in members:
            payload = b""
            info = tarfile.TarInfo(f"{root}/{member}")
            info.size = len(payload)
            bundle.addfile(info, io.BytesIO(payload))
    return path


# -- _members ----------------------------------------------------------------


def test_the_release_prefix_is_stripped_from_every_member(
    tmp_path: pathlib.Path,
) -> None:
    """The assertion names ``Cargo.lock``, not ``stilyagi-0.2.0/Cargo.lock``."""
    archive = _write_sdist(
        tmp_path / "stilyagi-0.2.0.tar.gz",
        ["Cargo.toml", "Cargo.lock", "python/stilyagi/__init__.py"],
    )

    members = _members(archive)

    assert members == {
        "Cargo.toml",
        "Cargo.lock",
        "python/stilyagi/__init__.py",
    }, members


def test_a_member_at_the_archive_root_is_dropped(tmp_path: pathlib.Path) -> None:
    """A name with no separator is the prefix itself, not a member of it."""
    archive = _write_sdist(
        tmp_path / "stilyagi-0.2.0.tar.gz",
        ["Cargo.toml"],
        root="stilyagi-0.2.0",
        writes_root_entry=True,
    )

    members = _members(archive)

    assert "Cargo.toml" in members, members
    assert "stilyagi-0.2.0" not in members, members


def test_only_the_first_separator_is_removed(tmp_path: pathlib.Path) -> None:
    """A nested member keeps its own directory structure below the prefix."""
    archive = _write_sdist(
        tmp_path / "stilyagi-0.2.0.tar.gz", ["crates/stilyagi-ir/Cargo.toml"]
    )

    members = _members(archive)

    assert members == {"crates/stilyagi-ir/Cargo.toml"}, members


# -- declared_version --------------------------------------------------------


def test_the_version_is_read_from_the_project_table(tmp_path: pathlib.Path) -> None:
    """The lookup answers ``[project].version`` and nothing else."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "stilyagi"\nversion = "9.8.7"\n', encoding="utf-8"
    )

    version = declared_version(tmp_path)

    assert version == "9.8.7", version


def test_the_repository_declares_the_version_its_manifest_names() -> None:
    """The tree under test reports a PEP 440 version, not an empty string."""
    version = declared_version(_REPOSITORY_ROOT)

    assert version, "the manifest declares no version"
    assert version[0].isdigit(), version


# -- _build_sdist ------------------------------------------------------------


def test_the_build_returns_the_one_archive_it_wrote(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    """The build is run for the pyext manifest into the requested directory."""
    out_dir = tmp_path / "sdist"
    seen: dict[str, typ.Any] = {}

    def build(command: list[str], **kwargs: typ.Any) -> None:  # ruff: ignore[any-type] - mirrors subprocess.run's keyword surface.
        """Write one archive, as maturin would, and record the call."""
        seen["command"] = command
        seen.update(kwargs)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "stilyagi-0.2.0.tar.gz").write_bytes(b"archive")

    monkeypatch.setattr(subprocess, "run", build)

    built = _build_sdist(out_dir)

    assert built.name == "stilyagi-0.2.0.tar.gz", built.name
    assert seen["timeout"] == 600, seen["timeout"]
    assert str(out_dir) in seen["command"], seen["command"]
    assert "sdist" in seen["command"], seen["command"]
    assert str(out_dir) not in str(seen["cwd"]), "the build ran outside the repository"


def test_a_build_that_writes_two_archives_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    """A leftover archive means the sdist under test is not the one just built."""
    out_dir = tmp_path / "sdist"

    def build(_command: list[str], **_kwargs: typ.Any) -> None:  # ruff: ignore[any-type] - mirrors subprocess.run's keyword surface.
        """Write two archives, which the helper must refuse."""
        out_dir.mkdir(parents=True, exist_ok=True)
        for name in ("stilyagi-0.1.9.tar.gz", "stilyagi-0.2.0.tar.gz"):
            (out_dir / name).write_bytes(b"")

    monkeypatch.setattr(subprocess, "run", build)

    with pytest.raises(AssertionError, match="Expected exactly one sdist"):
        _build_sdist(out_dir)
