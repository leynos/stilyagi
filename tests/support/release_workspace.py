"""The workspace and scripted destinations a publishing step runs against.

A release step is a shell script that reaches the network only through
``curl`` and ``gh``, so a test of one runs the workflow's own script in a
workspace that holds this repository's ``scripts/`` and a pair of state
directories standing in for PyPI and the GitHub Release. This module supplies
that workspace, the step sequences each job's scripted steps form, and the
seed writing that gives a test the destinations it wants.

The step names are data about ``release.yml`` rather than about any one test:
several contract modules run the same job, so a sequence is stated once here
and read by each. What a test asserts about the run stays in the test.
"""

import typing as typ

from tests.support.release_fakes import FakeRelease
from tests.support.release_workflow import (
    RELEASE_WORKFLOW,
    step_script,
    workflow_job,
)
from tests.support.workflow_documents import WORKFLOWS_DIRECTORY
from tests.support.workflows import load_workflow

if typ.TYPE_CHECKING:
    import pathlib

    from tests.support.workflows import WorkflowDocument

#: The x86_64 wheel the scripted runs build.
WHEEL: typ.Final = "stilyagi-0.2.0-cp314-cp314-manylinux_2_28_x86_64.whl"

#: The one source distribution the scripted runs build.
SDIST: typ.Final = "stilyagi-0.2.0.tar.gz"

#: The run-unique bundle name ``attest`` stages.
BUNDLE: typ.Final = "stilyagi-v0.2.0-run7-1.sigstore.json"

#: ``draft-release``'s scripted steps, in workflow order. Each publishes into
#: the directory the one before it filled, so they are a sequence, not a set.
DRAFT_STEPS: typ.Final = (
    "Create or reuse the draft release",
    "Snapshot the release assets",
    "Verify the carried assets' provenance",
)

#: ``publish-pypi``'s scripted steps, in workflow order.
PUBLISH_STEPS: typ.Final = ("Fetch the PyPI index", "Skip artefacts already on PyPI")

#: The step that hands the upload set to PyPI. It is a ``uses:`` step carrying
#: no script, so it is listed only where the job's own gate is the subject: a
#: gate that wrongly let it run fails on the missing script rather than
#: passing unnoticed.
PYPI_UPLOAD_STEP: typ.Final = "Publish to PyPI"

#: ``publish-pypi``'s steps with that gate in the sequence, for a run whose
#: upload is expected to be skipped.
PUBLISH_WITH_GATE_STEPS: typ.Final = (*PUBLISH_STEPS, PYPI_UPLOAD_STEP)

#: ``publish-release``'s steps up to, and including, the upload. The upload
#: step carries a script that ``gh release upload`` would run, so it belongs in
#: the sequence: an assertion that no upload was made has to cover the step
#: that would make one. Its gate reads ``steps.stage.outputs.pending``, which
#: ``run_job_steps`` honours, so a refusal at staging skips it exactly as the
#: runner does.
RELEASE_DECISION_STEPS: typ.Final = (
    "Fetch the PyPI index",
    "List the release assets",
    "Stage the assets the release lacks",
    "Upload the assets the release lacks",
)

#: What one scripted run consists of: the workspace, its fake destinations,
#: and the directory the build's artefacts are staged in.
type Workspace = tuple[pathlib.Path, FakeRelease, pathlib.Path]


def release_document() -> WorkflowDocument:
    """Return the release workflow document.

    Returns
    -------
    WorkflowDocument
        ``release.yml``, parsed by the same reader every other contract uses.
    """
    return load_workflow(
        (WORKFLOWS_DIRECTORY / RELEASE_WORKFLOW).read_text(encoding="utf-8")
    )


def release_script(job: str, step: str) -> str:
    """Return one named step's script from the release workflow's job.

    Parameters
    ----------
    job
        The job identifier holding the step.
    step
        The step's ``name``.

    Returns
    -------
    str
        The step's ``run`` script.
    """
    return step_script(workflow_job(release_document(), job), step)


def stage_rebuild(publish: pathlib.Path) -> None:
    """Write the rebuilt bytes the build jobs hand to a publishing job.

    Each publishing job downloads ``release-dist`` into its own workspace, so
    this is written again before each job: ``publish-pypi`` deletes every name
    it skips from ``dist/publish``, and the job after it starts from the
    artefact rather than from that emptied directory.

    Parameters
    ----------
    publish
        The ``dist/publish`` directory to write the rebuild into.
    """
    (publish / WHEEL).write_bytes(b"rebuilt-wheel")
    (publish / SDIST).write_bytes(b"rebuilt-sdist")


def seed_release(
    publish: pathlib.Path,
    fake: FakeRelease,
    *,
    pypi: tuple[str, ...] = (),
    github: tuple[str, ...] = (),
) -> None:
    """Write a rebuilt artefact set and the two destinations' holdings.

    Whatever either destination holds is attested, as it would be in practice:
    a file reaches PyPI or the Release only through a run that signed it.

    Parameters
    ----------
    publish
        The ``dist/publish`` directory to write the rebuild into.
    fake
        The scripted destinations to fill.
    pypi
        The names PyPI already holds.
    github
        The names the GitHub Release already holds.
    """
    stage_rebuild(publish)
    canonical = {WHEEL: b"canonical-wheel", SDIST: b"canonical-sdist"}
    fake.attest(canonical)
    for directory, names in ((fake.pypi, pypi), (fake.github, github)):
        for name in names:
            (directory / name).write_bytes(canonical[name])


__all__ = [
    "BUNDLE",
    "DRAFT_STEPS",
    "PUBLISH_STEPS",
    "PUBLISH_WITH_GATE_STEPS",
    "PYPI_UPLOAD_STEP",
    "RELEASE_DECISION_STEPS",
    "SDIST",
    "WHEEL",
    "Workspace",
    "release_document",
    "release_script",
    "seed_release",
    "stage_rebuild",
]
