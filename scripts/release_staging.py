"""Stage the artefact set PyPI receives, refusing an unsafe carry.

``stage_pypi`` is the command ``release.yml``'s ``publish-pypi`` job runs
before the upload: it leaves in ``dist/publish`` exactly the canonical bytes
PyPI lacks, and refuses rather than proceed where the bytes it was promised are
not the bytes it has.

It lives apart from ``release_assets`` because it is a command rather than a
decision. The pure rules it dispatches over -- which destination is canonical
for a name, and what each side lacks -- are in ``release_assets``; this module
performs the filesystem work and states the two refusals that guard it.

``scripts/release_assets_cli.py`` imports the command through
``release_assets``, which re-exports it, so the wrapper's constraint is
unchanged: no third-party code is resolved at release time.
"""

import shutil
import typing as typ

from release_assets import (
    Plan,
    ReleaseAssetError,
    Source,
    State,
    local_names,
    plan,
    require_digest,
    sha256_of,
)
from release_provenance import ProvenanceRecordError, require_matching_record

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    from pathlib import Path


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
    no record -- which is a refusal, not a licence to skip.

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


def _refuse_rebuild_beside_an_earlier_build(
    decided: Plan, on_pypi: cabc.Collection[str]
) -> None:
    """Refuse to add this run's rebuild beside an earlier build of the tag.

    ``pypa/gh-action-pypi-publish`` uploads file by file, so an interrupted
    attempt can leave PyPI holding some of the tag's names and not the rest.
    A re-run that sent its own bytes for the remainder would leave PyPI with
    two builds that never formed a pair, and no single provenance statement
    covers both -- the state ``adr-0015`` calls a mixed release. It cannot be
    repaired, because a published filename can never be replaced.

    The distinction from the legitimate carry is where the missing name's
    bytes come from, not how many names PyPI holds. A run that fills the gap
    from the Release sends bytes an earlier run built and signed
    (``Source.GITHUB``); a run that fills it from its own rebuild sends bytes
    no destination has seen (``Source.LOCAL``). Only the second is refused.

    Raises
    ------
    ReleaseAssetError
        If PyPI holds at least one of the tag's names and this run would add
        one of its own built bytes under a name PyPI does not hold.
    """
    rebuilt = sorted(
        name
        for name, source in decided.canonical.items()
        if source is Source.LOCAL and name in decided.pypi_uploads
    )
    if not rebuilt or not set(on_pypi) & set(decided.canonical):
        return
    msg = (
        f"refusing to add this run's rebuild ({', '.join(rebuilt)}) beside "
        f"bytes PyPI already holds ({', '.join(sorted(on_pypi))}): an "
        "interrupted upload left the tag's release mixed, and its remaining "
        "names must come from that run's build. Re-run the tag once its "
        "artefacts are retained and retrievable; adr-0015 records the "
        "recovery mechanism as unimplemented, so this release needs manual "
        "repair"
    )
    raise ReleaseAssetError(msg)


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

    Notes
    -----
    The command refuses rather than proceed in the cases its two guards name:
    a carry whose bytes or provenance are not established
    (``_require_carried_asset``), and a run that would add its own rebuild
    beside an earlier build of the same tag, which is the mixed release
    (``_refuse_rebuild_beside_an_earlier_build``). The second is checked
    before anything is deleted, so a refusal leaves ``publish`` untouched.
    """
    decided = plan(local_names(state.publish), state.pypi, state.github)
    _refuse_rebuild_beside_an_earlier_build(decided, state.pypi)
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


__all__ = ["stage_pypi"]
