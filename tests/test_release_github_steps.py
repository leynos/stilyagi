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

import json
import typing as typ

import pytest

from tests.support.release_fakes import Attested, FakeRelease, fake_release
from tests.support.release_steps import (
    requires_bash,
    run_bash,
    run_job_steps,
)
from tests.support.release_workflow import (
    RELEASE_WORKFLOW,
    REPOSITORY_ROOT,
    link_scripts,
    step,
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
EARLIER_BUNDLE: typ.Final = "stilyagi-v0.2.0-run6-1.sigstore.json"

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
    "Check both destinations hold the same bytes",
    "Publish the GitHub Release",
)

#: The steps up to and including the comparison, but not the publication.
THROUGH_VERIFY: typ.Final = RELEASE_STEPS[:-1]


def _document() -> WorkflowDocument:
    """Return the release workflow document."""
    return load_workflow(
        (WORKFLOWS_DIRECTORY / RELEASE_WORKFLOW).read_text(encoding="utf-8")
    )


def _job() -> dict[str, object]:
    """Return ``publish-release``'s parsed job.

    Returns
    -------
    dict[str, object]
        The job's mapping from the checked-in workflow.
    """
    return workflow_job(_document(), "publish-release")


@pytest.fixture
def workspace(tmp_path: pathlib.Path) -> tuple[pathlib.Path, FakeRelease]:
    """Return a workspace in the state the job's own actions leave it.

    ``scripts/`` is the repository's, linked so the executed code is the code
    under test; ``dist/publish`` and ``dist/attestations`` hold what ``attest``
    uploaded; and the tag's release already exists as a draft, which is what
    ``draft-release`` leaves behind for this job to finish.

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
    _record_state(fake, draft=True, prerelease=False)
    return work, fake


def _record_state(fake: FakeRelease, **state: bool) -> None:
    """Write the release state the fake ``gh`` edits."""
    (fake.root / "release-state.json").write_text(json.dumps(state), encoding="utf-8")


def _run(
    workspace: tuple[pathlib.Path, FakeRelease],
    names: tuple[str, ...] = RELEASE_STEPS,
) -> subprocess.CompletedProcess[str]:
    """Run ``publish-release``'s scripted steps against the fakes.

    ``check-version`` reports a final release in the runs that do not ask for a
    pre-release, so that is the job environment here; the workflow reads a
    tag's own value through the publication step's ``env:``.

    Returns
    -------
    subprocess.CompletedProcess[str]
        The first step that failed, or the last step to run when all passed.
    """
    work, fake = workspace
    return run_job_steps(
        _job(), names, work, environ=fake.environ(IS_PRERELEASE="false")
    )


def _seed(
    work: pathlib.Path,
    fake: FakeRelease,
    *,
    pypi: tuple[str, ...] = (),
    github: tuple[str, ...] = (),
) -> None:
    """Write the rebuilt artefacts, this run's bundle and both holdings.

    The canonical bytes differ from the rebuild in every case, so a step that
    takes the wrong source is visible in what lands on the release. Both
    destinations' copies are attested, as they would be: an artefact only
    reaches either one through a run that signed it.
    """
    publish = work / "dist" / "publish"
    (publish / WHEEL).write_bytes(b"rebuilt-wheel")
    (publish / SDIST).write_bytes(b"rebuilt-sdist")
    bundle = work / "dist" / "attestations" / BUNDLE
    bundle.write_bytes(b"bundle")
    canonical = {
        WHEEL: b"canonical-wheel",
        SDIST: b"canonical-sdist",
        EARLIER_BUNDLE: b"earlier-bundle",
    }
    fake.attest({name: canonical[name] for name in (WHEEL, SDIST)})
    fake.attest({BUNDLE: bundle.read_bytes()})
    for directory, names in ((fake.pypi, pypi), (fake.github, github)):
        for name in names:
            (directory / name).write_bytes(canonical[name])


def _published(fake: FakeRelease) -> dict[str, object]:
    """Return the draft/prerelease state the release was left in."""
    path = fake.root / "release-state.json"
    assert path.exists(), "the release was never created"
    return typ.cast("dict[str, object]", json.loads(path.read_text(encoding="utf-8")))


def _uploads(fake: FakeRelease) -> list[tuple[str, ...]]:
    """Return every ``gh release upload`` the job made."""
    return [call for call in fake.calls("gh") if call[:2] == ("release", "upload")]


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
    _seed(work, fake, pypi=(WHEEL, SDIST), github=(WHEEL, SDIST, EARLIER_BUNDLE))
    completed = _run(workspace)
    assert completed.returncode == 0, completed.stderr
    assert not _uploads(fake), _uploads(fake)
    assert not any((work / "github-upload").iterdir()), sorted(
        path.name for path in (work / "github-upload").iterdir()
    )
    assert _published(fake) == {"draft": False, "prerelease": False}, _published(fake)


@requires_bash
def test_a_gap_whose_bytes_no_run_attests_is_never_attached(
    workspace: tuple[pathlib.Path, FakeRelease],
) -> None:
    """The upload set is refused, so the release stays a draft.

    A Release asset cannot be replaced, so bytes whose origin is unestablished
    are not attached at all: the run fails and the release stays unpublished.
    """
    work, fake = workspace
    _seed(work, fake, pypi=(WHEEL, SDIST), github=(SDIST,))
    for record in fake.attestations.iterdir():
        record.unlink()
    completed = _run(workspace)
    assert completed.returncode != 0, completed.stdout
    assert "no attestations found" in completed.stderr, completed.stderr
    assert not (fake.github / WHEEL).exists(), sorted(
        path.name for path in fake.github.iterdir()
    )
    assert _published(fake)["draft"] is True, "the draft was published"


@requires_bash
def test_a_gap_attested_only_by_another_repository_is_refused(
    workspace: tuple[pathlib.Path, FakeRelease],
) -> None:
    """A signature from someone else's release is not this repository's."""
    work, fake = workspace
    _seed(work, fake, pypi=(WHEEL, SDIST), github=(SDIST,))
    for record in fake.attestations.iterdir():
        record.unlink()
    fake.attest(
        {WHEEL: b"canonical-wheel", SDIST: b"canonical-sdist"},
        as_=Attested(repository="someone-else/stilyagi"),
    )
    completed = _run(workspace)
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
    _seed(work, fake, pypi=(WHEEL, SDIST), github=(SDIST,))
    completed = _run(workspace)
    assert completed.returncode == 0, completed.stderr
    assert (fake.github / WHEEL).read_bytes() == b"canonical-wheel", (
        "the release must hold PyPI's bytes, not the rebuild"
    )
    uploads = _uploads(fake)
    assert len(uploads) == 1, uploads
    assert "--clobber" not in uploads[0], uploads[0]


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
    _seed(work, fake, pypi=(WHEEL, SDIST), github=(SDIST, EARLIER_BUNDLE))
    completed = _run(workspace)
    assert completed.returncode == 0, completed.stderr
    staged = work / "github-upload"
    assert {path.name for path in staged.iterdir()} == {WHEEL}, sorted(
        path.name for path in staged.iterdir()
    )
    assert (fake.github / EARLIER_BUNDLE).read_bytes() == b"earlier-bundle", (
        "an existing asset must be left alone"
    )


@requires_bash
def test_a_release_without_an_attestation_receives_one(
    workspace: tuple[pathlib.Path, FakeRelease],
) -> None:
    """The first run of a tag attaches its own bundle, and only that one.

    A release published with no attestation would give a consumer no way to
    check where its assets came from, so the run that finds none supplies one.
    """
    work, fake = workspace
    _seed(work, fake, pypi=(WHEEL, SDIST), github=(WHEEL, SDIST))
    completed = _run(workspace)
    assert completed.returncode == 0, completed.stderr
    staged = work / "github-upload"
    assert {path.name for path in staged.iterdir()} == {BUNDLE}, sorted(
        path.name for path in staged.iterdir()
    )
    assert (fake.github / BUNDLE).read_bytes() == b"bundle", sorted(
        path.name for path in fake.github.iterdir()
    )


@requires_bash
def test_the_fetch_stage_names_every_file_it_needs_as_tsv(
    workspace: tuple[pathlib.Path, FakeRelease],
) -> None:
    """The TSV is the only channel from the stage step to the fetch loop."""
    work, fake = workspace
    _seed(work, fake, pypi=(WHEEL, SDIST), github=(SDIST,))
    completed = _run(workspace, RELEASE_STEPS[:3])
    assert completed.returncode == 0, completed.stderr
    fetched = (work / "pypi-fetch.tsv").read_text(encoding="utf-8")
    assert fetched.splitlines() == [
        f"{WHEEL}\thttps://files.example.test/packages/{WHEEL}"
    ], fetched


@requires_bash
def test_a_destination_that_disagrees_keeps_the_release_a_draft(
    workspace: tuple[pathlib.Path, FakeRelease],
) -> None:
    """The comparison is the gate on publishing, and it does not pass."""
    work, fake = workspace
    _seed(work, fake, pypi=(WHEEL, SDIST), github=(SDIST,))
    (fake.github / WHEEL).write_bytes(b"someone-else's-wheel")
    completed = _run(workspace)
    assert completed.returncode == 1, completed.stdout
    assert WHEEL in completed.stderr, completed.stderr
    assert _published(fake)["draft"] is True, "the draft was published"


@requires_bash
def test_the_verification_runs_before_the_release_is_published(
    workspace: tuple[pathlib.Path, FakeRelease],
) -> None:
    """A release still a draft while the check is running cannot go out early."""
    work, fake = workspace
    _seed(work, fake, pypi=(WHEEL, SDIST), github=(WHEEL, SDIST))
    _record_state(fake, draft=True, prerelease=False)
    completed = _run(workspace, THROUGH_VERIFY)
    assert completed.returncode == 0, completed.stderr
    assert _published(fake) == {"draft": True, "prerelease": False}, _published(fake)


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
    _record_state(fake, draft=True, prerelease=not expected)
    completed = run_bash(
        typ.cast("str", step(_job(), "Publish the GitHub Release")["run"]),
        work,
        environ=fake.environ(IS_PRERELEASE=prerelease),
    )
    assert completed.returncode == 0, completed.stderr
    assert _published(fake) == {"draft": False, "prerelease": expected}, _published(
        fake
    )


def test_every_scripted_step_is_run_by_this_module() -> None:
    """A step added to the job without a contract here is caught."""
    steps = _job().get("steps")
    assert isinstance(steps, list), "steps must be a list"
    scripted = tuple(
        str(entry["name"])
        for entry in steps
        if isinstance(entry, dict) and isinstance(entry.get("run"), str)
    )
    assert scripted == RELEASE_STEPS, scripted
