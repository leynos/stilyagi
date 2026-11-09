"""Lay out the workspace ``publish-release`` runs against, and read its result.

``publish-release`` receives a working directory holding the run's rebuilt
artefacts and its attestation, and two destinations that already hold some of
the names. These helpers write that state from payloads and read back what the
scripted ``gh`` recorded, so a test states only what each destination holds in
bytes and what the job left behind.

The canonical bytes differ from the run's rebuild unless a caller says
otherwise, which is what makes a step taking the wrong source visible in what
lands on the Release. A bundle is evidence rather than an artefact: its own
bytes are its statement's, not the payload the other names share.
"""

import json
import typing as typ

from tests.support.errors import ReadingError
from tests.support.release_assets_fixtures import write_bundle

if typ.TYPE_CHECKING:
    import pathlib

    from tests.support.release_fakes import FakeRelease

#: The wheel the release run builds, in the matrix's Linux x86_64 shape.
WHEEL: typ.Final = "stilyagi-0.2.0-cp314-cp314-manylinux_2_28_x86_64.whl"
#: The source distribution the release run builds.
SDIST: typ.Final = "stilyagi-0.2.0.tar.gz"
#: This run's bundle, named for the run that wrote it.
BUNDLE: typ.Final = "stilyagi-v0.2.0-run7-1.sigstore.json"
#: The bundle an earlier run of the same tag attached to the Release.
EARLIER_BUNDLE: typ.Final = "stilyagi-v0.2.0-run6-1.sigstore.json"

#: The rebuilt payloads, which are canonical only on a first release.
_REBUILD: typ.Final = {WHEEL: b"rebuilt-wheel", SDIST: b"rebuilt-sdist"}
#: The payloads an earlier run published, which a re-run carries forward.
PUBLISHED_PAYLOADS: typ.Final = {WHEEL: b"canonical-wheel", SDIST: b"canonical-sdist"}


class Holding(typ.NamedTuple):
    """Each destination's holdings, named as the release scripts name them."""

    pypi: tuple[str, ...] = ()
    github: tuple[str, ...] = ()


def record_state(fake: FakeRelease, **state: bool) -> None:
    """Write the draft/prerelease state the fake ``gh`` edits."""
    (fake.root / "release-state.json").write_text(json.dumps(state), encoding="utf-8")


def seed_release(
    work: pathlib.Path,
    fake: FakeRelease,
    holding: Holding,
    *,
    canonical_is_rebuild: bool = False,
) -> None:
    """Write the rebuilt artefacts, this run's bundle and both holdings.

    The canonical bytes differ from the rebuild unless `canonical_is_rebuild`
    says otherwise, so a step that takes the wrong source is visible in what
    lands on the release. A first release is the exception the flag describes:
    PyPI received this run's bytes, so PyPI's bytes *are* the rebuild and this
    run's bundle covers them.

    Both destinations' copies are attested, as they would be: an artefact only
    reaches either one through a run that signed it. `EARLIER_BUNDLE` is the
    bundle that run attached to the release, so it names the canonical bytes
    rather than this run's rebuild.

    Parameters
    ----------
    work
        The job's working directory, holding ``dist/publish`` and
        ``dist/attestations``.
    fake
        The scripted destinations to fill.
    holding
        The names each destination already holds.
    canonical_is_rebuild
        Whether this run's bytes are the canonical ones, as on a first release.
    """
    publish = work / "dist" / "publish"
    for name, payload in _REBUILD.items():
        (publish / name).write_bytes(payload)
    write_bundle(work / "dist" / "attestations", BUNDLE, _REBUILD)
    canonical = dict(_REBUILD) if canonical_is_rebuild else dict(PUBLISHED_PAYLOADS)
    fake.attest(canonical)
    for directory, names in ((fake.pypi, holding.pypi), (fake.github, holding.github)):
        for name in names:
            if name != EARLIER_BUNDLE:
                (directory / name).write_bytes(canonical[name])
    if EARLIER_BUNDLE in holding.github:
        write_bundle(fake.github, EARLIER_BUNDLE, canonical)


def published(fake: FakeRelease) -> dict[str, object]:
    """Return the draft/prerelease state the release was left in.

    Parameters
    ----------
    fake
        The scripted release destination.

    Returns
    -------
    dict[str, object]
        The recorded ``draft`` and ``prerelease`` flags.

    Raises
    ------
    ReadingError
        If the run never created the release. Every test that reads the state
        expects a release to exist, so its absence is a broken fixture rather
        than a property under test.
    """
    path = fake.root / "release-state.json"
    if not path.exists():
        msg = "the release was never created"
        raise ReadingError(msg, reader="release state", path=str(path))
    return typ.cast("dict[str, object]", json.loads(path.read_text(encoding="utf-8")))


def uploads(fake: FakeRelease) -> list[tuple[str, ...]]:
    """Return every ``gh release upload`` the job made."""
    return [call for call in fake.calls("gh") if call[:2] == ("release", "upload")]


__all__ = [
    "BUNDLE",
    "EARLIER_BUNDLE",
    "PUBLISHED_PAYLOADS",
    "SDIST",
    "WHEEL",
    "Holding",
    "published",
    "record_state",
    "seed_release",
    "uploads",
]
