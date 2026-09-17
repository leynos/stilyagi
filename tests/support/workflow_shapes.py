"""The workflow shapes these contracts read, and the fault reading one.

Separated from ``coverage_workflows`` so the reading and the shapes it
reads stay legible apart, and so neither module outgrows the 400-line
limit ``AGENTS.md`` sets. The shapes are modelled only as far as the
contracts consume them.
"""

import typing as typ

if typ.TYPE_CHECKING:
    from pathlib import Path


class WorkflowError(OSError):
    """Base for every fault this package raises about a workflow file.

    The repository's exception rule asks for a domain base so a caller
    can catch the family without naming each member, and the two other
    error families in ``tests/support`` are shaped that way:
    ``TimeoutBudgetError`` and ``RoundTripEditError`` each sit above
    their concrete errors. This one keeps ``OSError`` as its own base,
    because acquisition failures here are operating-system failures and
    a caller already catching ``OSError`` should keep catching them.
    """


class WorkflowReadingError(WorkflowError):
    """Raised when a workflow file cannot be read or parsed.

    Acquisition is fallible in two ways the query above it is not: the
    file may not be readable, and its text may not be YAML. Letting
    either escape raw reports a scanner error naming a line number, or
    an errno, with nothing saying which workflow or that the failure
    was in acquisition at all. Reporting the path and chaining the
    cause is what makes the failure actionable, and it keeps the query
    free of the question, since a document it is handed has already
    parsed.

    Attributes
    ----------
    path : Path
        The workflow file the fault is about.
    """

    def __init__(self, message: str, *, path: Path) -> None:
        """Record the message and the file it is about.

        Parameters
        ----------
        message : str
            What went wrong, for a person reading the failure.
        path : Path
            The workflow file that could not be read.
        """
        super().__init__(message)
        self.path = path


class WorkflowConfigurationError(WorkflowError):
    """Raised when a workflow declares a budget that is not a number.

    The query above acquisition reads two numeric fields out of YAML,
    ``timeout-minutes`` and the watchdog variable, and YAML hands back
    whatever was written: a list, a mapping, or a ``${{ }}`` expression
    this contract cannot evaluate. Converting one raw would report a
    ``ValueError`` naming the text and nothing else, with no workflow,
    no job and no field, and a reader would have to guess which of the
    tree's lanes it came from.

    Treating such a value as absent is worse than raising. A lane whose
    watchdog is an expression is a lane whose budget is unknown, and
    reporting it as unset credits the job with the action's default and
    certifies an ordering nobody has checked.

    Attributes
    ----------
    workflow : str
        The workflow file the fault is about.
    job : str
        The job within it.
    field : str
        Which budget could not be read.
    value : object
        The value as the document supplied it.
    """

    def __init__(self, *, workflow: str, job: str, field: str, value: object) -> None:
        """Record where the unreadable budget was declared.

        Parameters
        ----------
        workflow : str
            The workflow file's name.
        job : str
            The job's identifier.
        field : str
            Which budget could not be read.
        value : object
            The value as the document supplied it.
        """
        message = (
            f"{workflow}:{job} declares {field} as {value!r}, which is not a "
            f"number; a budget this contract cannot read is a budget nobody "
            f"has checked, and reading it as absent would credit the lane "
            f"with a default instead"
        )
        super().__init__(message)
        self.workflow = workflow
        self.job = job
        self.field = field
        self.value = value


def numeric_field(value: object, *, workflow: str, job: str, field: str) -> float:
    """Return one workflow field as a number, or say where it was not.

    Conversion happens here, at the boundary between the parsed document
    and the budgets the contract compares, so that nothing downstream
    receives a value it has to re-check. A raw ``float()`` would report
    a ``ValueError`` naming the text alone, with no workflow, no job and
    no field, and a reader of the failure would have to search the tree
    for it.

    Parameters
    ----------
    value : object
        The value as the document supplied it.
    workflow : str
        The workflow file's name.
    job : str
        The job's identifier.
    field : str
        Which budget is being read.

    Returns
    -------
    float
        The value as a number.

    Raises
    ------
    WorkflowConfigurationError
        If the value is not one, an expression included.
    """
    # The shape is narrowed before the conversion rather than after.
    # `float` raises `TypeError` for a `timeout-minutes` written as a
    # YAML list and `ValueError` for one written as text, and catching
    # only the second would let the first escape naming nothing; a match
    # refuses both by shape and leaves the conversion with a value it
    # can take, which is also what keeps the type checker satisfied
    # without a suppression.
    match value:
        case bool():
            # Answered before `int`, which `bool` subclasses in Python
            # and does not in YAML. A bare `true` or `false` is a
            # Boolean, and `float()` turns them into a 1 s and a 0 s
            # budget: a ceiling of one second reads as present and
            # ordered, and would cancel the lane almost immediately.
            raise WorkflowConfigurationError(
                workflow=workflow, job=job, field=field, value=value
            )
        case int() | float() | str():
            try:
                return float(value)
            except ValueError as error:
                raise WorkflowConfigurationError(
                    workflow=workflow, job=job, field=field, value=value
                ) from error
        case _:
            raise WorkflowConfigurationError(
                workflow=workflow, job=job, field=field, value=value
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
