"""Decide whether a provenance bundle covers the GitHub Release's assets.

``actions/attest-build-provenance`` attaches a Sigstore bundle beside the files
it signs, and that bundle is the provenance a consumer of the Release can
check. A bundle covers a Release only when one statement names every asset, by
name and digest: a bundle attached for a rebuild, or a file added to the
Release by hand, leaves the rest of the Release unattested.

Coverage is asked of a *statement*, never of a collection. Reading the union of
several statements would pass a Release no single signature vouches for: two
bundles covering one asset each, beside a third whose edited statement names
both, would otherwise satisfy the check that neither signature does. The same
holds inside one file, since ``gh attestation download`` writes JSON lines.

Like the other release modules, this one resolves no third-party code and makes
no network call: the workflow's ``gh`` steps list and download the bundles it
reads.
"""

import shutil
import typing as typ

from release_assets import ReleaseAssetError
from release_provenance import ProvenanceRecordError, has_matching_subject
from release_sigstore import read_bundle_statements

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    from pathlib import Path

    from release_assets import State

#: The suffix every provenance bundle's name carries.
BUNDLE_SUFFIX = ".sigstore.json"


def _covers(statement: object, assets: cabc.Mapping[str, str]) -> bool:
    """Return whether one statement names every asset and digest in ``assets``.

    Coverage means every asset, not any one of them: a Release published with a
    statement attesting some of its files leaves the rest with a provenance
    claim that says nothing about them. It is deliberately one statement and
    not a set: two statements naming one asset each are two signatures, and
    neither of them vouches for the Release both are read to cover.

    Returns
    -------
    bool
        Whether every name and digest in ``assets`` appears in ``statement``.
    """
    return all(
        has_matching_subject([statement], name, digest)
        for name, digest in assets.items()
    )


def _covering_bundle(bundle: Path, assets: cabc.Mapping[str, str]) -> bool:
    """Return whether one bundle's file holds a statement covering ``assets``.

    A bundle file may hold several statements, and each is asked separately. A
    file that is not a bundle at all covers nothing, so it answers ``False``
    here rather than raising: each caller's refusal names what would be
    published otherwise.

    Returns
    -------
    bool
        Whether one of the file's statements covers every asset.
    """
    try:
        records = read_bundle_statements(bundle)
    except ProvenanceRecordError:
        return False
    return any(_covers(record, assets) for record in records)


def verified_bundle_names(directory: Path, assets: cabc.Mapping[str, str]) -> list[str]:
    """Return the bundles in ``directory`` that verified against every asset.

    The directory is one the workflow's ``gh attestation verify --bundle`` loop
    filled, so a name that is absent there answered nothing for the Release.
    That absence is the point rather than an indirect way of asking the same
    question: the answer that admits an asset is a signature over the bundle's
    statement, and decoding alone would accept an edited one.

    Parameters
    ----------
    directory
        The directory holding a copy of each bundle that verified.
    assets
        Each artefact name and the digest it must be named under.

    Returns
    -------
    list[str]
        The verified bundles whose statement covers every asset.
    """
    return [
        name
        for name in bundle_names(directory)
        if _covering_bundle(directory / name, assets)
    ]


def bundle_names(directory: Path) -> list[str]:
    """Return the provenance bundles in ``directory``, in a stable order.

    An absent directory holds no bundles rather than being an error: a Release
    the workflow never managed to download a bundle from is exactly the case
    the caller refuses on, and it must refuse there rather than raise an
    unrelated ``FileNotFoundError``.

    Returns
    -------
    list[str]
        The ``.sigstore.json`` file names found, sorted by name.
    """
    return (
        sorted(
            path.name
            for path in directory.iterdir()
            if path.name.endswith(BUNDLE_SUFFIX)
        )
        if directory.is_dir()
        else []
    )


def held_bundles(state: State) -> list[str]:
    """Return the provenance bundles the GitHub Release holds, sorted."""
    return sorted(name for name in state.github if name.endswith(BUNDLE_SUFFIX))


def holds_bundle(assets: cabc.Iterable[str]) -> bool:
    """Return whether the Release already holds a provenance bundle."""
    return any(name.endswith(BUNDLE_SUFFIX) for name in assets)


def artefact_digests(assets: cabc.Mapping[str, str | None]) -> dict[str, str]:
    """Return the digest of each asset that is an artefact rather than evidence.

    An asset GitHub reports no digest for cannot be shown to be attested, so it
    is refused here instead of being dropped from the set the bundle must
    cover: dropping it would publish a Release whose provenance claim silently
    excludes one of its files.

    Returns
    -------
    dict[str, str]
        Each artefact name and its digest, with the bundle names left out.

    Raises
    ------
    ReleaseAssetError
        If an artefact's digest is missing from the listing.
    """
    missing = sorted(
        name
        for name, digest in assets.items()
        if digest is None and not name.endswith(BUNDLE_SUFFIX)
    )
    if missing:
        msg = f"the GitHub Release reports no digest for {missing}"
        raise ReleaseAssetError(msg)
    return {
        name: digest
        for name, digest in assets.items()
        if digest is not None and not name.endswith(BUNDLE_SUFFIX)
    }


def copy_covering_bundle(bundles: Path, assets: dict[str, str], output: Path) -> None:
    """Copy one of this run's bundles into ``output`` when one covers ``assets``.

    Name alone does not establish coverage: the bytes a run attaches may come
    from PyPI rather than from its own build, and this run's bundle then
    attests *different* bytes. A bundle is attached only if one of its
    statements names every digest the Release is receiving. A Release left with
    no such bundle is refused here rather than published with provenance for
    bytes it does not hold; the refusal names the repair, because no retry of
    the same run can supply the missing statement.

    Raises
    ------
    ReleaseAssetError
        If none of this run's bundles covers ``assets``.
    """
    covering = [
        name
        for name in bundle_names(bundles)
        if _covering_bundle(bundles / name, assets)
    ]
    if not covering:
        msg = (
            "the Release holds no provenance bundle and none of this run's "
            "covers the assets it is receiving, so publishing would attach a "
            "record of other bytes. Attach the run's attestation for those "
            "bytes from the repository's attestation store to the draft "
            "Release, then re-run."
        )
        raise ReleaseAssetError(msg)
    shutil.copyfile(bundles / covering[0], output / covering[0])


def check_release_bundle(state: State, bundle_dir: Path) -> None:
    """Raise unless one verified bundle covers every asset the Release holds.

    The bundle beside the assets is the provenance a consumer checks, and it
    is read here as a consumer would: downloaded from the Release, verified,
    decoded, and compared against the Release's own asset digests. That is the
    claim the published Release makes, and it is checked on the run that
    uploaded nothing as well as on the one that uploaded, because a Release can
    also become unattested by having an asset attached to it outside this
    workflow.

    ``bundle_dir`` is the directory the workflow's verification loop filled, so
    a bundle it refused is not here to be read. Coverage over the whole
    directory would admit a Release no signature covers, and coverage of a
    statement that was never verified is the same claim with less evidence.

    Parameters
    ----------
    state
        The staged artefacts and both destinations' holdings. ``state.github``
        is the Release's asset listing, which supplies the digests the bundle
        must cover.
    bundle_dir
        The directory holding the copies of the Release's bundles that
        verified, named as the Release lists them.

    Raises
    ------
    ReleaseAssetError
        If the Release holds no bundle, an asset has no digest, or no verified
        bundle covers every asset.
    """
    digests = artefact_digests(state.github)
    if not verified_bundle_names(bundle_dir, digests):
        held = bundle_names(bundle_dir)
        msg = (
            f"the GitHub Release holds no verified provenance bundle covering "
            f"{sorted(digests)}, so publishing it would attach provenance for "
            f"other bytes. It holds "
            f"{held or 'no bundle that verified against every asset'}. Attach "
            "the attestation for these bytes from the repository's attestation "
            "store, then re-run."
        )
        raise ReleaseAssetError(msg)
