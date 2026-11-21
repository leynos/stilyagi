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

from tests.support.release_assets_fixtures import write_bundle
from tests.support.release_fakes import Attested
from tests.support.release_steps import (
    requires_bash,
    run_bash,
    run_job_steps,
)
from tests.support.release_workflow import github_output, workflow_job
from tests.support.release_workspace import (
    BUNDLE,
    DRAFT_STEPS,
    PUBLISH_STEPS,
    PUBLISH_WITH_GATE_STEPS,
    RELEASE_DECISION_STEPS,
    SDIST,
    WHEEL,
    Workspace,
    release_document,
    release_script,
    seed_release,
    stage_rebuild,
)

pytest_plugins = ("tests.support.release_workspace_fixtures",)

if typ.TYPE_CHECKING:
    import subprocess


def _run_publish(workspace: Workspace) -> subprocess.CompletedProcess[str]:
    """Run ``draft-release`` and then ``publish-pypi``, as a release does.

    The tag's release is created or reused first, its assets snapshotted and
    their provenance verified, and only then is the index fetched and the
    upload set decided. Later steps consume what the earlier ones wrote, so
    they cannot be reordered or run in isolation.

    Returns
    -------
    subprocess.CompletedProcess[str]
        The first step that failed, or the last step to run when all passed.
    """
    work, fake, _publish = workspace
    document = release_document()
    environ = fake.environ()
    completed = run_job_steps(
        workflow_job(document, "draft-release"), DRAFT_STEPS, work, environ=environ
    )
    if completed.returncode != 0:
        return completed
    return run_job_steps(
        workflow_job(document, "publish-pypi"), PUBLISH_STEPS, work, environ=environ
    )


@requires_bash
def test_a_stale_index_never_reaches_a_skipped_upload_s_run(
    workspace: Workspace,
) -> None:
    """The run that uploads nothing is the one the staging guard exists for.

    The whole sequence is run, in the order the workflow runs it. The index
    first lists both artefacts, so ``publish-pypi`` uploads nothing and
    writes ``remaining=false``. The index is then read again from a cache
    edge, and that read omits a name the Release still lacks. Filling the gap
    from this run's rebuild would attach bytes PyPI never accepted under a
    name it has published, and no re-run could repair it, so staging refuses
    and no ``gh release upload`` is made.

    Gating the refusal on "did this run upload" leaves exactly this case
    unguarded, which is why the rule is asked of the index alone.
    """
    work, fake, publish = workspace
    seed_release(publish, fake, pypi=(WHEEL, SDIST), github=(SDIST,))
    document = release_document()

    completed = run_job_steps(
        workflow_job(document, "draft-release"),
        DRAFT_STEPS,
        work,
        environ=fake.environ(),
    )
    assert completed.returncode == 0, completed.stderr

    # A complete index: every artefact is already PyPI's, so the run skips the
    # upload. The gate step is in the sequence because that is the fact under
    # test; a gate that ran it would fail here on the missing script.
    completed = run_job_steps(
        workflow_job(document, "publish-pypi"),
        PUBLISH_WITH_GATE_STEPS,
        work,
        environ=fake.environ(FAKE_RELEASE_INDEX_OMITS=""),
    )
    assert completed.returncode == 0, completed.stderr
    skipped = github_output(fake.root / "github-output")
    assert skipped["remaining"] == "false", skipped

    # The next job downloads the artefacts for itself; the one before deleted
    # every name it skipped.
    stage_rebuild(publish)
    completed = run_job_steps(
        workflow_job(document, "publish-release"),
        RELEASE_DECISION_STEPS,
        work,
        environ=fake.environ(FAKE_RELEASE_INDEX_OMITS=WHEEL),
    )
    assert completed.returncode == 1, completed.stdout
    assert "does not list" in completed.stderr, completed.stderr
    assert WHEEL in completed.stderr, completed.stderr
    assert not [
        call for call in fake.calls("gh") if call[:2] == ("release", "upload")
    ], "a stale index must not reach an upload"


@requires_bash
def test_a_fresh_index_reaches_the_release_upload(
    workspace: Workspace,
) -> None:
    """The sequence does reach ``gh release upload`` when staging permits it.

    This is the control the refusal test needs. Without it, "no upload was
    made" would also hold if the step list never ran the upload step, or if
    the gate could never open, and the assertion would pass for the wrong
    reason. Here staging is given the covering bundle it requires, and the
    same step list reaches the upload and attaches the file PyPI holds.
    """
    work, fake, publish = workspace
    seed_release(publish, fake, pypi=(WHEEL, SDIST), github=(SDIST,))
    bundles = work / "dist" / "attestations"
    bundles.mkdir()
    write_bundle(
        bundles, BUNDLE, {WHEEL: b"canonical-wheel", SDIST: b"canonical-sdist"}
    )
    completed = run_job_steps(
        workflow_job(release_document(), "publish-release"),
        RELEASE_DECISION_STEPS,
        work,
        environ=fake.environ(),
    )
    assert completed.returncode == 0, completed.stderr
    uploads = [call for call in fake.calls("gh") if call[:2] == ("release", "upload")]
    assert len(uploads) == 1, uploads
    assert (fake.github / WHEEL).read_bytes() == b"canonical-wheel", (
        "the Release must receive PyPI's bytes, not this run's rebuild"
    )


@pytest.mark.usefixtures("workspace")
def test_the_publishing_steps_name_this_repository_scripts() -> None:
    """The steps run the checked-in modules, not an inline copy."""
    for job, step in (
        ("draft-release", "Snapshot the release assets"),
        ("publish-pypi", "Skip artefacts already on PyPI"),
        ("publish-release", "Stage the assets the release lacks"),
        ("publish-release", "Check the fetched PyPI bytes"),
        ("publish-release", "Verify the upload set's provenance"),
        ("publish-release", "Check both destinations hold the same bytes"),
    ):
        script = release_script(job, step)
        assert "PYTHONPATH=scripts" in script, (job, step)
        assert "-m release_assets_cli" in script, (job, step)


def test_the_upload_step_is_gated_on_the_staging_output() -> None:
    """PyPI is never called when nothing remains to publish."""
    upload = workflow_job(release_document(), "publish-pypi").get("steps")
    assert isinstance(upload, list), "steps must be a list"
    publish = [s for s in upload if s.get("name") == "Publish to PyPI"]
    assert len(publish) == 1, publish
    assert publish[0].get("if") == "steps.pending.outputs.remaining == 'true'", publish


@requires_bash
def test_a_missing_release_is_created(
    workspace: Workspace,
) -> None:
    """A confirmed absence is the one case that creates a release."""
    work, fake, _publish = workspace
    completed = run_bash(
        release_script("draft-release", "Create or reuse the draft release"),
        work,
        environ=fake.environ(FAKE_RELEASE_VIEW_STATUS="1", IS_PRERELEASE="false"),
    )
    assert completed.returncode == 0, completed.stderr
    created = [call for call in fake.calls("gh") if call[:2] == ("release", "create")]
    assert len(created) == 1, created


@requires_bash
def test_a_view_failure_that_is_not_absence_is_reported_as_itself(
    workspace: Workspace,
) -> None:
    """A network or token failure must not become "release already exists".

    Only ``release not found`` means the Release is absent. Any other failure
    is passed through with its own message: creating after one would fail
    misleadingly, and the release's real state would never be examined.
    """
    work, fake, _publish = workspace
    completed = run_bash(
        release_script("draft-release", "Create or reuse the draft release"),
        work,
        environ=fake.environ(
            FAKE_RELEASE_VIEW_STATUS="1",
            FAKE_RELEASE_VIEW_ERROR="HTTP 403: Resource not accessible by integration",
            IS_PRERELEASE="false",
        ),
    )
    assert completed.returncode == 1, completed.stdout
    assert "403" in completed.stderr, completed.stderr
    created = [call for call in fake.calls("gh") if call[:2] == ("release", "create")]
    assert not created, "a release must not be created on an unconfirmed absence"


@requires_bash
def test_a_first_release_uploads_every_artefact(
    workspace: Workspace,
) -> None:
    """With both destinations empty, both files remain for PyPI."""
    _work, fake, publish = workspace
    seed_release(publish, fake)
    completed = _run_publish(workspace)
    assert completed.returncode == 0, completed.stderr
    assert {p.name for p in publish.iterdir()} == {WHEEL, SDIST}, (
        "expected {p.name for p in publish.iterdir()} == {WHEEL, SDIST}"
    )
    output = github_output(workspace[1].root / "github-output")
    assert output["remaining"] == "true", output


@requires_bash
def test_a_re_run_holds_back_what_pypi_already_has(
    workspace: Workspace,
) -> None:
    """Rebuilt bytes never replace bytes PyPI already published."""
    _work, fake, publish = workspace
    seed_release(publish, fake, pypi=(WHEEL, SDIST), github=(SDIST,))
    completed = _run_publish(workspace)
    assert completed.returncode == 0, completed.stderr
    assert not any(publish.iterdir()), sorted(p.name for p in publish.iterdir())
    output = github_output(fake.root / "github-output")
    assert output["remaining"] == "false", output
    # The release's carried bytes are what was checked, not the rebuild.
    assert (fake.github / SDIST).read_bytes() == b"canonical-sdist", fake.github / SDIST


@requires_bash
def test_a_name_only_the_release_holds_is_sent_with_the_releases_bytes(
    workspace: Workspace,
) -> None:
    """The destination that holds the name decides the bytes, not the rebuild."""
    _work, fake, publish = workspace
    seed_release(publish, fake, pypi=(SDIST,), github=(WHEEL,))
    completed = _run_publish(workspace)
    assert completed.returncode == 0, completed.stderr
    assert {p.name for p in publish.iterdir()} == {WHEEL}, [
        p.name for p in publish.iterdir()
    ]
    assert (publish / WHEEL).read_bytes() == b"canonical-wheel", publish


@requires_bash
def test_a_carried_asset_with_no_attestation_is_never_sent_to_pypi(
    workspace: Workspace,
) -> None:
    """The release's bytes are attested, or PyPI does not receive them.

    The digest the Release reports proves only that the file matches what the
    Release holds now; the attestation is the only evidence of who built it.
    """
    _work, fake, publish = workspace
    seed_release(publish, fake, github=(WHEEL,))
    for record in fake.attestations.iterdir():
        record.unlink()
    completed = _run_publish(workspace)
    assert completed.returncode != 0, completed.stdout
    assert "no attestations found" in completed.stderr, completed.stderr
    assert (publish / SDIST).exists(), "the refusal must stop the carry, not the run"
    assert (publish / WHEEL).read_bytes() == b"rebuilt-wheel", (
        "the unattested file must not replace the rebuild"
    )


@requires_bash
def test_a_carried_asset_signed_by_another_workflow_is_refused(
    workspace: Workspace,
) -> None:
    """A signature proves *a* workflow ran, so the workflow is named too."""
    _work, fake, publish = workspace
    seed_release(publish, fake, github=(WHEEL,))
    for record in fake.attestations.iterdir():
        record.unlink()
    fake.attest(
        {WHEEL: b"canonical-wheel"},
        as_=Attested(workflow="/.github/workflows/build-wheels.yml"),
    )
    completed = _run_publish(workspace)
    assert completed.returncode != 0, completed.stdout
    assert "no attestations matched the policy" in completed.stderr, completed.stderr


@requires_bash
def test_the_staged_upload_set_addresses_pypi_exactly_once(
    workspace: Workspace,
) -> None:
    """One staging decision is read once; no artefact is retried or skipped."""
    _work, fake, publish = workspace
    seed_release(publish, fake, github=())
    completed = _run_publish(workspace)
    assert completed.returncode == 0, completed.stderr
    index_calls = [call for call in fake.calls("curl") if "--write-out" in call]
    assert len(index_calls) == 1, index_calls


@requires_bash
def test_a_connection_failure_is_retried_then_reported(
    workspace: Workspace,
) -> None:
    """A runner that cannot reach PyPI fails rather than releasing blind."""
    _work, fake, _publish = workspace
    environ = fake.environ(FAKE_RELEASE_CURL_STATUSES="000")
    completed = run_bash(
        release_script("publish-pypi", "Fetch the PyPI index"),
        workspace[0],
        environ=environ,
    )
    assert completed.returncode == 1, completed.stdout
    output = github_output(fake.root / "github-output")
    assert output["status"] == "000", output
    assert output["attempts"] == "6", output
    # A retry is silent unless it is annotated, and an operator reading a run
    # that sat for minutes needs to know which failures it was retrying. One
    # annotation per attempt, naming that attempt and its status.
    retries = [
        line
        for line in completed.stdout.splitlines()
        if line.startswith("::warning title=PyPI index retry::")
    ]
    assert len(retries) == 6, completed.stdout
    assert "attempt 1 of 6, status 000" in retries[0], retries
    assert "attempt 6 of 6, status 000" in retries[-1], retries


@requires_bash
def test_a_first_release_treats_a_404_as_an_empty_index(
    workspace: Workspace,
) -> None:
    """A project PyPI has never seen has no page, and that is not an error."""
    _work, fake, _publish = workspace
    completed = run_bash(
        release_script("publish-pypi", "Fetch the PyPI index"),
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
    workspace: Workspace,
) -> None:
    """A proxy's refusal must not be mistaken for "nothing published"."""
    _work, fake, _publish = workspace
    completed = run_bash(
        release_script("publish-pypi", "Fetch the PyPI index"),
        workspace[0],
        environ=fake.environ(FAKE_RELEASE_CURL_STATUSES=status),
    )
    assert completed.returncode == 1, completed.stdout
    assert completed.stderr.strip(), "a non-200 must say why it stopped"
