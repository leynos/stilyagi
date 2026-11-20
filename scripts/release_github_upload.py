"""Assemble and check the upload set the GitHub Release receives.

``release_assets.py`` decides which destination holds each name's canonical
bytes; this module turns that decision into the files a single workflow step
uploads, and checks them afterwards. A name PyPI holds is fetched from PyPI so
the Release receives PyPI's bytes rather than this run's rebuild; a name only
this run has is copied from its attested build. Whether the Release's own
bundle covers what it holds is ``release_bundles.py``'s question.

Like ``release_assets.py``, this module resolves no third-party code and makes
no network call: the workflow's ``curl`` and ``gh`` steps fetch what it names.
"""

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
from release_bundles import (
    BUNDLE_SUFFIX,
    artefact_digests,
    copy_covering_bundle,
    holds_bundle,
)
from release_provenance import ProvenanceRecordError, require_matching_record

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    from pathlib import Path


def _pypi_fetch_list(
    lacking: cabc.Iterable[str], pypi: cabc.Mapping[str, PypiFile]
) -> list[tuple[str, str]]:
    """Return the PyPI (name, url) pairs to fetch, insisting on HTTPS."""
    fetch = [(name, pypi[name].url) for name in lacking if name in pypi]
    if any(not url.startswith("https://") for _, url in fetch):
        msg = "every PyPI download must use HTTPS"
        raise ReleaseAssetError(msg)
    return fetch


def unlisted_by_pypi(
    lacking: cabc.Iterable[str],
    pypi: cabc.Mapping[str, PypiFile],
) -> list[str]:
    """Return the artefacts PyPI's index should list but does not.

    ``publish-release`` runs only after ``publish-pypi`` has completed, and
    that job completes only when the index it read held every artefact of the
    run. A name the Release still lacks and PyPI's index no longer lists is
    therefore not new: PyPI held it a moment ago, and the read that omits it
    predates a write this release made. PyPI's simple index is served from a
    cache, so that window is real rather than theoretical.

    The rule is asked of the index alone, deliberately not of a flag saying
    whether this run uploaded. A run that skipped the upload is the case the
    guard exists for: it skipped because the index already listed everything,
    so a later read that omits a name is stale with no upload of ours to
    explain it. Gating on "did this run upload" would leave exactly that case
    unguarded.

    Filling such a gap from this run's rebuild is unsafe. The bytes PyPI holds
    are whatever it accepted, which for a re-run's rebuild need not equal what
    this run built; the Release would then receive different bytes under a
    name PyPI has already published, and no retry could repair that, because
    attaching an asset again would overwrite a published file.

    Parameters
    ----------
    lacking
        The names the GitHub Release lacks and must receive.
    pypi
        The files PyPI's index lists.

    Returns
    -------
    list[str]
        The names that must not be filled from local bytes; empty when none.

    Examples
    --------
    >>> unlisted_by_pypi(["a.whl"], {})
    ['a.whl']
    >>> unlisted_by_pypi(["a.whl"], {"a.whl": PypiFile("ab", "https://x/a")})
    []
    """
    return sorted(name for name in lacking if name not in pypi)


def stage_github(
    state: State,
    bundles: Path,
    output: Path,
) -> list[tuple[str, str]]:
    """Stage what the GitHub Release lacks; return the PyPI files to fetch.

    Every name the Release lacks is fetched from PyPI. Staging never copies
    this run's rebuild into the upload set: by the time this job runs, PyPI
    has published every artefact of the release, so a name its index omits is
    a stale read rather than a new file, and the rebuild is not the canonical
    byte for it.

    Parameters
    ----------
    state
        The staged artefacts and both destinations' holdings.
    bundles
        The run's provenance bundles, staged for a Release that lacks them.
    output
        The directory the upload set is built in.

    Returns
    -------
    list[tuple[str, str]]
        The PyPI ``(name, url)`` pairs to fetch.

    Raises
    ------
    ReleaseAssetError
        If PyPI's index does not list an artefact the Release lacks, or a PyPI
        URL is not HTTPS.
    """
    lacking = sorted(state.plan().github_uploads)
    unlisted = unlisted_by_pypi(lacking, state.pypi)
    if unlisted:
        msg = (
            f"PyPI's index does not list {unlisted}, which the GitHub Release "
            "must also carry, so the index read predates a write this release "
            "made. Uploading this run's rebuild would put different bytes on "
            "GitHub from the ones PyPI holds, and a retry could not repair "
            "it. Re-run once the index lists every distribution."
        )
        raise ReleaseAssetError(msg)
    fetch = _pypi_fetch_list(lacking, state.pypi)
    output.mkdir(parents=True, exist_ok=True)
    # A Release that already holds a bundle is left alone: the first run's
    # record is the one a consumer checks, and a second run's describes a
    # rebuild the Release does not hold.
    if not holds_bundle(state.github):
        copy_covering_bundle(
            bundles,
            artefact_digests(_resulting_assets(state, fetch)),
            output,
        )
    return fetch


def _resulting_assets(
    state: State, fetch: cabc.Iterable[tuple[str, str]]
) -> dict[str, str | None]:
    """Return the digest map the Release holds once this run's upload lands.

    The bundle is chosen for the *finished* Release, not for the gap: a run
    that carries PyPI's bytes must attach a bundle naming those bytes, and
    this run's own bundle names its rebuild instead.

    Returns
    -------
    dict[str, str | None]
        Each name the Release will hold and its digest, or ``None`` where the
        listing reports none.
    """
    assets = dict(state.github)
    for name, _ in fetch:
        assets[name] = state.pypi[name].sha256
    return assets


def _attached_artefacts(upload: Path) -> list[Path]:
    """Return the files in ``upload`` that are assets rather than evidence."""
    return [
        artefact
        for artefact in sorted(upload.iterdir())
        if not artefact.name.endswith(BUNDLE_SUFFIX)
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
    required here is that the Release holds *a* bundle: without one, the assets
    it carries have no provenance a consumer can check, which is the whole
    point of publishing an attested release. That the bundle covers those
    assets is ``release_bundles.check_release_bundle``'s question, asked of the
    Release's own downloaded bundle rather than of any local recording.

    Returns
    -------
    list[str]
        One message per missing or differing artefact, plus one when the
        Release holds no provenance bundle; empty when all is well.
    """
    pypi = {name: file.sha256 for name, file in state.pypi.items()}
    problems = mismatches(local_names(state.publish), pypi, state.github)
    if not holds_bundle(state.github):
        problems.append("the GitHub Release holds no provenance bundle")
    return problems
