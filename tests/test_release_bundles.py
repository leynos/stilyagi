"""Specify the checks on the bundle the published Release carries.

A Release's provenance is the Sigstore bundle attached beside its assets, and
that bundle is what a consumer checks. It names the files it attested by digest,
so it covers a Release only when one statement names *every* asset the Release
holds: a bundle attached for a rebuild, or a file added to the Release by hand,
leaves the rest of the Release unattested. These tests state that rule from
both sides, on the upload that attaches a bundle and on the Release the check
reads afterwards.
"""

import typing as typ

import pytest
import release_bundles
import release_github_upload
from release_assets import PypiFile, ReleaseAssetError, State

from tests.support.release_assets_fixtures import digest, write_bundle, write_file

if typ.TYPE_CHECKING:
    import pathlib


def _pypi(name: str, url: str = "https://x/a") -> dict[str, PypiFile]:
    """Return a one-file PyPI holding whose digest matches no real payload."""
    return {name: PypiFile(sha256="ab", url=url)}


# -- the bundle the published Release carries -------------------------------


def _release_with_bundle(
    tmp_path: pathlib.Path, held: dict[str, bytes]
) -> tuple[State, pathlib.Path]:
    """Return a Release holding ``held`` plus a bundle attesting it."""
    publish = tmp_path / "publish"
    bundles = tmp_path / "release-bundles"
    write_file(publish, "a.whl", b"a")
    write_file(publish, "b.whl", b"b")
    write_bundle(bundles, "run6.sigstore.json", held)
    state = State(
        publish=publish,
        pypi=_pypi("a.whl") | {"b.whl": PypiFile("ab", "https://x/b")},
        github={
            "a.whl": digest(publish / "a.whl"),
            "b.whl": digest(publish / "b.whl"),
            "run6.sigstore.json": digest(bundles / "run6.sigstore.json"),
        },
    )
    return state, bundles


def test_a_releases_bundle_that_covers_every_asset_passes(
    tmp_path: pathlib.Path,
) -> None:
    """The check reads the Release's own bundle, as a consumer would."""
    state, bundles = _release_with_bundle(tmp_path, {"a.whl": b"a", "b.whl": b"b"})

    release_bundles.check_release_bundle(state, bundles)


def test_a_releases_bundle_that_misses_an_asset_does_not_pass(
    tmp_path: pathlib.Path,
) -> None:
    """A bundle naming only some of the Release's assets leaves the rest bare.

    An asset attached to the Release outside this workflow has no statement in
    the bundle, and finding the bundle present is not the same as finding the
    assets covered. Publishing would make a provenance claim that excludes
    that file.
    """
    state, bundles = _release_with_bundle(tmp_path, {"a.whl": b"a"})

    with pytest.raises(ReleaseAssetError, match="no provenance bundle covering"):
        release_bundles.check_release_bundle(state, bundles)


def test_a_release_holding_no_bundle_does_not_pass_the_bundle_check(
    tmp_path: pathlib.Path,
) -> None:
    """A Release that never received a bundle is refused, and says so."""
    publish = tmp_path / "publish"
    write_file(publish, "a.whl", b"a")
    state = State(
        publish=publish,
        pypi=_pypi("a.whl"),
        github={"a.whl": digest(publish / "a.whl")},
    )

    with pytest.raises(ReleaseAssetError, match="no bundle at all"):
        release_bundles.check_release_bundle(state, tmp_path / "release-bundles")


def test_a_bundle_naming_other_bytes_does_not_pass(
    tmp_path: pathlib.Path,
) -> None:
    """The statement must name the bytes the Release holds now, not a rebuild."""
    state, bundles = _release_with_bundle(
        tmp_path, {"a.whl": b"a-rebuild", "b.whl": b"b-rebuild"}
    )

    with pytest.raises(ReleaseAssetError, match="no provenance bundle covering"):
        release_bundles.check_release_bundle(state, bundles)


def test_an_asset_with_no_digest_does_not_pass_the_bundle_check(
    tmp_path: pathlib.Path,
) -> None:
    """An asset GitHub reports no digest for cannot be shown to be covered."""
    publish = tmp_path / "publish"
    write_file(publish, "a.whl", b"a")
    state = State(publish=publish, pypi=_pypi("a.whl"), github={"a.whl": None})

    with pytest.raises(ReleaseAssetError, match="no digest"):
        release_bundles.check_release_bundle(state, tmp_path / "release-bundles")


def test_the_release_bundles_are_reported_by_name(tmp_path: pathlib.Path) -> None:
    """The workflow downloads exactly the bundles the Release lists."""
    publish = tmp_path / "publish"
    write_file(publish, "a.whl", b"a")
    state = State(
        publish=publish,
        pypi=_pypi("a.whl"),
        github={
            "a.whl": digest(publish / "a.whl"),
            "run7.sigstore.json": "ab",
            "run6.sigstore.json": "cd",
        },
    )

    assert release_bundles.held_bundles(state) == [
        "run6.sigstore.json",
        "run7.sigstore.json",
    ], "bundles must be listed in a stable order, and never as artefacts"


# -- attaching a bundle to the Release -------------------------------------


def test_a_release_without_provenance_receives_one_bundle(
    tmp_path: pathlib.Path,
) -> None:
    """A first release attaches one record, not one per bundle it was handed."""
    publish = tmp_path / "publish"
    bundles = tmp_path / "attestations"
    output = tmp_path / "upload"
    write_file(publish, "a.whl", b"a")
    write_bundle(bundles, "run7.sigstore.json", {"a.whl": b"a"})
    write_bundle(bundles, "run6.sigstore.json", {"a.whl": b"a"})
    state = State(publish=publish, pypi={}, github={})

    release_github_upload.stage_github(state, bundles, output)

    staged = sorted(path.name for path in output.iterdir())
    assert [name for name in staged if name.endswith(".sigstore.json")] == [
        "run6.sigstore.json"
    ], staged


def test_a_first_release_fills_its_gap_from_its_own_build(
    tmp_path: pathlib.Path,
) -> None:
    """Before PyPI has the name, this run's bytes *are* the canonical bytes."""
    publish = tmp_path / "publish"
    bundles = tmp_path / "attestations"
    output = tmp_path / "upload"
    write_file(publish, "a.whl", b"a")
    write_bundle(bundles, "run7.sigstore.json", {"a.whl": b"a"})
    state = State(publish=publish, pypi={}, github={})

    assert (
        release_github_upload.stage_github(state, bundles, output, pypi_published=False)
        == []
    ), "a name already on PyPI is never also copied from this run's rebuild"
    assert (output / "a.whl").read_bytes() == b"a", sorted(
        path.name for path in output.iterdir()
    )


def test_a_bundle_for_other_bytes_is_not_attached_to_this_release(
    tmp_path: pathlib.Path,
) -> None:
    """A re-run carries PyPI's bytes, so its own bundle attests the wrong ones.

    The Release is left with no bundle rather than one naming a rebuild it does
    not hold: a consumer cannot check provenance for bytes the Release lacks,
    and a bundle attached for them would be evidence of something else.
    """
    publish = tmp_path / "publish"
    bundles = tmp_path / "attestations"
    output = tmp_path / "upload"
    write_file(publish, "a.whl", b"this-runs-rebuild")
    write_bundle(bundles, "run7.sigstore.json", {"a.whl": b"this-runs-rebuild"})
    state = State(
        publish=publish,
        pypi={"a.whl": PypiFile(sha256="ab", url="https://x/a")},
        github={},
    )

    with pytest.raises(ReleaseAssetError, match="no provenance bundle"):
        release_github_upload.stage_github(state, bundles, output)
    assert not list(output.iterdir()), "the refusal must stage nothing"


def test_a_bundle_covering_only_some_assets_is_not_coverage(
    tmp_path: pathlib.Path,
) -> None:
    """Every asset the Release receives must be named by the bundle attached."""
    publish = tmp_path / "publish"
    bundles = tmp_path / "attestations"
    output = tmp_path / "upload"
    write_file(publish, "a.whl", b"a")
    write_file(publish, "b.whl", b"b")
    write_bundle(bundles, "run7.sigstore.json", {"a.whl": b"a"})
    state = State(publish=publish, pypi={}, github={})

    with pytest.raises(ReleaseAssetError, match="no provenance bundle"):
        release_github_upload.stage_github(state, bundles, output)


def test_an_unreadable_bundle_is_not_read_as_coverage(
    tmp_path: pathlib.Path,
) -> None:
    """A staged file that is not a verifier answer covers nothing.

    Coverage is decided by reading the bundle, so a placeholder -- an empty
    file, a truncated copy, or a differently shaped document -- must refuse
    rather than pass as a bundle whose subjects happen to be unread.
    """
    publish = tmp_path / "publish"
    bundles = tmp_path / "attestations"
    write_file(publish, "a.whl", b"a")
    write_file(bundles, "run7.sigstore.json", b"not a verifier answer")
    state = State(publish=publish, pypi={}, github={})

    with pytest.raises(ReleaseAssetError, match="no provenance bundle"):
        release_github_upload.stage_github(state, bundles, tmp_path / "upload")


def test_a_release_holding_its_bundle_receives_no_second_one(
    tmp_path: pathlib.Path,
) -> None:
    """The bundle is attached once, on the run that first fills the Release.

    A later run that also has a local gap must not attach its own bundle as
    well: the Release then carries two records of the same bytes, and the
    run-unique name means neither is ever replaced.
    """
    publish = tmp_path / "publish"
    bundles = tmp_path / "attestations"
    output = tmp_path / "upload"
    write_file(publish, "b.whl", b"b")
    write_bundle(bundles, "run7.sigstore.json", {"b.whl": b"b"})
    state = State(
        publish=publish,
        pypi={},
        github={"run6.sigstore.json": "ab"},
    )

    assert release_github_upload.stage_github(state, bundles, output) == [], (
        "the name the Release lacks is local, so nothing is fetched from PyPI"
    )
    assert sorted(path.name for path in output.iterdir()) == ["b.whl"], sorted(
        path.name for path in output.iterdir()
    )
