"""Run one tag's whole release, then run the same tag again.

A tag's release is three jobs in sequence. ``draft-release`` creates or reuses
the Release and verifies what it already carries, ``publish-pypi`` decides the
upload set and sends it to PyPI, and ``publish-release`` fills the Release from
PyPI's bytes and publishes it. Every other release module runs one of those
jobs; none runs the three in order over one tag, and the tag is the unit issue
#229 states its requirement in.

So this module drives the workflow's own scripts for all three jobs, in the
workflow's order, against a scripted Release and PyPI. Each job is given its
own output file, as a runner gives it. The PyPI upload is a ``uses:`` step
carrying no script, so the harness cannot run it; the test performs the
transfer it would make, from exactly the files the staging step left behind.

The re-run stages deliberately different bytes. A rebuild is never
byte-identical to the build before it, so a second run that took its own bytes
rather than the destinations' is visible here. Staging one payload twice would
hide the defect these tests exist for.
"""

import dataclasses as dc
import typing as typ

from tests.support.release_assets_fixtures import write_bundle
from tests.support.release_github_workspace import (
    SDIST,
    WHEEL,
    published,
    record_state,
)
from tests.support.release_publish_release import RELEASE_STEPS
from tests.support.release_steps import requires_bash, run_job_steps
from tests.support.release_workflow import github_output, workflow_job
from tests.support.release_workspace import (
    BUNDLE,
    DRAFT_STEPS,
    PUBLISH_STEPS,
    Workspace,
    release_document,
)

pytest_plugins = ("tests.support.release_workspace_fixtures",)

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    import pathlib
    import subprocess

    from tests.support.release_fakes import FakeRelease

#: The bytes one build of the tag produces. The two runs differ so that a step
#: taking the rebuild where it should take a destination's bytes is caught.
FIRST: typ.Final = {WHEEL: b"first-wheel", SDIST: b"first-sdist"}
SECOND: typ.Final = {WHEEL: b"second-wheel", SDIST: b"second-sdist"}


#: One job of the tag's release: what to run, and where its outputs go.
@dc.dataclass(frozen=True, slots=True)
class Job:
    """A job of the release workflow and the environment its steps read."""

    name: str
    steps: tuple[str, ...]
    output: str
    env: cabc.Mapping[str, str] = dc.field(default_factory=dict)


#: The second run's bundle. ``attest`` names each run's bundle after that run,
#: so a second run that attached its own would add an asset of its own rather
#: than collide with the first and be refused.
SECOND_BUNDLE: typ.Final = "stilyagi-v0.2.0-run8-1.sigstore.json"


def _stage(work: pathlib.Path, payloads: dict[str, bytes], bundle: str) -> None:
    """Replace what this run downloads with a build of its own.

    Each job downloads the build's artefacts rather than inheriting the
    directory the job before it worked in, so this writes both directories
    from scratch: the artefacts the build produced and the one bundle
    ``attest`` signed over them. Clearing first matters on a re-run, where the
    previous run's files would otherwise still be there to be sent.

    Parameters
    ----------
    work
        The job's working directory, holding ``dist``.
    payloads
        Each artefact name and the bytes this build produced.
    bundle
        The run-unique bundle name this run's ``attest`` step uploaded.
    """
    publish = work / "dist" / "publish"
    attestations = work / "dist" / "attestations"
    for directory in (publish, attestations):
        for path in directory.glob("*") if directory.exists() else ():
            path.unlink()
        directory.mkdir(parents=True, exist_ok=True)
    for name, payload in payloads.items():
        (publish / name).write_bytes(payload)
    write_bundle(attestations, bundle, payloads)


def _hold(fake: FakeRelease, pypi: dict[str, bytes], github: dict[str, bytes]) -> None:
    """Place each destination's holdings and attest the bytes each one holds.

    A file reaches PyPI or the Release only through a run that signed it, so
    the attestation store answers for these bytes however they arrived.
    """
    fake.attest({**pypi, **github})
    for directory, payloads in ((fake.pypi, pypi), (fake.github, github)):
        for name, payload in payloads.items():
            (directory / name).write_bytes(payload)


def _run(
    work: pathlib.Path, fake: FakeRelease, job: Job
) -> subprocess.CompletedProcess[str]:
    """Run one job's scripted steps against the fakes.

    Each job gets its own ``GITHUB_OUTPUT`` file, as a runner gives it, so a
    later job cannot overwrite the outputs an earlier one is read for. The
    job's ``env`` carries the entries GitHub resolves from an earlier job's
    outputs before the step runs.

    Parameters
    ----------
    work
        The job's working directory.
    fake
        The scripted destinations the steps reach.
    job
        The job to run.

    Returns
    -------
    subprocess.CompletedProcess[str]
        The first step that failed, or the last step to run when all passed.
    """
    return run_job_steps(
        workflow_job(release_document(), job.name),
        job.steps,
        work,
        environ=fake.environ(
            GITHUB_OUTPUT=str(work / job.output),
            **dict(job.env),
        ),
    )


def _publish(work: pathlib.Path, fake: FakeRelease) -> subprocess.CompletedProcess[str]:
    """Run ``draft-release`` and ``publish-pypi``, then give PyPI its upload.

    The upload is performed from ``dist/publish`` after the staging step, which
    is what ``pypa/gh-action-pypi-publish`` would send. A name the staging step
    dropped is therefore not published, and a name it retained is.

    Returns
    -------
    subprocess.CompletedProcess[str]
        The first step that failed, or the staging step when both passed.
    """
    completed = _run(work, fake, Job("draft-release", DRAFT_STEPS, "out-draft"))
    if completed.returncode != 0:
        return completed
    completed = _run(work, fake, Job("publish-pypi", PUBLISH_STEPS, "out-pypi"))
    if completed.returncode != 0:
        return completed
    publish = work / "dist" / "publish"
    for path in sorted(publish.iterdir()):
        (fake.pypi / path.name).write_bytes(path.read_bytes())
    return completed


def _finish(work: pathlib.Path, fake: FakeRelease) -> subprocess.CompletedProcess[str]:
    """Run ``publish-release`` over the artefacts its own job downloads.

    ``github-upload`` is emptied first: the step that stages the upload set
    writes into it, and the step that uploads sends everything in it, so a job
    starting from a fresh workspace is what keeps one run's set out of the
    next run's upload. ``check-version`` reports a final release for the
    scripted tag, so that is the job-level value the publication step reads.

    Returns
    -------
    subprocess.CompletedProcess[str]
        The first step that failed, or the last step to run when all passed.
    """
    staging = work / "github-upload"
    if staging.exists():
        for path in staging.glob("*"):
            path.unlink()
    return _run(
        work,
        fake,
        Job(
            "publish-release", RELEASE_STEPS, "out-release", {"IS_PRERELEASE": "false"}
        ),
    )


def _release_tag(
    work: pathlib.Path, fake: FakeRelease
) -> tuple[subprocess.CompletedProcess[str], subprocess.CompletedProcess[str]]:
    """Run the tag once, as a first release of bytes neither destination holds.

    Returns
    -------
    tuple[subprocess.CompletedProcess[str], subprocess.CompletedProcess[str]]
        The publishing half's result and the finishing half's, so a test can
        report which of the two failed.
    """
    record_state(fake, draft=True, prerelease=False)
    fake.attest(FIRST)
    _stage(work, FIRST, BUNDLE)
    sent = _publish(work, fake)
    if sent.returncode != 0:
        return sent, sent
    # A publishing job starts from the artefact rather than from the directory
    # the job before it emptied, so the rebuild is staged again for the job.
    _stage(work, FIRST, BUNDLE)
    return sent, _finish(work, fake)


@requires_bash
def test_one_tag_run_leaves_both_destinations_holding_the_same_bytes(
    workspace: Workspace,
) -> None:
    """The tag's own acceptance: PyPI and the Release agree, and it publishes.

    This is issue #229's first requirement stated at the level it is written:
    one tag, every artefact on PyPI, the same bytes on the Release, the
    provenance bundle beside them, and the Release no longer a draft. A job
    that dropped a name or left the Release unpublished fails here even though
    each job's own contract passes.

    The byte comparison is not sharp in this test: on a first release the
    rebuild *is* what PyPI publishes, so taking the rebuild where a
    destination's bytes belong would agree with itself. It is sharp in the
    interrupted-tag test, where the rebuild and the destinations' bytes
    differ.
    """
    work, fake, _publish_dir = workspace
    sent, finished = _release_tag(work, fake)
    assert sent.returncode == 0, sent.stderr
    assert finished.returncode == 0, finished.stderr
    assert github_output(work / "out-pypi")["remaining"] == "true", (
        "a first release leaves both artefacts for PyPI"
    )
    assert {path.name for path in fake.pypi.iterdir()} == {WHEEL, SDIST}, sorted(
        path.name for path in fake.pypi.iterdir()
    )
    assert {path.name for path in fake.github.iterdir()} == {
        WHEEL,
        SDIST,
        BUNDLE,
    }, sorted(path.name for path in fake.github.iterdir())
    for name in (WHEEL, SDIST):
        assert (fake.pypi / name).read_bytes() == (fake.github / name).read_bytes(), (
            f"the two destinations disagree about {name}"
        )
    assert published(fake) == {"draft": False, "prerelease": False}, published(fake)


@requires_bash
def test_a_second_run_of_the_tag_uploads_nothing_to_either_destination(
    workspace: Workspace,
) -> None:
    """Issue #229's second requirement: the tag re-runs, and nothing is sent.

    The second build's bytes differ from everything already published, so a
    step that decided from its own rebuild rather than from the destinations
    would try to send them. It must not: the run finishes successfully with an
    empty upload set, PyPI keeps the bytes it published, and the Release is not
    given a second asset or a second bundle.
    """
    work, fake, _publish_dir = workspace
    _sent, first = _release_tag(work, fake)
    assert first.returncode == 0, first.stderr
    held = {path.name: path.read_bytes() for path in fake.github.iterdir()}
    on_pypi = {path.name: path.read_bytes() for path in fake.pypi.iterdir()}

    _stage(work, SECOND, SECOND_BUNDLE)
    sent = _publish(work, fake)
    assert sent.returncode == 0, sent.stderr
    assert github_output(work / "out-pypi")["remaining"] == "false", (
        "a re-run must leave nothing for PyPI"
    )
    assert not any((work / "dist" / "publish").iterdir()), sorted(
        path.name for path in (work / "dist" / "publish").iterdir()
    )
    _stage(work, SECOND, SECOND_BUNDLE)
    finished = _finish(work, fake)
    assert finished.returncode == 0, finished.stderr
    assert not any((work / "github-upload").iterdir()), sorted(
        path.name for path in (work / "github-upload").iterdir()
    )
    assert {path.name: path.read_bytes() for path in fake.github.iterdir()} == held, (
        "a re-run must not add to or replace the Release"
    )
    assert {path.name: path.read_bytes() for path in fake.pypi.iterdir()} == on_pypi, (
        "a re-run must not replace the bytes PyPI published"
    )
    assert published(fake) == {"draft": False, "prerelease": False}, published(fake)


@requires_bash
def test_an_interrupted_tag_reaches_pypi_and_then_fails_at_the_release(
    workspace: Workspace,
) -> None:
    """A tag stopped between jobs is carried on, and stops where it cannot heal.

    PyPI holding the sdist while the Release holds the wheel is what an
    interrupted run leaves. ``publish-pypi`` cannot tell that from the
    legitimate sequence, so it completes and sends the Release's wheel; the
    release is then mixed rather than healed. ``publish-release`` refuses it:
    the Release holds no bundle covering the sdist it lacks, and a Release
    asset cannot be replaced, so attaching the rebuild there would record
    bytes no run signed over.

    This asserts the limit the ADR records rather than approving it. If
    staging ever distinguishes the two states, this test fails and the ADR,
    which says the recovery mechanism is unimplemented, needs revising with it.
    """
    work, fake, _publish_dir = workspace
    record_state(fake, draft=True, prerelease=False)
    _hold(fake, {SDIST: b"published-sdist"}, {WHEEL: b"released-wheel"})
    _stage(work, SECOND, SECOND_BUNDLE)

    sent = _publish(work, fake)
    assert sent.returncode == 0, sent.stderr
    assert (fake.pypi / WHEEL).read_bytes() == b"released-wheel", (
        "the carried wheel must reach PyPI as the Release's bytes"
    )

    _stage(work, SECOND, SECOND_BUNDLE)
    finished = _finish(work, fake)
    assert finished.returncode == 1, finished.stdout
    assert "provenance bundle" in finished.stderr, finished.stderr
    assert SDIST not in {path.name for path in fake.github.iterdir()}, sorted(
        path.name for path in fake.github.iterdir()
    )
    assert published(fake)["draft"] is True, "a mixed release must not be published"
