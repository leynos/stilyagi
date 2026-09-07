"""Reads every coverage-invoking job out of the workflow files.

Separated from `tests/test_timeout_ordering_contract.py` so the reading
and the assertions over it stay legible apart. The shapes are modelled
only as far as this contract consumes them.
"""

import typing as typ
from pathlib import Path

import yaml

WORKFLOWS_DIRECTORY: typ.Final[Path] = (
    Path(__file__).resolve().parents[2] / ".github" / "workflows"
)

#: The environment variable the shared coverage action reads for its
#: wall-clock cap on one `cargo` invocation.
WATCHDOG_VARIABLE: typ.Final[str] = "RUN_RUST_CARGO_WAIT_TIMEOUT"

#: The action whose steps run under that watchdog.
COVERAGE_ACTION: typ.Final[str] = (
    "leynos/shared-actions/.github/actions/generate-coverage"
)


class WorkflowStep(typ.TypedDict, total=False):
    """One step of a workflow job, as this contract reads it.

    Only the keys consumed here are modelled, and all are optional: a
    step that neither uses an action nor sets an environment has
    neither.

    Attributes
    ----------
    uses : str
        The action the step invokes, when it invokes one.
    env : dict[str, object]
        The step-level environment.
    """

    uses: str
    env: dict[str, object]


#: One job of a workflow. Written in the functional form because
#: ``timeout-minutes`` is not a Python identifier and so cannot be a
#: class attribute.
WorkflowJob = typ.TypedDict(
    "WorkflowJob",
    {
        "timeout-minutes": float,
        "env": dict[str, object],
        "steps": list[WorkflowStep],
    },
    total=False,
)


class WorkflowDocument(typ.TypedDict, total=False):
    """One workflow file, as this contract reads it.

    Attributes
    ----------
    env : dict[str, object]
        The workflow-level environment, where both workflows here set
        the watchdog.
    jobs : dict[str, WorkflowJob]
        The workflow's jobs, keyed by identifier.
    """

    env: dict[str, object]
    jobs: dict[str, WorkflowJob]


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

    Returns
    -------
    float or None
        The budget in seconds, or None when no level sets one.
    """
    levels = (step.get("env"), job.get("env"), document.get("env"))
    for source in levels:
        raw = (source or {}).get(WATCHDOG_VARIABLE)
        if raw is not None:
            return float(str(raw))
    return None


def _workflow_documents() -> dict[str, WorkflowDocument]:
    """Return every workflow document, keyed by file name.

    Both extensions are read. A coverage lane in the other one would
    otherwise escape every assertion below without failing anything.

    Returns
    -------
    dict[str, WorkflowDocument]
        File name to parsed document.
    """
    documents: dict[str, WorkflowDocument] = {}
    for pattern in ("*.yml", "*.yaml"):
        for path in sorted(WORKFLOWS_DIRECTORY.glob(pattern)):
            parsed: object = yaml.safe_load(path.read_text(encoding="utf-8"))
            if isinstance(parsed, dict):
                documents[path.name] = typ.cast("WorkflowDocument", parsed)
    return documents


def _jobs_of(document: WorkflowDocument) -> dict[str, WorkflowJob]:
    """Return a document's jobs with a narrow test-local shape.

    Parameters
    ----------
    document : WorkflowDocument
        The parsed workflow document.

    Returns
    -------
    dict[str, WorkflowJob]
        Job identifier to job, empty when the document declares none.
    """
    jobs: object = document.get("jobs")
    if not isinstance(jobs, dict):
        return {}
    return typ.cast("dict[str, WorkflowJob]", jobs)


def _coverage_steps(job: WorkflowJob) -> list[WorkflowStep]:
    """Return the steps in one job that invoke the coverage action.

    Parameters
    ----------
    job : WorkflowJob
        The parsed job.

    Returns
    -------
    list[WorkflowStep]
        The matching steps, in the order the job runs them.
    """
    steps: object = job.get("steps")
    if not isinstance(steps, list):
        return []
    return [
        typ.cast("WorkflowStep", step)
        for step in typ.cast("list[object]", steps)
        if isinstance(step, dict) and COVERAGE_ACTION in str(step.get("uses", ""))
    ]


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
    """
    steps = _coverage_steps(job)
    if not steps:
        return None
    raw_timeout = job.get("timeout-minutes")
    return CoverageJob(
        workflow=workflow,
        job=job_name,
        steps=len(steps),
        watchdogs=tuple(_watchdog_of(document, job, step) for step in steps),
        job_timeout=None if raw_timeout is None else float(raw_timeout) * 60.0,
        conditions=tuple((step.get("if"), job.get("if")) for step in steps),
    )


def coverage_jobs() -> tuple[CoverageJob, ...]:
    """Return every job invoking the coverage action, with its budgets.

    Jobs are the unit rather than steps, because the ceiling is a job's
    and it has to contain every watchdog inside it. Counting steps is
    what makes the two invocations here visible to the arithmetic.

    Returns
    -------
    tuple[CoverageJob, ...]
        One entry per coverage-invoking job.
    """
    return tuple(
        found
        for name, document in _workflow_documents().items()
        for job_name, job in _jobs_of(document).items()
        if (found := _coverage_job(name, document, str(job_name), job)) is not None
    )
