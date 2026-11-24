"""Run ``publish-release``'s provenance checks against a damaged bundle.

The bundle beside a Release's assets is the provenance a consumer checks, and
the job asks two different questions of it: whether the signature holds, and
whether one signed statement names every asset. ``gh release upload`` has no
``--clobber`` and a Release asset cannot be replaced, so a bundle that fails
either question must be refused before it becomes an asset rather than after.

Each test damages a bundle in exactly one respect and asserts which refusal
fires. That isolates the two questions from the order the steps happen to run
in: a test that broke both at once would pass even if only one of the checks
existed.
"""

import typing as typ

import pytest

from tests.support.release_assets_fixtures import write_bundle
from tests.support.release_bundle_tampering import (
    break_bundle_signature,
    edit_bundle_subjects,
)
from tests.support.release_github_workspace import (
    BUNDLE,
    EARLIER_BUNDLE,
    PUBLISHED_PAYLOADS,
    SDIST,
    WHEEL,
    Holding,
    published,
    seed_release,
    uploads,
)
from tests.support.release_publish_release import (
    COMPLETE,
    THROUGH_VERIFY,
    release_workspace,
    run_release_steps,
)
from tests.support.release_steps import requires_bash

if typ.TYPE_CHECKING:
    import pathlib

    from tests.support.release_fakes import FakeRelease


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
def test_partial_bundles_beside_a_tampered_covering_one_do_not_publish(
    workspace: tuple[pathlib.Path, FakeRelease],
) -> None:
    """Neither verification nor coverage may be satisfied by combining records.

    This is the case the two rules exist for. Two bundles verify, one against
    each asset, and a third decodes as naming both because its statement was
    edited after signing. Asking per asset admits all three, and asking
    coverage across them accepts the third's claim, so the Release would
    publish carrying provenance no single signer gave. Asked of one verified
    statement, it does not: the partial bundles do not cover the Release and
    the covering one does not verify.
    """
    work, fake = workspace
    seed_release(work, fake, COMPLETE)
    (fake.github / EARLIER_BUNDLE).unlink()
    write_bundle(fake.github, "run6-wheel.sigstore.json", {WHEEL: b"canonical-wheel"})
    write_bundle(fake.github, "run6-sdist.sigstore.json", {SDIST: b"canonical-sdist"})
    tampered = write_bundle(
        fake.github, "run6-both.sigstore.json", {WHEEL: b"other", SDIST: b"other"}
    )
    edit_bundle_subjects(tampered, PUBLISHED_PAYLOADS)
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
    edit_bundle_subjects(fake.github / EARLIER_BUNDLE, PUBLISHED_PAYLOADS)
    completed = run_release_steps(workspace, THROUGH_VERIFY)
    assert completed.returncode == 1, completed.stdout
    assert "no attestations found" in completed.stderr, completed.stderr
    assert published(fake)["draft"] is True, "the draft was published"


@requires_bash
def test_a_staged_bundle_that_does_not_verify_is_never_uploaded(
    workspace: tuple[pathlib.Path, FakeRelease],
) -> None:
    """A Release asset cannot be replaced, so the bad bundle stops before one exists.

    The staged bundle becomes a Release asset, and ``gh release upload`` has no
    ``--clobber``: once a bundle is attached, a re-run finds the Release
    already holding one, stages no replacement, and the failing check runs
    again over the same bytes. A bundle whose statement names the right
    digests but whose signature does not hold would therefore wedge the tag
    permanently, not merely fail once.

    The Release here holds every artefact and no bundle, which is the case
    that stages one; only that bundle's signature is broken. The run must stop
    before ``gh release upload``, leaving the Release a draft and still
    holding no bundle.
    """
    work, fake = workspace
    seed_release(
        work,
        fake,
        Holding(pypi=(WHEEL, SDIST), github=(WHEEL, SDIST)),
        canonical_is_rebuild=True,
    )
    break_bundle_signature(work / "dist" / "attestations" / BUNDLE)
    # The whole sequence, upload and publication included. `run_job_steps`
    # stops at the first failing step, so the upload is in the list and is
    # reached only if the provenance check lets the run through: that is what
    # makes "no upload" evidence rather than an artefact of the step list.
    completed = run_release_steps(workspace)
    assert completed.returncode == 1, completed.stdout
    assert "no attestations found" in completed.stderr, completed.stderr
    assert not uploads(fake), "a bundle that does not verify must not be uploaded"
    assert not (fake.github / BUNDLE).exists(), "the bad bundle reached the Release"
    assert published(fake)["draft"] is True, "the draft was published"
