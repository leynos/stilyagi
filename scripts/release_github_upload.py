"""Assemble and check the upload set the GitHub Release receives.

``release_assets.py`` decides which destination holds each name's canonical
bytes; this module turns that decision into the files a single workflow step
uploads, and checks them afterwards. A name PyPI holds is fetched from PyPI so
the Release receives PyPI's bytes rather than this run's rebuild; a name only
this run has is copied from its attested build.

Like ``release_assets.py``, this module resolves no third-party code and makes
no network call: the workflow's ``curl`` and ``gh`` steps fetch what it names.
"""

import shutil
import typing as typ

from release_assets import (
    PypiFile,
    ReleaseAssetError,
    State,
    local_names,
    mismatches,
    require_digest,
    sha256_of,
)
from release_provenance import ProvenanceRecordError, require_matching_record

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    from pathlib import Path

#: The suffix every provenance bundle's name carries.
_BUNDLE_SUFFIX = ".sigstore.json"


def _pypi_fetch_list(
    lacking: cabc.Iterable[str], pypi: cabc.Mapping[str, PypiFile]
) -> list[tuple[str, str]]:
    """Return the PyPI (name, url) pairs to fetch, insisting on HTTPS."""
    fetch = [(name, pypi[name].url) for name in lacking if name in pypi]
    if any(not url.startswith("https://") for _, url in fetch):
        msg = "every PyPI download must use HTTPS"
        raise ReleaseAssetError(msg)
    return fetch


def _copy_pypi_gap(
    lacking: cabc.Iterable[str],
    pypi: cabc.Mapping[str, PypiFile],
    publish: Path,
    output: Path,
) -> None:
    """Copy each lacking artefact that PyPI does not list into ``output``.

    A name PyPI does not list is copied from this run's rebuild *only* when
    PyPI is expected not to have it, which is the case for a first release.
    ``stage_github`` has already refused the ambiguous case: once a run has
    published to PyPI, a name absent from the index means the index is stale,
    so the callers that reach here have established PyPI never saw the name.
    """
    for name in lacking:
        if name not in pypi:
            shutil.copyfile(publish / name, output / name)


def unlisted_after_publishing(
    lacking: cabc.Iterable[str],
    pypi: cabc.Mapping[str, PypiFile],
    *,
    pypi_published: bool,
) -> list[str]:
    """Return the artefacts PyPI should list but the index does not.

    PyPI's simple index is served from a cache, so a run that has just
    uploaded can read an index that predates its own upload. Falling back to
    this run's rebuild in that window is unsafe: the bytes published to PyPI
    are whatever PyPI accepted, and the rebuild need not equal them. GitHub
    would then be sent different bytes from PyPI's, verification would fail,
    and no retry could repair the asset, because uploading it again would
    overwrite a published asset.

    A name absent from an index read *before* this run published is not
    ambiguous: it is simply new, and this run's bytes are canonical for it.

    Parameters
    ----------
    lacking
        The names the GitHub Release lacks and must receive.
    pypi
        The files PyPI's index lists.
    pypi_published
        Whether this workflow has already published to PyPI in this release.

    Returns
    -------
    list[str]
        The names that must not be filled from local bytes; empty when none.

    Examples
    --------
    >>> unlisted_after_publishing(["a.whl"], {}, pypi_published=False)
    []
    >>> unlisted_after_publishing(["a.whl"], {}, pypi_published=True)
    ['a.whl']
    """
    if not pypi_published:
        return []
    return sorted(name for name in lacking if name not in pypi)


def _copy_first_bundle(
    bundles: Path, github: cabc.Mapping[str, str | None], output: Path
) -> None:
    """Copy one bundle into ``output`` only when the Release holds none.

    A run attests its own bytes under a run-unique name so that no asset is
    overwritten, but a re-run must still upload nothing: the Release already
    records provenance for the canonical bytes, and attaching a second bundle
    for a rebuild would describe bytes the Release does not hold. The first
    bundle to reach the Release is therefore the only one it receives, and the
    later runs' bundles stay in the attestation store.
    """
    if any(name.endswith(_BUNDLE_SUFFIX) for name in github):
        return
    for bundle in sorted(bundles.iterdir()):
        if bundle.name.endswith(_BUNDLE_SUFFIX):
            shutil.copyfile(bundle, output / bundle.name)
            return


def stage_github(
    state: State,
    bundles: Path,
    output: Path,
    *,
    pypi_published: bool = False,
) -> list[tuple[str, str]]:
    """Stage what the GitHub Release lacks; return the PyPI files to fetch.

    Parameters
    ----------
    state
        The staged artefacts and both destinations' holdings.
    bundles
        The run's provenance bundles, staged for a Release that lacks them.
    output
        The directory the upload set is built in.
    pypi_published
        Whether this workflow already published to PyPI in this release. When
        it has, a name the index does not list is a stale read rather than a
        new artefact, and staging refuses it instead of substituting bytes
        that need not match PyPI's.

    Returns
    -------
    list[tuple[str, str]]
        The PyPI ``(name, url)`` pairs to fetch.

    Raises
    ------
    ReleaseAssetError
        If an artefact is unlisted after this run published, or a PyPI URL is
        not HTTPS.
    """
    lacking = sorted(state.plan().github_uploads)
    unlisted = unlisted_after_publishing(
        lacking, state.pypi, pypi_published=pypi_published
    )
    if unlisted:
        msg = (
            f"PyPI's index does not list {unlisted} after this run published, "
            "so it is stale. Uploading this run's rebuild would put different "
            "bytes on GitHub from the ones PyPI holds, and a retry could not "
            "repair it. Re-run once the index lists every distribution."
        )
        raise ReleaseAssetError(msg)
    fetch = _pypi_fetch_list(lacking, state.pypi)
    output.mkdir(parents=True, exist_ok=True)
    _copy_pypi_gap(lacking, state.pypi, state.publish, output)
    _copy_first_bundle(bundles, state.github, output)
    return fetch


def _attached_artefacts(upload: Path) -> list[Path]:
    """Return the files in ``upload`` that are assets rather than evidence."""
    return [
        artefact
        for artefact in sorted(upload.iterdir())
        if not artefact.name.endswith(_BUNDLE_SUFFIX)
    ]


def check_provenance(upload: Path, records: Path) -> None:
    """Refuse the upload set unless every file in it is attested.

    Each file the Release is about to receive must be covered by a verified
    attestation naming exactly its bytes and the commit they were built from.
    ``records`` holds what the workflow verified: the run's own attestations,
    which cover this run's builds, and the original attestations of the names
    carried from PyPI, found by the digest PyPI published because the local
    file there is a different rebuild.

    The commit is required rather than pinned to this run, because a re-run
    legitimately attaches bytes an earlier run built. Naming the commit is what
    keeps such a file attributable; without it the Release would carry a
    signature over bytes nobody can trace to a revision.

    Parameters
    ----------
    upload
        The directory of files the Release is about to receive.
    records
        The directory of verified ``<name>.json`` records.

    Raises
    ------
    ReleaseAssetError
        If any artefact in ``upload`` has no matching verified record. The
        refusal is deliberate: a Release asset cannot be replaced, so bytes
        whose origin is unestablished must never be attached.
    """
    problems: list[str] = []
    for artefact in _attached_artefacts(upload):
        try:
            require_matching_record(
                records, artefact.name, sha256_of(artefact), require_source=True
            )
        except ProvenanceRecordError as error:
            problems.append(f"{artefact.name}: {error}")
    if problems:
        msg = (
            "refusing to attach bytes whose provenance is not established: "
            + "; ".join(problems)
        )
        raise ReleaseAssetError(msg)


def check_fetched(state: State, output: Path) -> None:
    """Raise unless every file fetched from PyPI matches PyPI's digest."""
    for name in sorted(state.plan().github_uploads & set(state.pypi)):
        require_digest(output / name, state.pypi[name].sha256)


def verify(state: State) -> list[str]:
    """Describe every artefact the two destinations do not hold identically.

    A bundle's name carries the run that wrote it, so a re-run's bundle is
    deliberately absent from the Release and is never compared. What is
    required is that the Release holds *a* bundle: without one, the assets it
    carries have no provenance a consumer can check, which is the whole point
    of publishing an attested release.

    Returns
    -------
    list[str]
        One message per missing or differing artefact, plus one when the
        Release holds no provenance bundle; empty when all is well.
    """
    pypi = {name: file.sha256 for name, file in state.pypi.items()}
    problems = mismatches(local_names(state.publish), pypi, state.github)
    if not any(name.endswith(_BUNDLE_SUFFIX) for name in state.github):
        problems.append("the GitHub Release holds no provenance bundle")
    return problems
