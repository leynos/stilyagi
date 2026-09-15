"""The workflow shapes these contracts read, and the fault reading one.

Separated from ``coverage_workflows`` so the reading and the shapes it
reads stay legible apart, and so neither module outgrows the 400-line
limit ``AGENTS.md`` sets. The shapes are modelled only as far as the
contracts consume them.
"""

import typing as typ

if typ.TYPE_CHECKING:
    from pathlib import Path


class WorkflowReadingError(OSError):
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
