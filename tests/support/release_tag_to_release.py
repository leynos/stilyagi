"""The harness that runs one tag's three release jobs in sequence.

A tag's release is ``draft-release``, then ``publish-pypi``, then
``publish-release``. The other support modules each drive one of those jobs;
this one spans all three, runs them in the workflow's order against one
workspace, and gives the ``uses:`` upload step the transfer it would make.

The division is by role. What lives here is mechanism: laying out the
workspace a tag's build leaves, running a job's own scripted steps, and
handing PyPI the files the staging step left. What a test asserts about the
result stays in the test module, so a change to the harness cannot quietly
restate the requirement it is meant to check.
"""

import dataclasses as dc
import typing as typ

from tests.support.release_assets_fixtures import write_bundle
from tests.support.release_publish_release import RELEASE_STEPS
from tests.support.release_steps import run_job_steps, should_run
from tests.support.release_workflow import step, workflow_job
from tests.support.release_workspace import (
    BUNDLE,
    DRAFT_STEPS,
    PUBLISH_STEPS,
    PYPI_UPLOAD_STEP,
    SDIST,
    WHEEL,
    release_document,
)

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    import pathlib
    import subprocess

    from tests.support.release_fakes import FakeRelease

#: The bytes one build of the tag produces. The two runs differ so that a step
#: taking the rebuild where it should take a destination's bytes is caught.
FIRST: typ.Final = {WHEEL: b"first-wheel", SDIST: b"first-sdist"}
SECOND: typ.Final = {WHEEL: b"second-wheel", SDIST: b"second-sdist"}

#: The second run's bundle. ``attest`` names each run's bundle after that run,
#: so a second run that attached its own would add an asset of its own rather
#: than collide with the first and be refused.
SECOND_BUNDLE: typ.Final = "stilyagi-v0.2.0-run8-1.sigstore.json"


@dc.dataclass(frozen=True, slots=True)
class Job:
    """One job of the release workflow and the environment its steps read."""

    name: str
    steps: tuple[str, ...]
    output: str
    env: cabc.Mapping[str, str] = dc.field(default_factory=dict)


@dc.dataclass(frozen=True, slots=True)
class Tag:
    """The state one run of a tag starts from.

    ``creates`` and ``prerelease`` are one subject: both are facts about the
    Release this run is for, which is why they travel together rather than as
    two parameters every caller must remember to pass.
    """

    #: Whether this run creates the tag's Release. The fake ``gh`` answers
    #: ``release view`` successfully whatever its state, so an absent Release
    #: is scripted as one it cannot find; that is the only answer the create
    #: step acts on. A run that reuses an existing Release leaves it be.
    creates: bool = False

    #: The value ``check-version`` derives from the tag. The create step marks
    #: the Release with it, and the publication step repeats it.
    prerelease: str = "false"


#: The default a caller gets when it names no tag: an existing final Release,
#: which is what every run after the first one starts from.
EXISTING: typ.Final = Tag()

#: The state a tag's first run starts from, before it has made its Release.
NEW_RELEASE: typ.Final = Tag(creates=True)


def stage_build(
    work: pathlib.Path, fake: FakeRelease, payloads: dict[str, bytes], bundle: str
) -> None:
    """Replace what this run downloads with a build of its own.

    Each job downloads the build's artefacts rather than inheriting the
    directory the job before it worked in, so this writes both directories
    from scratch: the artefacts the build produced and the one bundle
    ``attest`` signed over them. Clearing first matters on a re-run, where the
    previous run's files would otherwise still be there to be sent.

    ``actions/attest-build-provenance`` records its signature in the
    repository's attestation store as well as uploading the bundle, so the
    store receives this build's bytes here. That is what lets a later step
    establish where a file came from by digest.

    Parameters
    ----------
    work
        The job's working directory, holding ``dist``.
    fake
        The scripted destinations, whose attestation store is written.
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
    fake.attest(payloads)


def hold(fake: FakeRelease, pypi: dict[str, bytes], github: dict[str, bytes]) -> None:
    """Place each destination's holdings and attest the bytes each one holds.

    A file reaches PyPI or the Release only through a run that signed it, so
    the attestation store answers for these bytes however they arrived.

    Parameters
    ----------
    fake
        The scripted destinations to fill.
    pypi
        The name and bytes PyPI already holds.
    github
        The name and bytes the tag's Release already holds.
    """
    fake.attest({**pypi, **github})
    for directory, payloads in ((fake.pypi, pypi), (fake.github, github)):
        for name, payload in payloads.items():
            (directory / name).write_bytes(payload)


def holdings(fake: FakeRelease) -> dict[str, dict[str, bytes]]:
    """Read each destination as a map from asset name to bytes.

    Two reads taken at different points in a run compare directly, which is
    how a test states that a re-run changed nothing. Reading rather than
    listing means a file that was replaced is caught, not only one that was
    added.

    Parameters
    ----------
    fake
        The scripted destinations to read.

    Returns
    -------
    dict[str, dict[str, bytes]]
        Each destination's asset names and their bytes.
    """
    return {
        "pypi": {path.name: path.read_bytes() for path in fake.pypi.iterdir()},
        "github": {path.name: path.read_bytes() for path in fake.github.iterdir()},
    }


def run_job(
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


@dc.dataclass(frozen=True, slots=True)
class HandOff:
    """The files ``publish-pypi`` leaves for the upload step, and their output."""

    publish: pathlib.Path
    output: pathlib.Path


def transfer_to_pypi(
    hand_off: HandOff,
    fake: FakeRelease,
    *,
    omit: tuple[str, ...] = (),
) -> tuple[str, ...]:
    """Make the transfer ``pypa/gh-action-pypi-publish`` would make.

    The step is a ``uses:`` action carrying no ``run:`` script, so it cannot be
    executed here; what it would send is the content of ``dist/publish`` after
    the staging step, and that directory is already the staging decision.

    Its ``if:`` is read from the workflow and honoured as well. That is
    deliberate redundancy rather than the thing under test: ``stage_pypi``
    leaves the directory empty exactly when it reports nothing remains, so no
    state the workflow can reach tells the two apart. The gate is what stops a
    skipped upload if that invariant ever loosens;
    ``test_the_upload_step_is_gated_on_the_staging_output`` holds it to the
    workflow's own expression.

    Parameters
    ----------
    hand_off
        The staged directory and the job output that decides the upload.
    fake
        The scripted PyPI destination the files are copied into.
    omit
        Names to leave behind, which is how an interrupted upload is stated:
        the action sends what it can, and a failure part-way leaves the rest.

    Returns
    -------
    tuple[str, ...]
        The names the transfer sent, sorted.
    """
    gate = step(workflow_job(release_document(), "publish-pypi"), PYPI_UPLOAD_STEP)
    if not should_run(gate.get("if"), hand_off.output):
        return ()
    sent = tuple(
        sorted(
            path.name for path in hand_off.publish.iterdir() if path.name not in omit
        )
    )
    for name in sent:
        (fake.pypi / name).write_bytes((hand_off.publish / name).read_bytes())
    return sent


def publish_tag(
    work: pathlib.Path,
    fake: FakeRelease,
    *,
    omit: tuple[str, ...] = (),
    tag: Tag = EXISTING,
) -> tuple[subprocess.CompletedProcess[str], tuple[str, ...]]:
    """Run ``draft-release`` and ``publish-pypi``, then give PyPI its upload.

    Parameters
    ----------
    work
        The job's working directory.
    fake
        The scripted destinations.
    omit
        Names the PyPI transfer leaves behind, stating an interrupted upload.
    tag
        The Release's state before this run, and the value ``check-version``
        derives from the tag.

    Returns
    -------
    tuple[subprocess.CompletedProcess[str], tuple[str, ...]]
        The first step that failed or the staging step when both passed, and
        the names the PyPI transfer sent.
    """
    if tag.creates:
        # The absence is true only until this step makes the Release, so it is
        # scripted for this step alone: the snapshot after it must see the
        # Release the create step has just made, as it would on a runner.
        completed = run_job(
            work,
            fake,
            Job(
                "draft-release",
                DRAFT_STEPS[:1],
                "out-draft",
                {
                    "IS_PRERELEASE": tag.prerelease,
                    "FAKE_RELEASE_VIEW_STATUS": "1",
                },
            ),
        )
        if completed.returncode != 0:
            return completed, ()
        remaining = DRAFT_STEPS[1:]
    else:
        remaining = DRAFT_STEPS
    completed = run_job(
        work,
        fake,
        Job(
            "draft-release",
            remaining,
            "out-draft",
            {"IS_PRERELEASE": tag.prerelease},
        ),
    )
    if completed.returncode != 0:
        return completed, ()
    completed = run_job(work, fake, Job("publish-pypi", PUBLISH_STEPS, "out-pypi"))
    if completed.returncode != 0:
        return completed, ()
    hand_off = HandOff(publish=work / "dist" / "publish", output=work / "out-pypi")
    return completed, transfer_to_pypi(hand_off, fake, omit=omit)


def finish_tag(
    work: pathlib.Path, fake: FakeRelease, *, tag: Tag = EXISTING
) -> subprocess.CompletedProcess[str]:
    """Run ``publish-release`` over the artefacts its own job downloads.

    ``github-upload`` is emptied first: the step that stages the upload set
    writes into it, and the step that uploads sends everything in it, so a job
    starting from a fresh workspace is what keeps one run's set out of the
    next run's upload. ``check-version`` hands the tag's pre-release result to
    the publication step through the job's ``env:``, which ``tag`` carries.

    Parameters
    ----------
    work
        The job's working directory.
    fake
        The scripted destinations the steps reach.
    tag
        The Release this run is for, whose pre-release value the workflow's
        own ``check-version`` would have derived.

    Returns
    -------
    subprocess.CompletedProcess[str]
        The first step that failed, or the last step to run when all passed.
    """
    staging = work / "github-upload"
    if staging.exists():
        for path in staging.glob("*"):
            path.unlink()
    return run_job(
        work,
        fake,
        Job(
            "publish-release",
            RELEASE_STEPS,
            "out-release",
            {"IS_PRERELEASE": tag.prerelease},
        ),
    )


__all__ = [
    "BUNDLE",
    "EXISTING",
    "FIRST",
    "NEW_RELEASE",
    "SECOND",
    "SECOND_BUNDLE",
    "HandOff",
    "Job",
    "Tag",
    "finish_tag",
    "hold",
    "holdings",
    "publish_tag",
    "run_job",
    "stage_build",
    "transfer_to_pypi",
]
