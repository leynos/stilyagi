"""Decide whether a provenance bundle covers the GitHub Release's assets.

``actions/attest-build-provenance`` attaches a Sigstore bundle beside the files
it signs, and that bundle is the provenance a consumer of the Release can
check. A bundle covers a Release only when one statement names every asset, by
name and digest: a bundle attached for a rebuild, or a file added to the
Release by hand, leaves the rest of the Release unattested.

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


def _covers(bundle: Path, assets: cabc.Mapping[str, str]) -> bool:
    """Return whether one bundle's statement covers every asset's bytes.

    A bundle names the files its run attested, by digest. Coverage means every
    asset, not any one of them: a Release published with a bundle attesting
    some of its files leaves the rest with a provenance claim that says
    nothing about them. A file that is not a bundle at all covers nothing, so
    it answers ``False`` here rather than raising: each caller's refusal names
    what would be published otherwise.

    Returns
    -------
    bool
        Whether every name and digest in ``assets`` appears in the bundle.
    """
    try:
        records = read_bundle_statements(bundle)
    except ProvenanceRecordError:
        return False
    return all(
        has_matching_subject(records, name, digest) for name, digest in assets.items()
    )


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
    attests *different* bytes. A bundle is attached only if its statement names
    every digest the Release is receiving. A Release left with no such bundle
    is refused here rather than published with provenance for bytes it does
    not hold; the refusal names the repair, because no retry of the same run
    can supply the missing statement.

    Raises
    ------
    ReleaseAssetError
        If none of this run's bundles covers ``assets``.
    """
    covering = [
        name for name in bundle_names(bundles) if _covers(bundles / name, assets)
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
    """Raise unless a bundle the Release holds covers every asset it holds.

    The bundle beside the assets is the provenance a consumer checks, and it
    is read here as a consumer would: downloaded from the Release, decoded, and
    compared against the Release's own asset digests. That is the claim the
    published Release makes, and it is checked on the run that uploaded
    nothing as well as on the one that uploaded, because a Release can also
    become unattested by having an asset attached to it outside this workflow.

    Parameters
    ----------
    state
        The staged artefacts and both destinations' holdings. ``state.github``
        is the Release's asset listing, which supplies the digests the bundle
        must cover.
    bundle_dir
        The directory the Release's ``.sigstore.json`` assets were downloaded
        into.

    Raises
    ------
    ReleaseAssetError
        If the Release holds no bundle, an asset has no digest, or no bundle
        covers every asset.
    """
    digests = artefact_digests(state.github)
    covering = [
        name for name in bundle_names(bundle_dir) if _covers(bundle_dir / name, digests)
    ]
    if not covering:
        held = bundle_names(bundle_dir)
        msg = (
            f"the GitHub Release holds no provenance bundle covering "
            f"{sorted(digests)}, so publishing it would attach provenance for "
            f"other bytes. It holds {held or 'no bundle at all'}. Attach the "
            "attestation for these bytes from the repository's attestation "
            "store, then re-run."
        )
        raise ReleaseAssetError(msg)
