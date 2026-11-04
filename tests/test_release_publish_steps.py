"""Run the publishing steps against a scripted GitHub Release and PyPI.

``release.yml`` keeps its decisions in ``scripts/release_assets.py`` and its
network calls in ``curl`` and ``gh``, so the steps themselves are the contract
between the two: which files a step hands the next one, which of them survive
to be uploaded, and what a second run of the same tag does differently. Those
are properties of the shell scripts the workflow carries, and the only honest
way to check them is to run the scripts.

The state directories stand in for the two destinations. A step is run from the
workflow document, with the repository's own ``scripts/`` linked into its
working directory, so the code under test is the code that ships.
"""

import typing as typ

import pytest

from tests.support.release_fakes import FakeRelease, fake_release
from tests.support.release_steps import (
    requires_bash,
    run_bash,
    run_job_steps,
)
from tests.support.release_workflow import (
    RELEASE_WORKFLOW,
    REPOSITORY_ROOT,
    github_output,
    link_scripts,
    step_script,
    workflow_job,
)
from tests.support.workflow_documents import WORKFLOWS_DIRECTORY
from tests.support.workflows import load_workflow

if typ.TYPE_CHECKING:
    import pathlib
    import subprocess

    from tests.support.workflows import WorkflowDocument

WHEEL: typ.Final = "stilyagi-0.2.0-cp314-cp314-manylinux_2_28_x86_64.whl"
SDIST: typ.Final = "stilyagi-0.2.0.tar.gz"
BUNDLE: typ.Final = "stilyagi-v0.2.0-run7-1.sigstore.json"


def _document() -> WorkflowDocument:
    """Return the release workflow document."""
    return load_workflow(
        (WORKFLOWS_DIRECTORY / RELEASE_WORKFLOW).read_text(encoding="utf-8")
    )


def _script(job: str, step: str) -> str:
    """Return one named step's script from the release workflow's job."""
    return step_script(workflow_job(_document(), job), step)


@pytest.fixture
def workspace(
    tmp_path: pathlib.Path,
) -> tuple[pathlib.Path, FakeRelease, pathlib.Path]:
    """Return a working directory, its fake destinations and its publish dir."""
    work = tmp_path / "work"
    work.mkdir()
    link_scripts(REPOSITORY_ROOT, work)
    publish = work / "dist" / "publish"
    publish.mkdir(parents=True)
    return work, fake_release(tmp_path), publish


#: The steps up to and including PyPI's upload decision, in workflow order.
#: Each publishes into the directory the one before it filled, so they are a
#: sequence rather than a set.
_PUBLISH_TO_PYPI: typ.Final = (
    "Create or reuse the draft release",
    "Snapshot the release assets",
    "Fetch the PyPI index",
    "Skip artefacts already on PyPI",
)


def _run_publish(
    workspace: tuple[pathlib.Path, FakeRelease, pathlib.Path],
) -> subprocess.CompletedProcess[str]:
    """Run ``draft-release`` and then ``publish-pypi``, as a release does.

    The tag's release is created or reused first, its assets snapshotted, and
    only then is the index fetched and the upload set decided. Later steps
    consume what the earlier ones wrote, so they cannot be reordered or run
    in isolation.

    Returns
    -------
    subprocess.CompletedProcess[str]
        The first step that failed, or the last step to run when all passed.
    """
    work, fake, _publish = workspace
    document = _document()
    environ = fake.environ()
    completed = run_job_steps(
        workflow_job(document, "draft-release"),
        ("Create or reuse the draft release", "Snapshot the release assets"),
        work,
        environ=environ,
    )
    if completed.returncode != 0:
        return completed
    return run_job_steps(
        workflow_job(document, "publish-pypi"),
        ("Fetch the PyPI index", "Skip artefacts already on PyPI"),
        work,
        environ=environ,
    )


def _seed_release(
    publish: pathlib.Path,
    fake: FakeRelease,
    *,
    pypi: tuple[str, ...] = (),
    github: tuple[str, ...] = (),
) -> None:
    """Write a rebuilt artefact set and the two destinations' holdings."""
    (publish / WHEEL).write_bytes(b"rebuilt-wheel")
    (publish / SDIST).write_bytes(b"rebuilt-sdist")
    canonical = {WHEEL: b"canonical-wheel", SDIST: b"canonical-sdist"}
    for directory, names in ((fake.pypi, pypi), (fake.github, github)):
        for name in names:
            (directory / name).write_bytes(canonical[name])


@pytest.mark.usefixtures("workspace")
def test_the_publishing_steps_name_this_repositorys_scripts() -> None:
    """The steps run the checked-in modules, not an inline copy."""
    for job, step in (
        ("draft-release", "Snapshot the release assets"),
        ("publish-pypi", "Skip artefacts already on PyPI"),
        ("publish-release", "Stage the assets the release lacks"),
        ("publish-release", "Check the fetched PyPI bytes"),
        ("publish-release", "Check both destinations hold the same bytes"),
    ):
        script = _script(job, step)
        assert "PYTHONPATH=scripts" in script, (job, step)
        assert "-m release_assets_cli" in script, (job, step)


def test_the_upload_step_is_gated_on_the_staging_output() -> None:
    """PyPI is never called when nothing remains to publish."""
    upload = workflow_job(_document(), "publish-pypi").get("steps")
    assert isinstance(upload, list), "steps must be a list"
    publish = [s for s in upload if s.get("name") == "Publish to PyPI"]
    assert len(publish) == 1, publish
    assert publish[0].get("if") == "steps.pending.outputs.remaining == 'true'", publish


@requires_bash
def test_a_first_release_uploads_every_artefact(
    workspace: tuple[pathlib.Path, FakeRelease, pathlib.Path],
) -> None:
    """With both destinations empty, both files remain for PyPI."""
    _work, fake, publish = workspace
    _seed_release(publish, fake)
    completed = _run_publish(workspace)
    assert completed.returncode == 0, completed.stderr
    assert {p.name for p in publish.iterdir()} == {WHEEL, SDIST}, (
        "expected {p.name for p in publish.iterdir()} == {WHEEL, SDIST}"
    )
    output = github_output(workspace[1].root / "github-output")
    assert output["remaining"] == "true", output


@requires_bash
def test_a_re_run_holds_back_what_pypi_already_has(
    workspace: tuple[pathlib.Path, FakeRelease, pathlib.Path],
) -> None:
    """Rebuilt bytes never replace bytes PyPI already published."""
    _work, fake, publish = workspace
    _seed_release(publish, fake, pypi=(WHEEL, SDIST), github=(SDIST,))
    completed = _run_publish(workspace)
    assert completed.returncode == 0, completed.stderr
    assert not any(publish.iterdir()), sorted(p.name for p in publish.iterdir())
    output = github_output(fake.root / "github-output")
    assert output["remaining"] == "false", output
    # The release's carried bytes are what was checked, not the rebuild.
    assert (fake.github / SDIST).read_bytes() == b"canonical-sdist", fake.github / SDIST


@requires_bash
def test_a_name_only_the_release_holds_is_sent_with_the_releases_bytes(
    workspace: tuple[pathlib.Path, FakeRelease, pathlib.Path],
) -> None:
    """The destination that holds the name decides the bytes, not the rebuild."""
    _work, fake, publish = workspace
    _seed_release(publish, fake, pypi=(SDIST,), github=(WHEEL,))
    completed = _run_publish(workspace)
    assert completed.returncode == 0, completed.stderr
    assert {p.name for p in publish.iterdir()} == {WHEEL}, [
        p.name for p in publish.iterdir()
    ]
    assert (publish / WHEEL).read_bytes() == b"canonical-wheel", publish


@requires_bash
def test_the_staged_upload_set_addresses_pypi_exactly_once(
    workspace: tuple[pathlib.Path, FakeRelease, pathlib.Path],
) -> None:
    """One staging decision is read once; no artefact is retried or skipped."""
    _work, fake, publish = workspace
    _seed_release(publish, fake, github=())
    completed = _run_publish(workspace)
    assert completed.returncode == 0, completed.stderr
    index_calls = [call for call in fake.calls("curl") if "--write-out" in call]
    assert len(index_calls) == 1, index_calls


@requires_bash
def test_a_connection_failure_is_retried_then_reported(
    workspace: tuple[pathlib.Path, FakeRelease, pathlib.Path],
) -> None:
    """A runner that cannot reach PyPI fails rather than releasing blind."""
    _work, fake, _publish = workspace
    environ = fake.environ(FAKE_RELEASE_CURL_STATUSES="000")
    completed = run_bash(
        _script("publish-pypi", "Fetch the PyPI index"),
        workspace[0],
        environ=environ,
    )
    assert completed.returncode == 1, completed.stdout
    output = github_output(fake.root / "github-output")
    assert output["status"] == "000", output
    assert output["attempts"] == "6", output


@requires_bash
def test_a_first_release_treats_a_404_as_an_empty_index(
    workspace: tuple[pathlib.Path, FakeRelease, pathlib.Path],
) -> None:
    """A project PyPI has never seen has no page, and that is not an error."""
    _work, fake, _publish = workspace
    completed = run_bash(
        _script("publish-pypi", "Fetch the PyPI index"),
        workspace[0],
        environ=fake.environ(FAKE_RELEASE_CURL_STATUSES="404"),
    )
    assert completed.returncode == 0, completed.stderr
    index = (workspace[0] / "pypi-index.json").read_text(encoding="utf-8")
    assert index.strip() == '{"files": []}', index


@requires_bash
@pytest.mark.parametrize("status", ["403", "502"])
def test_an_unexpected_status_stops_the_release(
    status: str,
    workspace: tuple[pathlib.Path, FakeRelease, pathlib.Path],
) -> None:
    """A proxy's refusal must not be mistaken for "nothing published"."""
    _work, fake, _publish = workspace
    completed = run_bash(
        _script("publish-pypi", "Fetch the PyPI index"),
        workspace[0],
        environ=fake.environ(FAKE_RELEASE_CURL_STATUSES=status),
    )
    assert completed.returncode == 1, completed.stdout
    assert completed.stderr.strip(), "a non-200 must say why it stopped"
