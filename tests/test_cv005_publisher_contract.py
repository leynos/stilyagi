"""The local CV-005 clauses the shared contract checker leaves to us.

The shared ``cv005-contracts`` checker already holds the broad shape: one
publisher, one protected environment, and no CodeScene contact from a
pull-request lane. These contracts add the clauses it accepts more loosely
or does not read at all, and they are deliberately stricter:

* the publisher groups by workflow and ref, so every spelling the shared
  checker accepts cannot drift between repositories;
* the token check keeps one canonical name, id and command, its guard names
  that id, and the secret is bound nowhere but the uploader's
  ``access-token`` input;
* the pull-request lane preinstalls the exact ``cargo-nextest`` the pinned
  ``generate-coverage`` action reuses, so its ratchet compares one runner
  with the baseline rather than the difference between two.

The workflow reader is ``tests.support.workflow_documents``, whose shapes
live in ``workflow_shapes``. No module here parses YAML for itself.
"""

import re
import typing as typ

from tests.support.workflow_documents import workflow_documents
from tests.support.workflows import serves_pull_requests

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from tests.support.workflow_shapes import (
        WorkflowDocument,
        WorkflowJob,
        WorkflowStep,
    )

#: The estate's canonical publisher group. Keying on the ref alone keeps
#: every run for main in one queue; ``github.workflow`` names the group
#: after this file rather than repeating its stem.
CANONICAL_GROUP: typ.Final[str] = "${{ github.workflow }}-${{ github.ref }}"

#: The one name, id and command a publisher's token check may have. The
#: expression is evaluated before the shell starts, so the step binds
#: nothing and holds no conditional a prefix could neutralize.
CHECK_STEP_NAME: typ.Final[str] = "Check CodeScene token"
CHECK_STEP_ID: typ.Final[str] = "codescene-token"
CHECK_COMMAND: typ.Final[str] = (
    'echo "available=${{ secrets.CS_ACCESS_TOKEN != \'\' }}" >> "$GITHUB_OUTPUT"'
)

#: The upload guard: the canonical id and the main-ref term, both whole
#: ``&&`` terms. The ref term refuses a dispatch aimed at a branch, which
#: would otherwise upload that branch's coverage as the trunk's.
UPLOAD_GUARD: typ.Final[str] = (
    "steps.codescene-token.outputs.available == 'true' && "
    "github.ref == 'refs/heads/main'"
)

#: The expression naming the secret, not a secret value. It is the only
#: value the uploader's ``access-token`` input may take.
TOKEN_INPUT: typ.Final[str] = "${{ secrets.CS_ACCESS_TOKEN }}"  # ruff: ignore[hardcoded-password-string]

CODESCENE_ENVIRONMENT: typ.Final[str] = "codescene"
UPLOAD_ACTION: typ.Final[str] = (
    "leynos/shared-actions/.github/actions/upload-codescene-coverage"
)
COVERAGE_ACTION: typ.Final[str] = (
    "leynos/shared-actions/.github/actions/generate-coverage"
)

#: The shared-actions revision both coverage lanes pin. Its
#: ``scripts/install_cargo_nextest.py`` declares
#: ``CARGO_NEXTEST_VERSION = "0.9.145"`` and reuses a preinstalled
#: ``cargo-nextest`` rather than installing its own. Re-read that constant
#: when this pin moves; ``COVERAGE_NEXTEST_VERSION`` must move with it.
SHARED_ACTIONS_PIN: typ.Final[str] = "6cec89bac47a21cf756d68d638a9a510998e57f8"
COVERAGE_NEXTEST_VERSION: typ.Final[str] = "0.9.145"

#: The pull-request lane whose ratchet compares against the publisher.
PULL_REQUEST_LANE: typ.Final[str] = "smoke.yml"

#: A version pin written into a step's ``run`` as ``cargo-nextest@x.y.z``.
_NEXTEST_PIN: typ.Final[re.Pattern[str]] = re.compile(
    r"cargo-nextest@(?P<version>\d+\.\d+\.\d+)"
)

#: This repository's workflows, read once. Acquisition failures raise
#: rather than yielding an empty mapping, so a broken reader cannot make
#: every assertion below pass over nothing.
DOCUMENTS: typ.Final[dict[str, WorkflowDocument]] = workflow_documents()


def _jobs(document: WorkflowDocument) -> dict[str, WorkflowJob]:
    """Return a document's jobs, empty when the block is not a mapping."""
    jobs = document.get("jobs")
    if not isinstance(jobs, dict):
        return {}
    return typ.cast("dict[str, WorkflowJob]", jobs)


def _steps(job: WorkflowJob) -> list[WorkflowStep]:
    """Return a job's steps, empty when the block is not a list."""
    steps = job.get("steps")
    if not isinstance(steps, list):
        return []
    return steps


def _action_of(step: WorkflowStep) -> str:
    """Return the action a step invokes, without its ref."""
    return (step.get("uses") or "").partition("@")[0]


def _publisher() -> tuple[str, WorkflowDocument, str, WorkflowJob]:
    """Return the file, document, job name and job of the one uploader."""
    found = [
        (name, document, job_name, job)
        for name, document in DOCUMENTS.items()
        for job_name, job in _jobs(document).items()
        if any(_action_of(step) == UPLOAD_ACTION for step in _steps(job))
    ]
    assert len(found) == 1, f"expected one CodeScene publisher job, found {found}"
    return found[0]


def _coverage_step(document: WorkflowDocument) -> WorkflowStep:
    """Return the one step invoking the shared coverage action."""
    found = [
        step
        for job in _jobs(document).values()
        for step in _steps(job)
        if _action_of(step) == COVERAGE_ACTION
    ]
    assert len(found) == 1, f"expected one coverage step, found {found}"
    return found[0]


def _strings(value: object) -> cabc.Iterator[str]:
    """Yield every string in a parsed YAML value, keys included."""
    match value:
        case str() as text:
            yield text
        case dict() as mapping:
            for key, item in mapping.items():
                yield from _strings(key)
                yield from _strings(item)
        case list() as items:
            for item in items:
                yield from _strings(item)


def _declares_codescene(job: WorkflowJob) -> bool:
    """Return whether a job declares the ``codescene`` environment."""
    match job.get("environment"):
        case str() as name:
            return name.casefold() == CODESCENE_ENVIRONMENT
        case {"name": str() as name}:
            return name.casefold() == CODESCENE_ENVIRONMENT
        case _:
            return False


def _preinstalled_nextest(document: WorkflowDocument) -> list[str]:
    """Return every cargo-nextest version a workflow preinstalls."""
    return [
        match["version"]
        for job in _jobs(document).values()
        for step in _steps(job)
        for match in _NEXTEST_PIN.finditer(step.get("run") or "")
    ]


def test_the_publisher_never_cancels_a_superseded_run() -> None:
    """The publisher waits for a run it cannot cancel.

    A cancelled run abandons both its upload and its baseline write. The
    canonical group is the workflow-and-ref form the estate standardises
    on, keyed on the ref alone so every main run shares one queue; a job
    declaring its own group would be a second queue governing the same
    upload.
    """
    name, document, _job_name, _job = _publisher()
    concurrency = document.get("concurrency")
    assert isinstance(concurrency, dict), f"{name} declares no concurrency mapping"
    assert concurrency.get("group") == CANONICAL_GROUP, (
        f"{name} groups by {concurrency.get('group')!r}, not {CANONICAL_GROUP!r}"
    )
    assert concurrency.get("cancel-in-progress") is False, (
        f"{name} must set cancel-in-progress: false"
    )
    overrides = [
        job_name for job_name, job in _jobs(document).items() if "concurrency" in job
    ]
    assert not overrides, f"{name} declares concurrency on jobs {overrides}"


def _canonical_upload_step(job: WorkflowJob) -> WorkflowStep:
    """Assert the job's canonical token check and return its upload step."""
    steps = _steps(job)
    checks = [step for step in steps if step.get("id") == CHECK_STEP_ID]
    assert len(checks) == 1, f"expected one {CHECK_STEP_ID} step, found {checks}"
    check = checks[0]
    assert check.get("name") == CHECK_STEP_NAME, check
    assert check.get("run") == CHECK_COMMAND, check
    assert set(check) == {"name", "id", "run"}, check
    uploads = [step for step in steps if _action_of(step) == UPLOAD_ACTION]
    assert len(uploads) == 1, f"expected one upload step, found {uploads}"
    upload = uploads[0]
    assert upload.get("if") == UPLOAD_GUARD, upload.get("if")
    return upload


def _assert_token_scoped(
    document: WorkflowDocument, job: WorkflowJob, upload: WorkflowStep
) -> None:
    """Assert the secret is bound only by the uploader's token input.

    The check step's command names the secret in a comparison that GitHub
    evaluates before the shell starts, so it binds nothing. An ``env``
    entry would, and a composite action's nested steps inherit the calling
    step's environment, so the token may not sit in one at any level.
    """
    inputs = upload.get("with") or {}
    assert inputs.get("access-token") == TOKEN_INPUT, inputs.get("access-token")
    token_inputs = {
        key
        for key, value in inputs.items()
        if any("CS_ACCESS_TOKEN" in text for text in _strings(value))
    }
    assert token_inputs == {"access-token"}, token_inputs

    workflow_env = document.get("env") or {}
    job_env = job.get("env") or {}
    for scope, environment in (("workflow", workflow_env), ("job", job_env)):
        assert not any("CS_ACCESS_TOKEN" in text for text in _strings(environment)), (
            f"the token must not sit in the {scope} environment"
        )
    for step in _steps(job):
        step_env = step.get("env") or {}
        assert not any("CS_ACCESS_TOKEN" in text for text in _strings(step_env)), (
            f"the token must not sit in an environment: {step.get('name')!r}"
        )


def _assert_environment_boundary(
    name: str, job_name: str, document: WorkflowDocument
) -> None:
    """Assert the environment belongs to the publisher and no PR lane.

    The environment's deployment policy admits ``main`` alone, so a run on
    any other ref is refused rather than merely lacking the secret; the
    contracts add that no pull-request-reachable workflow may declare it.
    """
    declarations = [
        (workflow, declared_job)
        for workflow, candidate in DOCUMENTS.items()
        for declared_job, candidate_job in _jobs(candidate).items()
        if _declares_codescene(candidate_job)
    ]
    assert declarations == [(name, job_name)], (
        f"the environment must be declared by the publisher job alone: {declarations}"
    )

    publisher = typ.cast("dict[str | bool, object]", document)
    assert not serves_pull_requests(publisher), (
        f"{name} serves pull requests, so it may not hold the environment"
    )
    for other_name, candidate in DOCUMENTS.items():
        reachable = typ.cast("dict[str | bool, object]", candidate)
        if not serves_pull_requests(reachable):
            continue
        assert not [
            declared_job
            for declared_job, candidate_job in _jobs(candidate).items()
            if _declares_codescene(candidate_job)
        ], f"{other_name} is pull-request-reachable and declares the environment"


def test_the_codescene_token_check_is_canonical_and_scoped() -> None:
    """The token check has one shape, and its environment one owner.

    The shared checker finds the check step through whatever id the guard
    reads, so it accepts the estate's older spellings. This contract keeps
    the canonical spelling, because a second spelling is a second thing to
    audit and the guard has to read the same id either way.
    """
    name, document, job_name, job = _publisher()
    upload = _canonical_upload_step(job)
    _assert_token_scoped(document, job, upload)
    _assert_environment_boundary(name, job_name, document)


def test_the_pull_request_lane_keeps_a_comparable_ratchet_without_codescene() -> None:
    """The pull-request lane measures the same selection and touches no CodeScene.

    The ratchet is the whole of the coverage gate on this lane, so it
    compares this commit's report against the publisher's baseline. The
    format, output path, runner and feature set have to agree, or the
    comparison reports the difference between two builds. CodeScene
    belongs to the publisher alone: no action, token, CLI call or checksum
    input may appear here.
    """
    lane = DOCUMENTS[PULL_REQUEST_LANE]

    for text in _strings(lane):
        folded = text.casefold()
        assert "codescene" not in folded, text
        assert "cs_access_token" not in folded, text
        assert "cs-coverage" not in folded, text
    for job in _jobs(lane).values():
        for step in _steps(job):
            inputs = step.get("with") or {}
            checksums = [key for key in inputs if "checksum" in key.casefold()]
            assert not checksums, f"{step.get('name')!r} passes {checksums}"

    coverage = _coverage_step(lane)
    inputs = coverage.get("with") or {}
    assert inputs.get("with-ratchet") == "true", inputs
    assert inputs.get("publish-artefact") == "false", inputs

    assert _preinstalled_nextest(lane) == [COVERAGE_NEXTEST_VERSION], (
        "the lane must preinstall the runner the pinned action reuses"
    )
    publisher_name, publisher, _job_name, _job = _publisher()
    assert _preinstalled_nextest(publisher) == [], (
        f"{publisher_name} must let the coverage action install its own nextest"
    )

    pinned = f"{COVERAGE_ACTION}@{SHARED_ACTIONS_PIN}"
    for name, document in ((PULL_REQUEST_LANE, lane), (publisher_name, publisher)):
        assert _coverage_step(document).get("uses") == pinned, (
            f"{name} does not use the action the runner constant names"
        )
