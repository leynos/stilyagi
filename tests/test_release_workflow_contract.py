"""Hold ``release.yml`` to the shape a publishing workflow must have.

A release workflow runs on a tag, writes to PyPI and to a GitHub Release, and
holds a token for each. Every property in this module is one that a mistake in
turns a release into either a silent no-op or an irreversible upload: the
trigger that decides it runs at all, the write scopes each job declares rather
than inherits, the queue rather than cancel that protects a half-finished
upload, the draft that keeps a release unpublished until both destinations
agree, and the rule that no GitHub expression is expanded into a shell script.

Nothing here executes a step; ``test_release_publish_steps.py`` and
``test_release_github_steps.py`` do that. This module reads the document and
asserts its structure, so a failure names what the workflow says rather than
what a script did.
"""

import re
import typing as typ

import pytest

from tests.support.release_workflow import (
    BUILD_WHEELS_WORKFLOW,
    READER,
    RELEASE_WORKFLOW,
    outputs,
    step,
    step_mappings,
    step_script,
    workflow_job,
)
from tests.support.workflow_documents import WORKFLOWS_DIRECTORY
from tests.support.workflows import load_workflow, triggers

if typ.TYPE_CHECKING:
    from tests.support.workflows import WorkflowDocument

DOCUMENT: typ.Final[WorkflowDocument] = load_workflow(
    (WORKFLOWS_DIRECTORY / RELEASE_WORKFLOW).read_text(encoding="utf-8")
)

#: Jobs that must exist for a release to be published at all, and the ones they
#: wait on. Written out because a job deleted between two stages is exactly the
#: mistake the topology exists to catch.
EXPECTED_JOBS: typ.Final = {
    "check-version": set(),
    "build-wheels": set(),
    "attest": {"check-version", "build-wheels"},
    "draft-release": {"check-version", "attest"},
    "publish-pypi": {"attest", "draft-release"},
    "publish-release": {"check-version", "draft-release", "publish-pypi"},
}

#: The write scopes each job may declare. Nothing else, and no job may inherit
#: the workflow's own, which is empty.
JOB_PERMISSIONS: typ.Final = {
    "check-version": {"contents": "read"},
    "build-wheels": {"contents": "read"},
    "attest": {"contents": "read", "id-token": "write", "attestations": "write"},
    "draft-release": {"contents": "write"},
    "publish-pypi": {"contents": "read", "id-token": "write"},
    "publish-release": {"contents": "write"},
}


def _needs(document: WorkflowDocument) -> dict[str, set[str]]:
    """Return each job's ``needs`` as a set, empty where it declares none."""
    jobs = document["jobs"]
    assert isinstance(jobs, dict), "jobs must be a mapping"
    result: dict[str, set[str]] = {}
    for name, job in jobs.items():
        assert isinstance(job, dict), name
        declared = job.get("needs") or []
        result[str(name)] = {str(item) for item in declared}
    return result


def test_the_workflow_publishes_on_a_version_tag() -> None:
    """A tag is the only trigger: a branch push must not reach PyPI."""
    assert triggers(DOCUMENT) == {"push"}, "expected triggers(DOCUMENT) == {'push'}"
    on = DOCUMENT["on"]
    assert isinstance(on, dict), "expected triggers to be a mapping"
    push = on["push"]
    assert isinstance(push, dict), "expected push filters"
    assert push.get("tags") == ["v*.*.*"], push
    assert "branches" not in push, "expected 'branches' not in push"


def test_the_workflow_declares_no_permissions_of_its_own() -> None:
    """Scopes are declared per job, so a job cannot inherit a write."""
    assert DOCUMENT.get("permissions") == {}, DOCUMENT.get("permissions")


def test_a_re_run_queues_rather_than_cancels() -> None:
    """Cancelling could stop an upload part-way through."""
    concurrency = DOCUMENT.get("concurrency")
    assert isinstance(concurrency, dict), "expected a concurrency mapping"
    assert concurrency.get("group") == "release-${{ github.ref }}", concurrency
    assert concurrency.get("cancel-in-progress") == "false", concurrency


@pytest.mark.parametrize(("job", "needs"), sorted(EXPECTED_JOBS.items()))
def test_each_job_waits_on_the_jobs_it_needs(job: str, needs: set[str]) -> None:
    """No job runs before the thing it consumes has produced it."""
    assert _needs(DOCUMENT).get(job) == needs, (job, _needs(DOCUMENT))


@pytest.mark.parametrize(("job", "permissions"), sorted(JOB_PERMISSIONS.items()))
def test_each_job_declares_exactly_its_scopes(
    job: str, permissions: dict[str, str]
) -> None:
    """A job holds no scope it does not use, and no write it does not need."""
    declared = workflow_job(DOCUMENT, job).get("permissions")
    assert declared == permissions, (job, declared)


def test_the_build_wheels_delegation_is_local_and_read_only() -> None:
    """The platform matrix lives in one reusable file, not twice."""
    job = workflow_job(DOCUMENT, "build-wheels")
    assert job.get("uses") == "./.github/workflows/build-wheels.yml", job
    assert job.get("permissions") == {"contents": "read"}, job


def test_check_version_reports_the_two_values_the_release_needs() -> None:
    """The version and the pre-release flag are the only channels forward."""
    declared = outputs(workflow_job(DOCUMENT, "check-version"))
    assert set(declared) == {"version", "prerelease"}, declared
    assert "prerelease" in declared["prerelease"], declared


def test_the_version_step_reads_its_tag_from_an_environment_variable() -> None:
    """The tag reaches the script through the environment, not an expansion."""
    job = workflow_job(DOCUMENT, "check-version")
    version_step = step(job, "Check the pyproject.toml version against the tag")
    assert version_step.get("env") == {
        "TAG_VERSION": "${{ steps.cargo-version.outputs.version }}"
    }, version_step
    assert step_script(
        job, "Check the pyproject.toml version against the tag"
    ).startswith("python3 -m scripts.release_version"), version_step


def test_every_job_that_runs_a_script_installs_python_3_14() -> None:
    """The scripts use PEP 649 deferred annotations, which 3.12 cannot import.

    ``ubuntu-latest`` ships Python 3.12, so a job that runs ``python3``
    without installing its own interpreter fails on import rather than on
    the version it was checking. Every job running a script must therefore
    declare the setup step that the other jobs take for granted.
    """
    for name in ("check-version", "attest", "draft-release", "publish-pypi"):
        job = workflow_job(DOCUMENT, name)
        setup = step(job, "Install Python")
        assert setup.get("with") == {"python-version": "3.14"}, (name, setup)
        assert str(setup.get("uses", "")).startswith("actions/setup-python@"), (
            name,
            setup,
        )


def test_every_run_script_is_free_of_github_expressions() -> None:
    """A ``${{ }}`` in a script is expanded before the shell parses it.

    That makes a branch name, a tag or an output a code-injection surface, and
    it hides the value from anything that would lint the script. Values reach
    these steps through ``env:`` instead, where the shell treats them as data.
    """
    jobs = DOCUMENT["jobs"]
    assert isinstance(jobs, dict), "jobs must be a mapping"
    offenders = [
        f"{job}:{entry.get('name')}"
        for job, body in jobs.items()
        for entry in (body.get("steps") or [])
        if isinstance(entry, dict)
        and isinstance(entry.get("run"), str)
        and "${{" in entry["run"]
    ]
    assert not offenders, offenders


def test_every_checked_out_repository_keeps_its_credentials_to_itself() -> None:
    """A token left in ``.git/config`` is readable by every later step."""
    jobs = DOCUMENT["jobs"]
    assert isinstance(jobs, dict), "jobs must be a mapping"
    for job, body in jobs.items():
        for entry in body.get("steps") or []:
            if not isinstance(entry, dict):
                continue
            if not str(entry.get("uses", "")).startswith("actions/checkout@"):
                continue
            declared = entry.get("with") or {}
            inputs: dict[str, object] = declared if isinstance(declared, dict) else {}
            assert inputs.get("persist-credentials") == "false", (job, inputs)


def test_the_publishing_jobs_check_out_only_the_scripts() -> None:
    """A publisher needs the reconciliation code, not the source tree."""
    for job in ("attest", "draft-release", "publish-pypi", "publish-release"):
        checkout = step(workflow_job(DOCUMENT, job), "Check out repository")
        declared = checkout.get("with") or {}
        inputs: dict[str, object] = declared if isinstance(declared, dict) else {}
        assert inputs.get("sparse-checkout") == "scripts", (job, inputs)


def test_every_action_is_pinned_to_a_full_commit_sha() -> None:
    """A tag or branch reference can be moved under the release."""
    pattern = re.compile(r"@[0-9a-f]{40}$")
    jobs = DOCUMENT["jobs"]
    assert isinstance(jobs, dict), "jobs must be a mapping"
    for job, body in jobs.items():
        for entry in body.get("steps") or []:
            if not isinstance(entry, dict):
                continue
            uses = entry.get("uses")
            if not uses or str(uses).startswith("./"):
                continue
            assert pattern.search(str(uses)), (job, uses)


def _artefact_name(entry: dict[str, object], key: str) -> str | None:
    """Return one upload or download step's `name` input, or None when it has none."""
    declared = entry.get("with") or {}
    inputs: dict[str, object] = declared if isinstance(declared, dict) else {}
    name = inputs.get(key)
    return None if name is None else str(name)


def _uploaded_names(document: WorkflowDocument) -> set[str]:
    """Return every artefact name `document` uploads, as written."""
    jobs = document["jobs"]
    assert isinstance(jobs, dict), "jobs must be a mapping"
    names = {
        found
        for body in jobs.values()
        if isinstance(body, dict)
        for entry in step_mappings(body)
        if str(entry.get("uses", "")).startswith("actions/upload-artifact@")
        if (found := _artefact_name(entry, "name")) is not None
    }
    assert names, "the build workflow uploads no artefacts"
    return names


def _downloads_covering(name: str, patterns: set[str]) -> bool:
    """Return whether a download pattern reaches `name`.

    A `pattern` input is a glob matched against the upload's name, while a
    `name` input must equal it. GitHub matches the glob against the whole
    name, so only a trailing `*` is treated as a prefix here; anything richer
    would be guessed at rather than read.

    Returns
    -------
    bool
        Whether any of `patterns` reaches `name`.
    """
    return any(
        name == pattern or (pattern.endswith("*") and name.startswith(pattern[:-1]))
        for pattern in patterns
    )


def test_attest_downloads_every_artefact_the_build_uploads() -> None:
    """A name uploaded but never downloaded silently loses its bytes.

    The sdist is uploaded under its own name, not under ``wheels-*``. Download
    only the wheels and the cardinality guard finds no archive, so every tag
    aborts before anything is attested or published.
    """
    build = load_workflow(
        (WORKFLOWS_DIRECTORY / BUILD_WHEELS_WORKFLOW).read_text(encoding="utf-8")
    )
    downloads = {
        found
        for entry in step_mappings(workflow_job(DOCUMENT, "attest"))
        if str(entry.get("uses", "")).startswith("actions/download-artifact@")
        if (found := _artefact_name(entry, "pattern") or _artefact_name(entry, "name"))
        is not None
    }
    missing = [
        name
        for name in sorted(_uploaded_names(build))
        if not _downloads_covering(name, downloads)
    ]
    assert not missing, f"attest never downloads {missing}; it downloads {downloads}"


def test_the_pypi_job_publishes_from_an_environment() -> None:
    """Trusted Publishing binds the token to an environment, not just a job."""
    job = workflow_job(DOCUMENT, "publish-pypi")
    environment = job.get("environment")
    assert isinstance(environment, dict), environment
    assert environment.get("name") == "pypi", environment
    assert environment.get("url") == "https://pypi.org/project/stilyagi/", environment


def test_the_reading_names_its_own_document() -> None:
    """A missing job is reported as this workflow's, not an anonymous one."""
    assert READER == "release workflow", READER
