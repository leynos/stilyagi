"""The Python and Rust distributions state one version, as one exact string.

``release.yml``'s ``check-version`` job compares ``pyproject.toml``'s
``[project].version`` with the tag, and the wheels and the sdist take their
version from Cargo's ``[workspace.package].version``. If the two disagree, a
tag that passes the check publishes artefacts whose metadata names a different
version, and PyPI refuses the upload only after the build has been paid for.

The comparison is deliberately an exact string comparison rather than a parsed
one: ``0.2.0`` and ``0.2.0+build.1`` are equal as versions and different as
release identifiers, and the release process needs the identical spelling on
both sides. The reading is exercised over a synthetic mismatched project as
well as this repository, so a checker that raised on nothing, or that compared
a value with itself, cannot pass.
"""

import tomllib
import typing as typ
from pathlib import Path

import pytest

from tests.support.workflow_files import read_text

REPOSITORY_ROOT: typ.Final = Path(__file__).resolve().parents[1]
PYPROJECT: typ.Final = REPOSITORY_ROOT / "pyproject.toml"
WORKSPACE_MANIFEST: typ.Final = REPOSITORY_ROOT / "Cargo.toml"
PYEXT_MANIFEST: typ.Final = REPOSITORY_ROOT / "crates" / "stilyagi-pyext" / "Cargo.toml"
#: Every crate whose manifest is read here inherits ``version.workspace``.
INHERITING_MANIFESTS: typ.Final = (
    PYEXT_MANIFEST,
    REPOSITORY_ROOT / "crates" / "stilyagi-ir" / "Cargo.toml",
    REPOSITORY_ROOT / "crates" / "stilyagi-markdown" / "Cargo.toml",
)


def _table(
    document: dict[str, object], path: tuple[str, ...], *, source: str
) -> dict[str, object]:
    """Return one nested TOML table, naming it when it is absent."""
    value: object = document
    for key in path:
        value = value.get(key) if isinstance(value, dict) else None
    if not isinstance(value, dict):
        msg = f"{source} has no [{'.'.join(path)}] table"
        raise TypeError(msg)
    return typ.cast("dict[str, object]", value)


def _string(table: dict[str, object], key: str, *, source: str) -> str:
    """Return one string from a TOML table, naming it when it is absent."""
    value = table.get(key)
    if not isinstance(value, str):
        msg = f"{source} sets no string {key!r}"
        raise TypeError(msg)
    return value


def _parse(path: Path) -> dict[str, object]:
    """Parse one TOML document, naming the file when it is unreadable."""
    return tomllib.loads(read_text(path, reader="_parse"))


def declared_versions(pyproject_text: str, workspace_text: str) -> tuple[str, str]:
    r"""Return the Python and Rust versions declared by two manifests' text.

    Parameters
    ----------
    pyproject_text : str
        The text of a ``pyproject.toml`` holding ``[project]``.
    workspace_text : str
        The text of a ``Cargo.toml`` holding ``[workspace.package]``.

    Returns
    -------
    tuple[str, str]
        ``[project].version`` and ``[workspace.package].version``, unparsed.

    Examples
    --------
    >>> declared_versions(
    ...     '[project]\\nversion = "1.0.0"\\n',
    ...     '[workspace.package]\\nversion = "1.0.0"\\n',
    ... )
    ('1.0.0', '1.0.0')
    """
    pyproject = _parse_text(pyproject_text, "[project]")
    workspace = _parse_text(workspace_text, "[workspace.package]")
    python_version = _string(
        _table(pyproject, ("project",), source="pyproject.toml"),
        "version",
        source="[project]",
    )
    rust_version = _string(
        _table(workspace, ("workspace", "package"), source="Cargo.toml"),
        "version",
        source="[workspace.package]",
    )
    return python_version, rust_version


def _parse_text(text: str, table: str) -> dict[str, object]:
    """Parse TOML text, naming the table a caller was looking for."""
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        msg = f"text holding {table} does not parse: {error}"
        raise AssertionError(msg) from error


def version_faults(pyproject_text: str, workspace_text: str) -> list[str]:
    r"""Describe every way two manifests' declared versions disagree.

    Parameters
    ----------
    pyproject_text : str
        The text of a ``pyproject.toml`` holding ``[project]``.
    workspace_text : str
        The text of a ``Cargo.toml`` holding ``[workspace.package]``.

    Returns
    -------
    list[str]
        One message when the versions differ, or when either is missing;
        empty when they are the same exact string.

    Examples
    --------
    >>> version_faults('[project]\\nversion = "1.0.0"\\n', '[workspace.package]\\n')
    ['[workspace.package] sets no string \\'version\\'']
    """
    python_version, rust_version = declared_versions(pyproject_text, workspace_text)
    if python_version == rust_version:
        return []
    return [
        (
            f"[project].version {python_version!r} does not equal "
            f"[workspace.package].version {rust_version!r}"
        )
    ]


def test_the_declared_versions_are_identical() -> None:
    """The Python and the Rust distribution state the same exact version."""
    faults = version_faults(
        read_text(PYPROJECT, reader="test_the_declared_versions_are_identical"),
        read_text(
            WORKSPACE_MANIFEST, reader="test_the_declared_versions_are_identical"
        ),
    )
    assert not faults, "; ".join(faults)


@pytest.mark.parametrize(
    ("python_version", "rust_version"),
    [
        ("0.2.0", "0.2.1"),
        ("0.2.0", "0.2.0+build.1"),
        ("0.2.0", "0.2.0 "),
    ],
    ids=["different-patch", "local-label", "trailing-space"],
)
def test_a_differing_version_is_reported(
    python_version: str, rust_version: str
) -> None:
    """A version that is not the same exact string is a fault.

    Equality as versions is not enough: the release process publishes under
    the declared string, so a spelling that PyPI would normalize differently
    must be caught before anything is built.
    """
    faults = version_faults(
        f'[project]\nversion = "{python_version}"\n',
        f'[workspace.package]\nversion = "{rust_version}"\n',
    )
    assert faults, f"{python_version!r} vs {rust_version!r} should be a fault"


def test_matching_versions_are_accepted() -> None:
    """The checker accepts a synthetic pair that agrees, so it is not vacuous."""
    faults = version_faults(
        '[project]\nversion = "9.9.9"\n',
        '[workspace.package]\nversion = "9.9.9"\n',
    )
    assert not faults, f"identical synthetic versions reported {faults}"


@pytest.mark.parametrize("manifest", INHERITING_MANIFESTS, ids=lambda p: p.parent.name)
def test_crates_inherit_the_workspace_version(manifest: Path) -> None:
    """Every crate whose wheel or metadata is published inherits one version."""
    package = _table(_parse(manifest), ("package",), source=str(manifest))
    inherited = package.get("version")
    assert inherited == {"workspace": True}, (
        f"{manifest} must inherit the workspace version, found {inherited!r}"
    )


@pytest.mark.parametrize(
    "manifest", INHERITING_MANIFESTS[1:], ids=lambda p: p.parent.name
)
def test_the_test_fixtures_requirement_matches_the_workspace_version(
    manifest: Path,
) -> None:
    """A path requirement carrying a stale version is a publish-time surprise.

    `stilyagi-test-fixtures` is required with both a `path` and a `version`, so
    the literal is checked against the workspace rather than left to Cargo,
    which resolves the path locally and would never notice the drift until a
    release tried to resolve the version from a registry.
    """
    workspace = _table(
        _parse(WORKSPACE_MANIFEST), ("workspace", "package"), source="Cargo.toml"
    )
    expected = _string(workspace, "version", source="[workspace.package]")
    dependencies = _table(_parse(manifest), ("dev-dependencies",), source=str(manifest))
    required = dependencies.get("stilyagi-test-fixtures")
    assert isinstance(required, dict), (
        f"{manifest} must require stilyagi-test-fixtures, found {required!r}"
    )
    declared = typ.cast("dict[str, object]", required).get("version")
    assert declared == expected, (
        f"{manifest} requires stilyagi-test-fixtures {declared!r},"
        f" but the workspace is {expected!r}"
    )


def test_the_pyproject_version_is_literal() -> None:
    """The Python version is a literal: dynamic versioning would defeat the check."""
    project = _table(_parse(PYPROJECT), ("project",), source="pyproject.toml")
    assert isinstance(project.get("version"), str), (
        "[project].version must be a literal string"
    )
    dynamic = project.get("dynamic")
    assert not dynamic or "version" not in typ.cast("list[object]", dynamic), (
        "[project] must not compute its version dynamically"
    )
