"""The source distribution is the release's third artefact, and it must be whole.

The release publishes one sdist beside the native wheels, and both PyPI and the
GitHub Release receive the same bytes. Before this module, nothing in the suite
looked at the sdist at all: ``build-wheels.yml`` built a wheel, the snapshot
test read its metadata, and a packaging change that dropped the Python package,
the Rust crates, or the ``pyproject.toml`` from the sdist would have reached a
tag before anyone noticed.

Building an sdist needs the Rust toolchain and the pinned maturin, so these
tests reuse the availability skips of ``tests/test_maturin_build.py`` rather
than restating them. The build is module-scoped: one ``maturin sdist`` is
enough for every assertion here, and it is slow.
"""

import shutil
import subprocess  # ruff: ignore[suspicious-subprocess-import] - builds with the pinned maturin.
import sys
import tarfile
import tomllib
import typing as typ

import pytest

from tests.support.workflow_files import read_text
from tests.test_maturin_build import (
    REPOSITORY_ROOT,
    _installed_maturin_version,
    _maturin_module_available,
    _read_expected_maturin_version,
)

if typ.TYPE_CHECKING:
    import pathlib

_PYEXT_MANIFEST: typ.Final = (
    REPOSITORY_ROOT / "crates" / "stilyagi-pyext" / "Cargo.toml"
)
_SUBPROCESS_TIMEOUT_SECONDS: typ.Final = 600
#: What the sdist must contain beyond the Python package, relative to its
#: ``stilyagi-<version>/`` root. Both build inputs and the files a wheel build
#: from the sdist reads are named, because a missing ``Cargo.lock`` or
#: ``pyproject.toml`` fails at the consumer rather than here.
_REQUIRED_MEMBERS: typ.Final = frozenset({
    "Cargo.toml",
    "Cargo.lock",
    "pyproject.toml",
    "README.md",
    "LICENSE",
    "crates/stilyagi-pyext/Cargo.toml",
    "crates/stilyagi-core/Cargo.toml",
    "crates/stilyagi-extract/Cargo.toml",
    "crates/stilyagi-ir/Cargo.toml",
})


def _sdist_toolchain_available() -> bool:
    """Return whether the sdist build's prerequisites are available."""
    return bool(
        shutil.which("cargo") and shutil.which("rustc") and _maturin_module_available()
    )


def _build_sdist(out_dir: pathlib.Path) -> pathlib.Path:
    """Build the sdist with the pinned maturin and return the archive path.

    Parameters
    ----------
    out_dir : pathlib.Path
        The directory that receives the archive.

    Returns
    -------
    pathlib.Path
        The single ``.tar.gz`` the build produced.

    Raises
    ------
    AssertionError
        When the build writes anything other than exactly one archive.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] - trusted paths and the pinned maturin.
        [
            sys.executable,
            "-m",
            "maturin",
            "sdist",
            "--manifest-path",
            str(_PYEXT_MANIFEST),
            "--out",
            str(out_dir),
        ],
        check=True,
        cwd=REPOSITORY_ROOT,
        timeout=_SUBPROCESS_TIMEOUT_SECONDS,
    )
    archives = sorted(out_dir.glob("*.tar.gz"))
    if len(archives) != 1:
        msg = f"Expected exactly one sdist in {out_dir}, found {archives!r}"
        raise AssertionError(msg)
    return archives[0]


def _members(archive: pathlib.Path) -> set[str]:
    """Return the members of one built sdist relative to its release prefix.

    Parameters
    ----------
    archive : pathlib.Path
        The ``.tar.gz`` maturin wrote.

    Returns
    -------
    set[str]
        Member names with the ``stilyagi-<version>/`` directory removed, so
        the assertions name files rather than repeating the version.

    Examples
    --------
    >>> sorted(_members(archive))[:1]  # doctest: +SKIP
    ['Cargo.lock']
    """
    with tarfile.open(archive, "r:gz") as bundle:
        names = bundle.getnames()
    return {name.split("/", maxsplit=1)[1] for name in names if "/" in name}


def declared_version(root: pathlib.Path) -> str:
    """Return ``[project].version`` from the repository's ``pyproject.toml``."""
    pyproject = root / "pyproject.toml"
    document = tomllib.loads(read_text(pyproject, reader="declared_version"))
    version = typ.cast("dict[str, object]", document["project"])["version"]
    return typ.cast("str", version)


@pytest.fixture(scope="module")
def built_sdist(tmp_path_factory: pytest.TempPathFactory) -> pathlib.Path:
    """Build the sdist once for the module's contract tests."""
    if not _sdist_toolchain_available():
        pytest.skip("Rust toolchain or maturin unavailable.")
    expected_maturin = _read_expected_maturin_version(REPOSITORY_ROOT)
    if (installed_maturin := _installed_maturin_version()) != expected_maturin:
        pytest.skip(f"maturin pin {expected_maturin} != active {installed_maturin!r}.")
    return _build_sdist(tmp_path_factory.mktemp("sdist"))


@pytest.mark.slow
@pytest.mark.timeout(_SUBPROCESS_TIMEOUT_SECONDS + 60)
def test_the_sdist_holds_the_python_package(built_sdist: pathlib.Path) -> None:
    """The sdist carries every module of the Python package it distributes."""
    python_source = REPOSITORY_ROOT / "python" / "stilyagi"
    expected = {
        "python/stilyagi/" + path.relative_to(python_source).as_posix()
        for path in python_source.rglob("*.py")
    }
    missing = sorted(expected - _members(built_sdist))
    assert not missing, f"the sdist omits {missing}"


@pytest.mark.slow
@pytest.mark.timeout(_SUBPROCESS_TIMEOUT_SECONDS + 60)
def test_the_sdist_holds_every_build_input(built_sdist: pathlib.Path) -> None:
    """The sdist carries the crate manifests and files a rebuild reads."""
    missing = sorted(_REQUIRED_MEMBERS - _members(built_sdist))
    assert not missing, f"the sdist omits {missing}"


@pytest.mark.slow
@pytest.mark.timeout(_SUBPROCESS_TIMEOUT_SECONDS + 60)
def test_the_sdist_is_named_for_the_declared_version(
    built_sdist: pathlib.Path,
) -> None:
    """The archive is named ``stilyagi-<version>.tar.gz``, under one root."""
    version = declared_version(REPOSITORY_ROOT)
    assert built_sdist.name == f"stilyagi-{version}.tar.gz", (
        f"expected stilyagi-{version}.tar.gz, found {built_sdist.name}"
    )
    with tarfile.open(built_sdist, "r:gz") as bundle:
        names = bundle.getnames()
    prefix = f"stilyagi-{version}/"
    assert all(name.startswith(prefix) for name in names), (
        f"every member must sit under {prefix}"
    )
