"""The harness for running ``publish-release``'s scripted steps.

``publish-release`` is the job that finishes a tag's release: it fills a gap
from PyPI's bytes, checks the Release's own attestation still covers what it
holds, compares the two destinations, and only then edits the draft to
published. Its steps consume what the earlier ones wrote, so exercising it
means laying out the workspace its own actions would leave and running the
steps in order.

That harness lives here rather than beside the tests because it has two
callers: the contract tests that assert what a second run of a tag must not
redo, and the tests for the individual checks the job performs. Both need the
same scripted destinations, the same step order, and the same artefact bytes,
and each of those has to stay in one place or a change to the workflow would
be reflected in one suite and not the other.
"""

import hashlib
import typing as typ

from tests.support.release_fakes import FakeRelease, fake_release
from tests.support.release_github_workspace import (
    BUNDLE,
    EARLIER_BUNDLE,
    SDIST,
    WHEEL,
    Holding,
    record_state,
)
from tests.support.release_steps import run_job_steps
from tests.support.release_workflow import (
    RELEASE_WORKFLOW,
    REPOSITORY_ROOT,
    link_scripts,
    workflow_job,
)
from tests.support.workflow_documents import WORKFLOWS_DIRECTORY
from tests.support.workflows import load_workflow

if typ.TYPE_CHECKING:
    import pathlib
    import subprocess

    from tests.support.workflows import WorkflowDocument

#: Every ``publish-release`` step that carries a script, in workflow order. The
#: checkout and download actions are represented by the directories the fixture
#: lays out, exactly as those actions would leave them.
RELEASE_STEPS: typ.Final = (
    "Fetch the PyPI index",
    "List the release assets",
    "Stage the assets the release lacks",
    "Check the fetched PyPI bytes",
    "Verify the upload set's provenance",
    "Upload the assets the release lacks",
    "Check the Release's assets are attested",
    "Check both destinations hold the same bytes",
    "Publish the GitHub Release",
)

#: The steps up to and including the comparison, but not the publication.
THROUGH_VERIFY: typ.Final = RELEASE_STEPS[:-1]

#: Both destinations holding what a completed earlier run left them.
COMPLETE: typ.Final = Holding(
    pypi=(WHEEL, SDIST), github=(WHEEL, SDIST, EARLIER_BUNDLE)
)
#: PyPI complete, and the Release missing the wheel a retry must fill.
WHEEL_GAP: typ.Final = Holding(pypi=(WHEEL, SDIST), github=(SDIST, EARLIER_BUNDLE))


def publish_release_job() -> dict[str, object]:
    """Return ``publish-release``'s parsed job.

    Returns
    -------
    dict[str, object]
        The job's mapping from the checked-in workflow.
    """
    document: WorkflowDocument = load_workflow(
        (WORKFLOWS_DIRECTORY / RELEASE_WORKFLOW).read_text(encoding="utf-8")
    )
    return workflow_job(document, "publish-release")


def release_workspace(tmp_path: pathlib.Path) -> tuple[pathlib.Path, FakeRelease]:
    """Return a workspace in the state the job's own actions leave it.

    ``scripts/`` is the repository's, linked so the executed code is the code
    under test; ``dist/publish`` and ``dist/attestations`` hold what ``attest``
    uploaded; and the tag's release already exists as a draft, which is what
    ``draft-release`` leaves behind for this job to finish.

    Parameters
    ----------
    tmp_path
        The test's temporary directory, which the workspace is created under.

    Returns
    -------
    tuple[pathlib.Path, FakeRelease]
        The job's working directory and the scripted destinations.
    """
    work = tmp_path / "work"
    work.mkdir()
    link_scripts(REPOSITORY_ROOT, work)
    (work / "dist" / "publish").mkdir(parents=True)
    (work / "dist" / "attestations").mkdir()
    fake = fake_release(tmp_path)
    record_state(fake, draft=True, prerelease=False)
    return work, fake


def run_release_steps(
    workspace: tuple[pathlib.Path, FakeRelease],
    names: tuple[str, ...] = RELEASE_STEPS,
) -> subprocess.CompletedProcess[str]:
    """Run ``publish-release``'s scripted steps against the fakes.

    ``check-version`` reports a final release in the runs that do not ask for a
    pre-release, so that is the job environment here; the workflow reads a
    tag's own value through the publication step's ``env:``.

    Parameters
    ----------
    workspace
        The working directory and scripted destinations to run against.
    names
        The steps to run, which must be the workflow's own order.

    Returns
    -------
    subprocess.CompletedProcess[str]
        The first step that failed, or the last step to run when all passed.
    """
    work, fake = workspace
    return run_job_steps(
        publish_release_job(), names, work, environ=fake.environ(IS_PRERELEASE="false")
    )


def subjects_of(payloads: dict[str, bytes]) -> dict[str, object]:
    """Return an in-toto statement naming ``payloads`` by name and digest.

    Parameters
    ----------
    payloads
        Each artefact name and the bytes it holds.

    Returns
    -------
    dict[str, object]
        A statement whose subjects are those artefacts, as a bundle carries.
    """
    return {
        "subject": [
            {"name": name, "digest": {"sha256": hashlib.sha256(payload).hexdigest()}}
            for name, payload in payloads.items()
        ]
    }


__all__ = [
    "BUNDLE",
    "COMPLETE",
    "EARLIER_BUNDLE",
    "RELEASE_STEPS",
    "SDIST",
    "THROUGH_VERIFY",
    "WHEEL",
    "WHEEL_GAP",
    "publish_release_job",
    "release_workspace",
    "run_release_steps",
    "subjects_of",
]
