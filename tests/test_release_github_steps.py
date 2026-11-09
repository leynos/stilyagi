"""Run ``publish-release``: what a second run of the same tag must not redo.

``publish-release`` runs only after PyPI holds every artefact, so the release's
own gaps are filled with PyPI's bytes rather than this run's rebuild. That
ordering is the whole of the idempotence requirement: a tag run twice leaves
both destinations holding identical bytes, and the second pass uploads nothing.

The job is executed step by step against a scripted Release and PyPI, with the
repository's own ``scripts/`` linked into the workspace. The assertions are on
what the destinations end up holding and on which commands ran, so a step that
quietly re-uploads, or takes its bytes from the wrong source, fails here rather
than on a tag.
"""

import base64
import json
import typing as typ

import pytest

from tests.support.release_assets_fixtures import write_bundle
from tests.support.release_fakes import Attested, FakeRelease
from tests.support.release_github_workspace import (
    BUNDLE,
    EARLIER_BUNDLE,
    PUBLISHED_PAYLOADS,
    SDIST,
    WHEEL,
    Holding,
    published,
    record_state,
    seed_release,
    uploads,
)
from tests.support.release_publish_release import (
    COMPLETE,
    RELEASE_STEPS,
    THROUGH_VERIFY,
    WHEEL_GAP,
    publish_release_job,
    release_workspace,
    run_release_steps,
    subjects_of,
)
from tests.support.release_steps import requires_bash, run_bash
from tests.support.release_workflow import step

if typ.TYPE_CHECKING:
    import pathlib


@pytest.fixture
def workspace(tmp_path: pathlib.Path) -> tuple[pathlib.Path, FakeRelease]:
    """Return the job's working directory and its scripted destinations.

    Returns
    -------
    tuple[pathlib.Path, FakeRelease]
        The workspace ``publish-release`` would find, and the fakes behind it.
    """
    return release_workspace(tmp_path)


@requires_bash
def test_a_re_run_uploads_no_artefact_and_leaves_the_release_published(
    workspace: tuple[pathlib.Path, FakeRelease],
) -> None:
    """Both destinations hold every artefact: none is sent a second time.

    Nor is anything else. The run's own bundle is not attached either: the
    release already records provenance for the bytes it holds, and a second
    bundle would describe a rebuild the release does not carry. The run's
    attestation still reaches the attestation store, which is where it can be
    found by digest if it is ever needed.
    """
    work, fake = workspace
    seed_release(work, fake, COMPLETE)
    completed = run_release_steps(workspace)
    assert completed.returncode == 0, completed.stderr
    assert not uploads(fake), uploads(fake)
    assert not any((work / "github-upload").iterdir()), sorted(
        path.name for path in (work / "github-upload").iterdir()
    )
    assert published(fake) == {"draft": False, "prerelease": False}, published(fake)


@requires_bash
def test_a_gap_whose_bytes_no_run_attests_is_never_attached(
    workspace: tuple[pathlib.Path, FakeRelease],
) -> None:
    """The upload set is refused, so the release stays a draft.

    A Release asset cannot be replaced, so bytes whose origin is unestablished
    are not attached at all: the run fails and the release stays unpublished.
    """
    work, fake = workspace
    seed_release(work, fake, WHEEL_GAP)
    for record in fake.attestations.iterdir():
        record.unlink()
    completed = run_release_steps(workspace)
    assert completed.returncode != 0, completed.stdout
    assert "no attestations found" in completed.stderr, completed.stderr
    assert not (fake.github / WHEEL).exists(), sorted(
        path.name for path in fake.github.iterdir()
    )
    assert published(fake)["draft"] is True, "the draft was published"


@requires_bash
def test_a_gap_attested_only_by_another_repository_is_refused(
    workspace: tuple[pathlib.Path, FakeRelease],
) -> None:
    """A signature from someone else's release is not this repository's."""
    work, fake = workspace
    seed_release(work, fake, WHEEL_GAP)
    for record in fake.attestations.iterdir():
        record.unlink()
    fake.attest(
        {WHEEL: b"canonical-wheel", SDIST: b"canonical-sdist"},
        as_=Attested(repository="someone-else/stilyagi"),
    )
    completed = run_release_steps(workspace)
    assert completed.returncode != 0, completed.stdout
    assert "no attestations matched the policy" in completed.stderr, completed.stderr
    assert not (fake.github / WHEEL).exists(), sorted(
        path.name for path in fake.github.iterdir()
    )


@requires_bash
def test_a_gap_on_the_release_is_filled_with_pypi_s_bytes(
    workspace: tuple[pathlib.Path, FakeRelease],
) -> None:
    """The wheel arrives from PyPI, not from this run's rebuild."""
    work, fake = workspace
    seed_release(work, fake, WHEEL_GAP)
    completed = run_release_steps(workspace)
    assert completed.returncode == 0, completed.stderr
    assert (fake.github / WHEEL).read_bytes() == b"canonical-wheel", (
        "the release must hold PyPI's bytes, not the rebuild"
    )
    sent = uploads(fake)
    assert len(sent) == 1, sent
    assert "--clobber" not in sent[0], sent[0]


@requires_bash
def test_the_staged_set_is_the_gap_alone_when_provenance_is_already_attached(
    workspace: tuple[pathlib.Path, FakeRelease],
) -> None:
    """One upload carries the missing artefact, and no second bundle.

    The release already holds an attestation, so this run's bundle stays out of
    the upload: attaching it would make every re-run add an asset to a release
    that is otherwise complete.
    """
    work, fake = workspace
    seed_release(work, fake, WHEEL_GAP)
    earlier = (fake.github / EARLIER_BUNDLE).read_bytes()
    completed = run_release_steps(workspace)
    assert completed.returncode == 0, completed.stderr
    staged = work / "github-upload"
    assert {path.name for path in staged.iterdir()} == {WHEEL}, sorted(
        path.name for path in staged.iterdir()
    )
    assert (fake.github / EARLIER_BUNDLE).read_bytes() == earlier, (
        "an existing asset must be left alone"
    )


@requires_bash
def test_a_release_without_an_attestation_receives_one(
    workspace: tuple[pathlib.Path, FakeRelease],
) -> None:
    """The first run of a tag attaches its own bundle, and only that one.

    A release published with no attestation would give a consumer no way to
    check where its assets came from, so the run that finds none supplies one.
    The run's own bytes are canonical here, which is what lets its bundle
    cover them: this is a first release, so nothing was published before it.
    """
    work, fake = workspace
    seed_release(
        work,
        fake,
        Holding(pypi=(WHEEL, SDIST), github=(WHEEL, SDIST)),
        canonical_is_rebuild=True,
    )
    completed = run_release_steps(workspace)
    assert completed.returncode == 0, completed.stderr
    staged = work / "github-upload"
    assert {path.name for path in staged.iterdir()} == {BUNDLE}, sorted(
        path.name for path in staged.iterdir()
    )
    assert (fake.github / BUNDLE).read_bytes() == (
        work / "dist" / "attestations" / BUNDLE
    ).read_bytes(), sorted(path.name for path in fake.github.iterdir())


@requires_bash
def test_the_fetch_stage_names_every_file_it_needs_as_tsv(
    workspace: tuple[pathlib.Path, FakeRelease],
) -> None:
    """The TSV is the only channel from the stage step to the fetch loop."""
    work, fake = workspace
    seed_release(work, fake, WHEEL_GAP)
    completed = run_release_steps(workspace, RELEASE_STEPS[:3])
    assert completed.returncode == 0, completed.stderr
    fetched = (work / "pypi-fetch.tsv").read_text(encoding="utf-8")
    assert fetched.splitlines() == [
        f"{WHEEL}\thttps://files.example.test/packages/{WHEEL}"
    ], fetched


@requires_bash
def test_a_release_whose_bundle_covers_other_bytes_is_not_published(
    workspace: tuple[pathlib.Path, FakeRelease],
) -> None:
    """A bundle attached by an earlier run must still name today's assets.

    The Release can hold a bundle and still be unattested: if the assets were
    replaced, or a bundle was attached from a different run, the statement
    beside them says nothing about the bytes actually there. Publishing would
    present that as provenance, so the step refuses and the draft stays.

    Either refusal is a correct answer, and which one fires first depends on
    the order the checks run in: the verification loop finds no bundle that
    verifies against every asset, and the coverage step finds no verified
    statement naming them. Both leave the Release a draft, which is the
    property under test.
    """
    work, fake = workspace
    seed_release(work, fake, COMPLETE)
    write_bundle(fake.github, EARLIER_BUNDLE, {WHEEL: b"other", SDIST: b"other"})
    completed = run_release_steps(workspace, THROUGH_VERIFY)
    assert completed.returncode == 1, completed.stdout
    assert "no verified provenance bundle covering" in completed.stderr, (
        completed.stderr
    )
    assert published(fake)["draft"] is True, "the draft was published"


@requires_bash
def test_two_bundles_covering_one_asset_each_do_not_publish(
    workspace: tuple[pathlib.Path, FakeRelease],
) -> None:
    """Coverage is one statement's claim, not the union of two signatures.

    The Release can hold two bundles that each verify against one of its assets
    and neither of which names both. Read across them the Release looks
    covered: every asset has a statement, and every statement verified. It is
    not, because no signer said what publishing would present as said. The
    verify loop asks each bundle for the whole Release, so neither is admitted
    and the draft stays.
    """
    work, fake = workspace
    seed_release(work, fake, COMPLETE)
    (fake.github / EARLIER_BUNDLE).unlink()
    write_bundle(fake.github, "run6-wheel.sigstore.json", {WHEEL: b"canonical-wheel"})
    write_bundle(fake.github, "run6-sdist.sigstore.json", {SDIST: b"canonical-sdist"})
    completed = run_release_steps(workspace, THROUGH_VERIFY)
    assert completed.returncode == 1, completed.stdout
    assert "no verified provenance bundle covering" in completed.stderr, (
        completed.stderr
    )
    assert published(fake)["draft"] is True, "the draft was published"


@requires_bash
def test_a_bundle_whose_statement_was_edited_after_signing_does_not_publish(
    workspace: tuple[pathlib.Path, FakeRelease],
) -> None:
    """A bundle's subjects are checked against its signature, not merely read.

    Reading a statement out of the envelope says what its subject names, not
    that the signer named them. A Release holding a bundle whose subjects were
    edited to match its assets therefore passes a decode-only coverage check
    while carrying provenance for nothing. The verify step is what separates
    the two: without it this Release would publish.
    """
    work, fake = workspace
    seed_release(work, fake, COMPLETE)
    write_bundle(fake.github, EARLIER_BUNDLE, {WHEEL: b"other", SDIST: b"other"})
    _edit_after_signing(fake.github / EARLIER_BUNDLE)
    completed = run_release_steps(workspace, THROUGH_VERIFY)
    assert completed.returncode == 1, completed.stdout
    assert "no attestations found" in completed.stderr, completed.stderr
    assert published(fake)["draft"] is True, "the draft was published"


def _edit_after_signing(bundle: pathlib.Path) -> None:
    """Rewrite a bundle's subjects, leaving the signature that covered others.

    The signature is left exactly as it was while the payload is re-encoded
    over the Release's own assets, so the envelope is what a tampered bundle
    looks like: well-formed, and self-consistent in every field except the one
    that establishes who said it. Recomputing over the same statement it
    already carried would be no edit at all, which is why the bundle first
    attests other bytes.
    """
    document = json.loads(bundle.read_text(encoding="utf-8"))
    envelope = document["dsseEnvelope"]
    signature = envelope["signatures"][0]["sig"]
    envelope["payload"] = base64.b64encode(
        json.dumps(subjects_of(PUBLISHED_PAYLOADS)).encode("utf-8")
    ).decode("ascii")
    assert envelope["signatures"][0]["sig"] == signature, "the signature was rewritten"
    bundle.write_text(json.dumps(document), encoding="utf-8")


@requires_bash
def test_a_destination_that_disagrees_keeps_the_release_a_draft(
    workspace: tuple[pathlib.Path, FakeRelease],
) -> None:
    """The comparison is the gate on publishing, and it does not pass."""
    work, fake = workspace
    seed_release(work, fake, WHEEL_GAP)
    (fake.github / WHEEL).write_bytes(b"someone-else's-wheel")
    completed = run_release_steps(workspace)
    assert completed.returncode == 1, completed.stdout
    assert WHEEL in completed.stderr, completed.stderr
    assert published(fake)["draft"] is True, "the draft was published"


@requires_bash
def test_the_verification_runs_before_the_release_is_published(
    workspace: tuple[pathlib.Path, FakeRelease],
) -> None:
    """A release still a draft while the check is running cannot go out early."""
    work, fake = workspace
    seed_release(work, fake, COMPLETE)
    record_state(fake, draft=True, prerelease=False)
    completed = run_release_steps(workspace, THROUGH_VERIFY)
    assert completed.returncode == 0, completed.stderr
    assert published(fake) == {"draft": True, "prerelease": False}, published(fake)


@requires_bash
@pytest.mark.parametrize(("prerelease", "expected"), [("true", True), ("false", False)])
def test_the_release_takes_the_tag_s_prerelease_state(
    prerelease: str,
    workspace: tuple[pathlib.Path, FakeRelease],
    *,
    expected: bool,
) -> None:
    """``v0.2.0rc1`` must not be published as a final release."""
    work, fake = workspace
    record_state(fake, draft=True, prerelease=not expected)
    completed = run_bash(
        typ.cast(
            "str", step(publish_release_job(), "Publish the GitHub Release")["run"]
        ),
        work,
        environ=fake.environ(IS_PRERELEASE=prerelease),
    )
    assert completed.returncode == 0, completed.stderr
    assert published(fake) == {"draft": False, "prerelease": expected}, published(fake)


def test_every_scripted_step_is_run_by_this_module() -> None:
    """A step added to the job without a contract here is caught."""
    steps = publish_release_job().get("steps")
    assert isinstance(steps, list), "steps must be a list"
    scripted = tuple(
        str(entry["name"])
        for entry in steps
        if isinstance(entry, dict) and isinstance(entry.get("run"), str)
    )
    assert scripted == RELEASE_STEPS, scripted
