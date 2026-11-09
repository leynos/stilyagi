"""Reconcile the release artefacts so PyPI and the GitHub Release agree.

A re-pushed tag rebuilds every artefact, and rebuilt wheels are rarely
byte-identical, so each filename's canonical bytes are the ones already
published: PyPI's first, then an existing GitHub Release asset, and this run's
freshly built and attested file only when neither destination has the name.
Each destination receives only the names it lacks and nothing is overwritten.

``scripts/release_assets_cli.py`` wraps this module in the command-line
interface ``release.yml`` calls, importing it wholesale, so it inherits that
wrapper's constraint: it executes inside the job that holds the PyPI
publishing token, so it resolves no third-party code (Cyclopts or Cuprum) at
release time, and every network call stays in the workflow's ``curl`` and
``gh`` steps. ``scripts/release_github_upload.py`` assembles and checks the
upload set the GitHub Release receives.
"""

import dataclasses as dc
import enum
import hashlib
import json
import os
import re
import shutil
import typing as typ
import urllib.parse
from pathlib import Path

from release_provenance import ProvenanceRecordError, require_matching_record

if typ.TYPE_CHECKING:
    import collections.abc as cabc

#: The PEP 691 JSON simple index; relative file URLs resolve against it.
INDEX_URL = "https://pypi.org/simple/stilyagi/"

#: Artefact names this module will stage. Wheel and sdist names never need
#: more, and the bound keeps a name safe as a path and as a TSV field.
_SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]*")
_DIGEST_PREFIX = "sha256:"


class ReleaseAssetError(Exception):
    """A release asset is missing, unsafe, or holds unexpected bytes."""


class Source(enum.StrEnum):
    """Where one artefact name's canonical bytes come from."""

    PYPI = "pypi"
    GITHUB = "github"
    LOCAL = "local"


@dc.dataclass(frozen=True, slots=True)
class Plan:
    """The canonical source of each name and what each destination lacks."""

    canonical: cabc.Mapping[str, Source]
    pypi_uploads: frozenset[str]
    github_uploads: frozenset[str]


def canonical_source(
    name: str,
    on_pypi: cabc.Collection[str],
    on_github: cabc.Collection[str],
) -> Source:
    """Return the destination whose bytes are canonical for ``name``.

    PyPI outranks the GitHub Release, and the Release outranks this run's
    rebuilt file, because a published name's bytes can never be replaced.

    Parameters
    ----------
    name
        The artefact name to decide.
    on_pypi
        Names PyPI already holds.
    on_github
        Names the tag's GitHub Release already holds.

    Returns
    -------
    Source
        The first destination in precedence order that holds ``name``.

    Examples
    --------
    >>> canonical_source("a.whl", {"a.whl"}, {"a.whl"})
    <Source.PYPI: 'pypi'>
    >>> canonical_source("b.whl", set(), set())
    <Source.LOCAL: 'local'>
    """
    if name in on_pypi:
        return Source.PYPI
    if name in on_github:
        return Source.GITHUB
    return Source.LOCAL


def plan(
    local: cabc.Iterable[str],
    on_pypi: cabc.Collection[str],
    on_github: cabc.Collection[str],
) -> Plan:
    """Choose each name's canonical bytes and the uploads each side needs.

    Parameters
    ----------
    local
        The artefact names this run built and attested.
    on_pypi
        Names PyPI already holds.
    on_github
        Names the tag's GitHub Release already holds, draft or published.

    Returns
    -------
    Plan
        PyPI takes precedence over GitHub, and GitHub over this run's bytes;
        each destination is sent exactly the names it lacks.

    Examples
    --------
    >>> plan(["c.whl"], set(), {"c.whl"}).canonical["c.whl"]
    <Source.GITHUB: 'github'>
    """
    names = frozenset(local)
    canonical = {name: canonical_source(name, on_pypi, on_github) for name in names}
    return Plan(
        canonical=canonical,
        pypi_uploads=frozenset(name for name in names if name not in on_pypi),
        github_uploads=frozenset(name for name in names if name not in on_github),
    )


def mismatches(
    local: cabc.Iterable[str],
    pypi_digests: cabc.Mapping[str, str],
    github_digests: cabc.Mapping[str, str | None],
) -> list[str]:
    """Describe every name the two destinations do not hold identically.

    Parameters
    ----------
    local
        The artefact names the release must carry.
    pypi_digests
        PyPI's SHA-256 hex digest for each name it holds.
    github_digests
        The GitHub Release's SHA-256 hex digest per asset, ``None`` when
        GitHub reports none.

    Returns
    -------
    list[str]
        One message per missing or differing name; empty when they agree.

    Examples
    --------
    >>> mismatches(["c.whl"], {"c.whl": "ab"}, {"c.whl": "ab"})
    []
    """
    return [
        problem
        for name in sorted(set(local))
        if (problem := _mismatch(name, pypi_digests, github_digests))
    ]


def _mismatch(
    name: str,
    pypi_digests: cabc.Mapping[str, str],
    github_digests: cabc.Mapping[str, str | None],
) -> str | None:
    """Describe how one name differs between the destinations, if it does."""
    pypi, github = pypi_digests.get(name), github_digests.get(name)
    if pypi is None:
        return f"{name} is missing from PyPI"
    if github is None:
        return f"{name} is missing from the GitHub Release or has no digest"
    if pypi != github:
        return f"{name} differs: PyPI sha256 {pypi}, GitHub sha256 {github}"
    return None


@dc.dataclass(frozen=True, slots=True)
class PypiFile:
    """One file the PyPI index lists."""

    sha256: str
    url: str


def read_pypi_index(path: Path) -> dict[str, PypiFile]:
    """Map each filename in a PEP 691 JSON index to its digest and URL."""
    document = json.loads(path.read_text(encoding="utf-8"))
    return {
        entry["filename"]: PypiFile(
            sha256=entry["hashes"]["sha256"].lower(),
            url=urllib.parse.urljoin(INDEX_URL, entry["url"]),
        )
        for entry in document.get("files", [])
    }


def read_github_assets(path: Path) -> dict[str, str | None]:
    """Map each asset in ``gh release view --json assets`` to its digest."""
    document = json.loads(path.read_text(encoding="utf-8"))
    return {
        asset["name"]: _digest_hex(asset.get("digest"))
        for asset in document.get("assets", [])
    }


def _digest_hex(digest: object) -> str | None:
    """Return the hex of a ``sha256:`` digest; ``None`` for any other form."""
    if isinstance(digest, str) and digest.startswith(_DIGEST_PREFIX):
        return digest.removeprefix(_DIGEST_PREFIX).lower()
    return None


def sha256_of(path: Path) -> str:
    """Return the SHA-256 hex digest of one file's bytes."""
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def local_names(directory: Path) -> list[str]:
    """Return the artefact names in ``directory``, refusing any unsafe name.

    A directory entry is not an artefact, so an entry that is not a regular
    file is refused for the same reason as an unsafe name: it cannot be
    digested and it would not travel as one file.

    Parameters
    ----------
    directory
        The directory holding this run's built and attested artefacts.

    Returns
    -------
    list[str]
        The artefact names, sorted.

    Raises
    ------
    ReleaseAssetError
        If a name is not safe as a path and a TSV field, or an entry is not a
        regular file.
    """
    entries = sorted(directory.iterdir(), key=lambda path: path.name)
    names = [path.name for path in entries]
    unsafe = [
        name
        for path, name in zip(entries, names, strict=True)
        if not path.is_file() or not _SAFE_NAME.fullmatch(name)
    ]
    if unsafe:
        msg = f"refusing unsafe artefact names: {unsafe}"
        raise ReleaseAssetError(msg)
    return names


def require_digest(path: Path, expected: str | None) -> None:
    """Raise unless ``path`` holds bytes with the ``expected`` digest.

    Parameters
    ----------
    path
        The file whose bytes are hashed.
    expected
        The expected SHA-256 hex digest. ``None`` never matches, because a
        destination that reports no digest establishes nothing.

    Raises
    ------
    ReleaseAssetError
        If the file's digest differs from ``expected``.
    """
    actual = sha256_of(path)
    if expected is None or actual != expected:
        msg = f"{path.name} has sha256 {actual}, expected {expected}"
        raise ReleaseAssetError(msg)


def write_output(name: str, *, value: bool) -> None:
    """Append one ``true``/``false`` step output for the workflow."""
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
        output.write(f"{name}={str(value).lower()}\n")


@dc.dataclass(frozen=True, slots=True)
class State:
    """The run's artefacts and what each destination already holds."""

    publish: Path
    pypi: dict[str, PypiFile]
    github: dict[str, str | None]

    @classmethod
    def load(cls, publish: Path, index: Path | None, assets: Path) -> State:
        """Read the staged artefacts, the PyPI index, and the asset listing."""
        pypi = read_pypi_index(index) if index is not None else {}
        return cls(publish, pypi, read_github_assets(assets))

    def plan(self) -> Plan:
        """Plan this run's uploads against both destinations."""
        return plan(local_names(self.publish), self.pypi, self.github)


def carryover(state: State) -> list[str]:
    """Return the names whose GitHub bytes PyPI may need."""
    return sorted(set(local_names(state.publish)) & set(state.github))


def _require_carried_asset(
    name: str, carried: Path, provenance: Path | None, digest: str | None
) -> None:
    """Refuse a carried asset whose bytes or provenance are not established.

    The digest check alone proves only that the downloaded file matches what
    the Release's API reports *now*, which is not the same as proving that
    this repository's release workflow built it. A repository writer can
    manage releases without holding the PyPI token, so an asset substituted
    into a failed run's draft would otherwise reach PyPI under the expected
    name. The provenance record is the only evidence that did not come from
    the Release, so a carry without one is refused rather than trusted.

    That record is only worth as much as the verifier that wrote it. The step
    producing it pins ``--repo``, ``--signer-workflow release.yml``,
    ``--source-ref "${GITHUB_REF}"`` and ``--deny-self-hosted-runners``, so a
    record can only exist when this repository's release workflow signed
    these bytes for this tag; an asset attached by hand has none. Do not
    relax that step without restoring an equivalent binding here.

    ``provenance`` is ``None`` when the job that verified the assets uploaded
    no record — which is a refusal, not a licence to skip.

    Raises
    ------
    ReleaseAssetError
        If the file's digest differs from the Release's, or no verified record
        attests it.
    """
    require_digest(carried, digest)
    if provenance is None:
        msg = (
            f"cannot safely carry GitHub asset {name} to PyPI: no provenance "
            "record was supplied; rerun once the verification step has run"
        )
        raise ReleaseAssetError(msg)
    try:
        require_matching_record(provenance, name, sha256_of(carried))
    except ProvenanceRecordError as error:
        msg = f"cannot safely carry GitHub asset {name} to PyPI: {error}"
        raise ReleaseAssetError(msg) from error


def stage_pypi(
    state: State, github_files: Path, provenance: Path | None = None
) -> bool:
    """Leave in ``publish`` exactly the canonical bytes PyPI lacks.

    Parameters
    ----------
    state
        The staged artefacts and both destinations' holdings.
    github_files
        The GitHub Release assets ``draft-release`` downloaded.
    provenance
        The directory whose ``<asset>.json`` files hold the verifier's
        results. A name carried from the Release is sent on only when a
        record attests exactly those bytes; ``None`` refuses every carry.

    Returns
    -------
    bool
        Whether any artefact remains to upload.
    """
    decided = state.plan()
    for name, source in sorted(decided.canonical.items()):
        artefact = state.publish / name
        if source is Source.PYPI:
            print(f"::notice::Skipping {name}: already on PyPI")
            artefact.unlink()
        elif source is Source.GITHUB:
            carried = github_files / name
            _require_carried_asset(name, carried, provenance, state.github[name])
            print(f"::notice::Uploading the GitHub Release's bytes for {name}")
            shutil.copyfile(carried, artefact)
    if not decided.pypi_uploads:
        print("Every artefact is already on PyPI; nothing to publish.")
    return bool(decided.pypi_uploads)
