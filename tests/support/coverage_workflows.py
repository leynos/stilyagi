"""Reads every coverage-invoking job out of the workflow files.

Separated from `tests/test_timeout_ordering_contract.py` so the reading
and the assertions over it stay legible apart. The shapes are modelled
only as far as this contract consumes them.

The acquisition lives in `workflow_documents`, and `WORKFLOWS_DIRECTORY`
and `workflow_documents` are re-exported here so a reader of a coverage
lane keeps one import.
"""

import typing as typ

from tests.support.workflow_documents import (
    WORKFLOWS_DIRECTORY,
    workflow_documents,
)
from tests.support.workflow_shapes import (
    WorkflowDocument,
    WorkflowJob,
    WorkflowStep,
    numeric_field,
)

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    from pathlib import Path

#: The environment variable the shared coverage action reads for its
#: wall-clock cap on one `cargo` invocation.
WATCHDOG_VARIABLE: typ.Final[str] = "RUN_RUST_CARGO_WAIT_TIMEOUT"

#: The action whose steps run under that watchdog.
COVERAGE_ACTION: typ.Final[str] = (
    "leynos/shared-actions/.github/actions/generate-coverage"
)


class JobLocation(typ.NamedTuple):
    """Where a budget was declared, for a fault message.

    The two names travel together everywhere a budget is read, and
    passing them separately pushed the reader past the argument count
    the repository's lint allows. Bundling them says they are one
    coordinate rather than two unrelated strings.

    Attributes
    ----------
    workflow : str
        The workflow file's name.
    job : str
        The job's identifier within it.
    """

    workflow: str
    job: str


class CoverageJob(typ.NamedTuple):
    """One job that invokes the coverage action, with its budgets.

    Attributes
    ----------
    workflow : str
        The workflow file's name.
    job : str
        The job's identifier.
    steps : int
        How many coverage steps the job runs. Each gets its own watchdog,
        so the job must contain all of their budgets.
    watchdogs : tuple[float | None, ...]
        The watchdog budget in force for each of those steps, in order,
        with None where neither the step nor the job sets one.
    job_timeout : float or None
        The job's ``timeout-minutes`` in seconds, or None when it
        declares none and so inherits GitHub's six-hour default.
    conditions : tuple[tuple[object, object], ...]
        The ``if`` on each coverage step and on its job, in step order.
        A skipped step runs no ``cargo``, so its watchdog never arms and
        the tiers below say nothing about it; the condition is therefore
        part of what identifies a lane rather than incidental to it.
    """

    workflow: str
    job: str
    steps: int
    watchdogs: tuple[float | None, ...]
    job_timeout: float | None
    conditions: tuple[tuple[object, object], ...] = ()

    def __str__(self) -> str:
        """Return a location suitable for a failure message.

        Returns
        -------
        str
            ``workflow:job`` for this job.
        """
        return f"{self.workflow}:{self.job}"


def _watchdog_of(
    document: WorkflowDocument,
    job: WorkflowJob,
    step: WorkflowStep,
    at: JobLocation,
) -> float | None:
    """Return the watchdog budget in force for one step.

    All three levels are read, innermost first, as GitHub resolves them.
    Both workflows here set the value at workflow level, so a contract
    reading only the job would find nothing and report every lane as
    inheriting the action's default, which is exactly backwards.

    Parameters
    ----------
    document : WorkflowDocument
        The whole workflow document.
    job : WorkflowJob
        The enclosing job.
    step : WorkflowStep
        The coverage step.
    at : JobLocation
        Where this is, for a fault message.

    Returns
    -------
    float or None
        The budget in seconds, or None when no level sets one.
        ``numeric_field`` raises through this function when a level
        declares a value that is neither blank nor a number.
    """
    # The innermost scope that declares the variable wins, blank
    # included. GitHub takes the most specific declaration, and an empty
    # string is one: a step setting the variable to "" hands that step's
    # process an empty value, not the job's. Reading past a blank would
    # credit the lane with a budget nothing enforces.
    #
    # A declared blank reads as None, the same as undeclared, because
    # neither bounds the cargo invocation. Anything else that is not a
    # number is reported rather than read as absent: a lane whose
    # watchdog is a `${{ }}` expression has a budget this contract
    # cannot evaluate, and calling it unset would credit the lane with
    # the action's default and certify an ordering nobody has checked.
    levels = (step.get("env"), job.get("env"), document.get("env"))
    for source in levels:
        environment = source or {}
        if WATCHDOG_VARIABLE not in environment:
            continue
        declared = environment[WATCHDOG_VARIABLE]
        text = str(declared).strip()
        if not text:
            return None
        return numeric_field(
            text, workflow=at.workflow, job=at.job, field=WATCHDOG_VARIABLE
        )
    return None


def _jobs_of(document: WorkflowDocument) -> dict[str, WorkflowJob]:
    """Return a document's jobs with a narrow test-local shape.

    Parameters
    ----------
    document : WorkflowDocument
        The parsed workflow document.

    A document that is not a mapping declares no jobs. The acquisition
    skips those files, but the query is reachable with any document a
    caller supplies, and a reading that raised on one would fail the
    whole contract on a workflow that has nothing to do with coverage.

    Returns
    -------
    dict[str, WorkflowJob]
        Job identifier to job, empty when the document declares none.
    """
    match document:
        case {"jobs": dict() as jobs}:
            return typ.cast("dict[str, WorkflowJob]", jobs)
        case _:
            return {}


def _coverage_steps(job: WorkflowJob) -> list[WorkflowStep]:
    """Return the steps in one job that invoke the coverage action.

    A job that is not a mapping runs no step, for the same reason that a
    document which is not a mapping declares no job. The shape cannot be
    read, so it contributes no lane rather than ending the contract.

    Parameters
    ----------
    job : WorkflowJob
        The parsed job.

    Returns
    -------
    list[WorkflowStep]
        The matching steps, in the order the job runs them.
    """
    match job:
        case {"steps": list() as steps}:
            return [step for step in map(_step, steps) if _invokes_coverage(step)]
        case _:
            return []


def _step(value: object) -> WorkflowStep:
    """Return one parsed step, or an empty one when it is not a mapping."""
    match value:
        case dict() as step:
            return typ.cast("WorkflowStep", step)
        case _:
            return typ.cast("WorkflowStep", {})


def _invokes_coverage(step: WorkflowStep) -> bool:
    """Return whether one step invokes the shared coverage action.

    The identifier is compared with the whole path before the ``@``
    rather than looked for inside it. A substring test accepts a
    sibling whose path merely begins with this one, such as a
    ``generate-coverage-v2``, so the contract would report the coverage
    action as present in a lane that no longer invokes it, and every
    assertion resting on that lane would pass over the wrong step.

    Returns
    -------
    bool
        True when the step invokes the shared coverage action itself.
    """
    uses = step.get("uses")
    match uses:
        case str():
            return uses.partition("@")[0] == COVERAGE_ACTION
        case _:
            return False


def _coverage_job(
    workflow: str,
    document: WorkflowDocument,
    job_name: str,
    job: WorkflowJob,
) -> CoverageJob | None:
    """Return one job's budgets, or None when it runs no coverage step.

    Parameters
    ----------
    workflow : str
        The workflow file's name.
    document : WorkflowDocument
        The enclosing document, read for a workflow-level watchdog.
    job_name : str
        The job's identifier.
    job : WorkflowJob
        The parsed job.

    Returns
    -------
    CoverageJob or None
        The job's budgets, or None when it invokes no coverage step.
        ``numeric_field`` raises through this function when either
        budget is declared as something other than a number.
    """
    steps = _coverage_steps(job)
    if not steps:
        return None
    at = JobLocation(workflow=workflow, job=job_name)
    raw_timeout = job.get("timeout-minutes")
    return CoverageJob(
        workflow=workflow,
        job=job_name,
        steps=len(steps),
        watchdogs=tuple(_watchdog_of(document, job, step, at) for step in steps),
        job_timeout=(
            None
            if raw_timeout is None
            else numeric_field(
                raw_timeout,
                workflow=at.workflow,
                job=at.job,
                field="timeout-minutes",
            )
            * 60.0
        ),
        conditions=tuple((step.get("if"), job.get("if")) for step in steps),
    )


def coverage_jobs_in(
    documents: cabc.Mapping[str, WorkflowDocument],
) -> tuple[CoverageJob, ...]:
    """Return every job in those documents that invokes the action.

    The query is separate from the acquisition so it can be driven with
    supplied documents. Reading the repository's own workflow directory
    inside the query left no way to ask what this reading makes of a
    lane that does not exist here, and a contract that can only be
    exercised against the tree it guards is one whose own behaviour goes
    unasserted.

    Jobs are the unit rather than steps, because the ceiling is a job's
    and it has to contain every watchdog inside it. Counting steps is
    what makes the two invocations here visible to the arithmetic.

    Parameters
    ----------
    documents : Mapping[str, WorkflowDocument]
        Workflow file name to parsed document.

    Returns
    -------
    tuple[CoverageJob, ...]
        One entry per coverage-invoking job.
    """
    return tuple(
        found
        for name, document in documents.items()
        for job_name, job in _jobs_of(document).items()
        if (found := _coverage_job(name, document, str(job_name), job)) is not None
    )


def coverage_jobs(directory: Path = WORKFLOWS_DIRECTORY) -> tuple[CoverageJob, ...]:
    """Return every job invoking the coverage action, with its budgets.

    This is the acquisition half: it reads the workflow files and hands
    the parsed documents to the query.

    Parameters
    ----------
    directory : Path
        Directory of workflow files. Defaults to the repository's own.

    Returns
    -------
    tuple[CoverageJob, ...]
        One entry per coverage-invoking job.
    """
    return coverage_jobs_in(workflow_documents(directory))
