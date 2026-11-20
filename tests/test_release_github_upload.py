"""Specify the commands that fill and check the GitHub Release's upload set.

The Release's side of a release run is five commands in
``scripts/release_github_upload.py``: ``stage_github`` names the PyPI files to
fetch and refuses an index that does not list them, ``check_fetched`` enforces
PyPI's digest on what arrived, ``check_provenance`` demands a verified record
for every file about to be attached, ``verify`` compares the two destinations,
and ``unlisted_by_pypi`` is the predicate that decides which names the index
must list.

The theme here is the same as on PyPI's side: a command must be safe to run
twice, and must refuse rather than proceed where the bytes it was promised are
not the bytes it has. A stale index is the sharpest case, because the bytes it
would substitute can never be corrected afterwards.
"""

import typing as typ

import pytest
import release_github_upload
from release_assets import PypiFile, ReleaseAssetError, State

from tests.support.release_assets_fixtures import (
    digest,
    write_bundle,
    write_file,
    write_provenance,
)

if typ.TYPE_CHECKING:
    import pathlib


def _pypi(name: str, url: str = "https://x/a") -> dict[str, PypiFile]:
    """Return a one-file PyPI holding whose digest matches no real payload."""
    return {name: PypiFile(sha256="ab", url=url)}


# -- staging for the GitHub Release -----------------------------------------


def test_pypi_is_not_asked_for_a_file_over_plain_http(tmp_path: pathlib.Path) -> None:
    """A transport downgrade is refused before any URL reaches ``curl``."""
    publish = tmp_path / "publish"
    bundles = tmp_path / "bundles"
    bundles.mkdir()
    write_file(publish, "c.whl", b"rebuilt")
    state = State(
        publish=publish,
        pypi={"c.whl": PypiFile(sha256="ab", url="http://pypi.example/c.whl")},
        github={},
    )
    with pytest.raises(ReleaseAssetError, match="HTTPS"):
        release_github_upload.stage_github(state, bundles, tmp_path / "out")
    assert (publish / "c.whl").exists(), "the refusal must leave the artefact alone"


def test_staging_fetches_every_missing_name_from_pypi(
    tmp_path: pathlib.Path,
) -> None:
    """Every name the Release lacks is fetched, none is copied from the rebuild.

    ``publish-release`` runs only after ``publish-pypi`` completed, so PyPI
    holds every artefact of the release and its bytes are the canonical ones.
    The rebuild stays in ``publish`` untouched: it is not the byte PyPI
    accepted, and an asset uploaded from it could never be replaced.
    """
    publish = tmp_path / "publish"
    bundles = tmp_path / "attestations"
    output = tmp_path / "upload"
    write_file(publish, "a.whl", b"a")
    write_file(publish, "b.whl", b"b")
    write_bundle(bundles, "run7.sigstore.json", {"a.whl": b"a", "b.whl": b"b"})
    state = State(
        publish=publish,
        pypi={
            "a.whl": PypiFile(sha256=digest(publish / "a.whl"), url="https://x/a"),
            "b.whl": PypiFile(sha256=digest(publish / "b.whl"), url="https://x/b"),
        },
        # The Release already records provenance, so no bundle is staged beside
        # the gap: a re-run must leave the release's assets untouched.
        github={"run6.sigstore.json": None},
    )
    assert release_github_upload.stage_github(state, bundles, output) == [
        ("a.whl", "https://x/a"),
        ("b.whl", "https://x/b"),
    ], state
    assert not list(output.iterdir()), "staging must not copy the rebuild"


def test_a_stale_index_is_refused_rather_than_filled_from_the_rebuild(
    tmp_path: pathlib.Path,
) -> None:
    """A name the index omits after this job's predecessor published is stale.

    ``publish-release`` runs only after ``publish-pypi`` completed, and that
    job completes only when the index it read held every artefact of the run.
    A name the index now omits is therefore a read that predates a write, which
    PyPI's cached simple index makes a real window. The rule is asked of the
    index alone, so it also covers a run that skipped the upload -- the run
    most exposed, since nothing in it explains the omission.

    Substituting the rebuild would put different bytes on GitHub from the ones
    PyPI accepted, and because an upload never overwrites, no retry could
    repair it.
    """
    publish = tmp_path / "publish"
    bundles = tmp_path / "attestations"
    output = tmp_path / "upload"
    write_file(publish, "a.whl", b"this-runs-rebuild")
    bundles.mkdir()
    state = State(publish=publish, pypi={}, github={})

    with pytest.raises(ReleaseAssetError, match="does not list"):
        release_github_upload.stage_github(state, bundles, output)
    assert not output.exists(), "the refusal must stage nothing"


def test_a_stale_index_refusal_names_every_unlisted_artefact(
    tmp_path: pathlib.Path,
) -> None:
    """The message is the report: it must name each name the index omits."""
    publish = tmp_path / "publish"
    bundles = tmp_path / "attestations"
    write_file(publish, "a.whl", b"a")
    write_file(publish, "b.whl", b"b")
    write_file(publish, "c.tar.gz", b"c")
    bundles.mkdir()
    state = State(
        publish=publish,
        pypi=_pypi("a.whl") | {"b.whl": PypiFile("ab", "https://x/b")},
        github={},
    )

    with pytest.raises(ReleaseAssetError, match=r"\['c\.tar\.gz'\]"):
        release_github_upload.stage_github(state, bundles, tmp_path / "out")


def test_unlisted_by_pypi_reports_exactly_the_names_the_index_omits() -> None:
    """The predicate is the whole rule, so it is stated on its own."""
    listed = {"a.whl": PypiFile(sha256="ab", url="https://x/a")}
    assert release_github_upload.unlisted_by_pypi(["a.whl"], listed) == [], (
        "a listed name is never reported"
    )
    assert release_github_upload.unlisted_by_pypi(["a.whl"], {}) == ["a.whl"], (
        "an omitted name is reported regardless of any upload this run made"
    )
    assert release_github_upload.unlisted_by_pypi(
        ["a.whl", "b.whl", "c.tar.gz"], listed
    ) == ["b.whl", "c.tar.gz"], "every omitted name is reported, sorted"


def test_checking_a_fetched_file_enforces_pypis_digest(tmp_path: pathlib.Path) -> None:
    """The bytes PyPI served are checked against the bytes PyPI advertised."""
    publish = tmp_path / "publish"
    output = tmp_path / "upload"
    write_file(publish, "a.whl", b"rebuilt")
    write_file(output, "a.whl", b"fetched")
    wrong = State(publish=publish, pypi=_pypi("a.whl"), github={})
    with pytest.raises(ReleaseAssetError):
        release_github_upload.check_fetched(wrong, output)
    right = State(
        publish=publish,
        pypi={"a.whl": PypiFile(sha256=digest(output / "a.whl"), url="https://x/a")},
        github={},
    )
    release_github_upload.check_fetched(right, output)


def test_checking_provenance_passes_a_verified_upload_set(
    tmp_path: pathlib.Path,
) -> None:
    """Every file about to be attached is covered by a verified record."""
    upload = tmp_path / "upload"
    write_file(upload, "a.whl", b"a")
    write_file(upload, "run7.sigstore.json", b"bundle")
    records = write_provenance(tmp_path / "records", {"a.whl": {"a.whl": b"a"}})

    release_github_upload.check_provenance(upload, records)


def test_checking_provenance_refuses_a_file_no_record_attests(
    tmp_path: pathlib.Path,
) -> None:
    """A Release asset cannot be replaced, so unattested bytes never travel."""
    upload = tmp_path / "upload"
    write_file(upload, "a.whl", b"a")
    write_file(upload, "b.whl", b"b")
    records = write_provenance(tmp_path / "records", {"a.whl": {"a.whl": b"a"}})

    with pytest.raises(ReleaseAssetError, match=r"b\.whl"):
        release_github_upload.check_provenance(upload, records)


def test_checking_provenance_refuses_bytes_the_record_does_not_cover(
    tmp_path: pathlib.Path,
) -> None:
    """A record for the name is not enough; it must cover exactly these bytes."""
    upload = tmp_path / "upload"
    write_file(upload, "a.whl", b"swapped")
    records = write_provenance(tmp_path / "records", {"a.whl": {"a.whl": b"a"}})

    with pytest.raises(ReleaseAssetError, match="no verified attestation"):
        release_github_upload.check_provenance(upload, records)


def test_checking_provenance_demands_a_source_commit_here(
    tmp_path: pathlib.Path,
) -> None:
    """The Release's directory asks for attribution, unlike PyPI's.

    A file carried to the Release may have been built by any run of the tag,
    so a verified signature is not enough: the record must also name the
    revision it built from. ``check_provenance`` must therefore pass
    ``require_source`` through to the record reading, or a Release asset would
    be traceable only to *some* run of the workflow.
    """
    upload = tmp_path / "upload"
    write_file(upload, "a.whl", b"a")
    records = write_provenance(
        tmp_path / "records", {"a.whl": {"a.whl": b"a"}}, source=""
    )

    with pytest.raises(ReleaseAssetError, match="names no source commit"):
        release_github_upload.check_provenance(upload, records)


def test_checking_provenance_skips_the_bundles_it_is_handed(
    tmp_path: pathlib.Path,
) -> None:
    """A bundle is evidence, not a subject: nothing attests a bundle itself."""
    upload = tmp_path / "upload"
    write_file(upload, "a.whl", b"a")
    write_file(upload, "run7.sigstore.json", b"bundle")
    write_file(upload, "run6.sigstore.json", b"earlier")
    records = write_provenance(tmp_path / "records", {"a.whl": {"a.whl": b"a"}})

    release_github_upload.check_provenance(upload, records)


# -- verification ------------------------------------------------------------


def test_verification_reports_a_destination_that_lacks_a_name(
    tmp_path: pathlib.Path,
) -> None:
    """The Release holding no digest is a disagreement, not a quiet pass."""
    publish = tmp_path / "publish"
    write_file(publish, "a.whl", b"a")
    state = State(
        publish=publish,
        pypi={"a.whl": PypiFile(sha256=digest(publish / "a.whl"), url="https://x/a")},
        github={},
    )
    assert release_github_upload.verify(state) == [
        "a.whl is missing from the GitHub Release or has no digest",
        "the GitHub Release holds no provenance bundle",
    ], release_github_upload.verify(state)


def test_a_release_holding_no_bundle_does_not_verify(tmp_path: pathlib.Path) -> None:
    """An untraceable release is not published, however well its bytes agree."""
    publish = tmp_path / "publish"
    write_file(publish, "a.whl", b"a")
    state = State(
        publish=publish,
        pypi={"a.whl": PypiFile(sha256=digest(publish / "a.whl"), url="https://x/a")},
        github={"a.whl": digest(publish / "a.whl")},
    )
    assert release_github_upload.verify(state) == [
        "the GitHub Release holds no provenance bundle"
    ], release_github_upload.verify(state)


def test_an_agreed_release_verifies_clean(tmp_path: pathlib.Path) -> None:
    """Both destinations holding the same bytes for every name is clean.

    A re-run's own bundle is absent from the Release by design, and that
    absence is not reported: the bundle describes bytes, it is not one of them.
    """
    publish = tmp_path / "publish"
    write_file(publish, "a.whl", b"a")
    state = State(
        publish=publish,
        pypi={"a.whl": PypiFile(sha256=digest(publish / "a.whl"), url="https://x/a")},
        github={
            "a.whl": digest(publish / "a.whl"),
            "run6.sigstore.json": "ab",
        },
    )
    assert release_github_upload.verify(state) == [], release_github_upload.verify(
        state
    )
