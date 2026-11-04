"""Read one step of the release workflow and run its script.

``release.yml`` keeps every decision in ``scripts/release_assets.py`` and
every network call in a ``curl`` or ``gh`` invocation, so what a test can
usefully assert about the workflow itself is which steps exist, what each
step hands to the next, and what its script does with the files it is
given. This module supplies those readings and one way to execute a
step's script.

Nothing here builds a workflow document of its own: the document is read
by ``tests/support/workflows.load_workflow`` like every other contract's,
so the unique-key refusal and the typed scalars hold here too.

A missing job, step or key is a `ReadingError` naming the reading rather
than an `AssertionError` from a helper: the contract that called the
reading decides whether the absence is a failure, and it says so in its
own vocabulary. Running a step's script is `tests.support.release_steps`'
job; this module only reads the document that supplies it.
"""

import pathlib
import typing as typ

from tests.support.errors import ReadingError

if typ.TYPE_CHECKING:
    from tests.support.workflows import WorkflowDocument

READER: typ.Final = "release workflow"
RELEASE_WORKFLOW: typ.Final = "release.yml"
BUILD_WHEELS_WORKFLOW: typ.Final = "build-wheels.yml"
BASH: typ.Final = "/usr/bin/env bash"
REPOSITORY_ROOT: typ.Final = pathlib.Path(__file__).resolve().parents[2]


def workflow_job(document: WorkflowDocument, job: str) -> dict[str, object]:
    """Return one job mapping from a parsed workflow.

    Parameters
    ----------
    document
        A parsed workflow document.
    job
        The job identifier to return.

    Returns
    -------
    dict[str, object]
        The job's mapping.

    Raises
    ------
    ReadingError
        If the workflow declares no such job, or it is not a mapping.
    """
    jobs = document.get("jobs")
    if not isinstance(jobs, dict):
        msg = f"{RELEASE_WORKFLOW} declares no jobs"
        raise ReadingError(msg, reader=READER, path=RELEASE_WORKFLOW)
    found = jobs.get(job)
    if not isinstance(found, dict):
        msg = f"{RELEASE_WORKFLOW} declares no job {job!r}"
        raise ReadingError(msg, reader=READER, path=RELEASE_WORKFLOW)
    return found


def step(job: dict[str, object], name: str) -> dict[str, object]:
    """Return the step with `name` from a job.

    Parameters
    ----------
    job
        A parsed job mapping.
    name
        The step's ``name``.

    Returns
    -------
    dict[str, object]
        The step's mapping.

    Raises
    ------
    ReadingError
        If the job declares no such step.
    """
    steps = job.get("steps") or []
    if not isinstance(steps, list):
        msg = f"a job's steps must be a list, not {type(steps).__name__}"
        raise ReadingError(msg, reader=READER, path=RELEASE_WORKFLOW)
    for candidate in steps:
        if isinstance(candidate, dict) and candidate.get("name") == name:
            return candidate
    available = [s.get("name") for s in steps if isinstance(s, dict)]
    msg = f"no step named {name!r}; available steps: {available!r}"
    raise ReadingError(msg, reader=READER, path=RELEASE_WORKFLOW)


def step_script(job: dict[str, object], name: str) -> str:
    """Return a named step's shell script, refusing a step that has none.

    Parameters
    ----------
    job
        A parsed job mapping.
    name
        The step's ``name``.

    Returns
    -------
    str
        The step's ``run`` script.

    Raises
    ------
    ReadingError
        If the step carries no ``run`` key.
    """
    script = step(job, name).get("run")
    if not isinstance(script, str):
        msg = f"step {name!r} carries no run script"
        raise ReadingError(msg, reader=READER, path=RELEASE_WORKFLOW)
    return script


def step_ids(job: dict[str, object]) -> set[str]:
    """Return every ``id`` a job's steps declare.

    Parameters
    ----------
    job
        A parsed job mapping.

    Returns
    -------
    set[str]
        The declared step identifiers; empty when none are declared.
    """
    declared = job.get("steps") or []
    steps: list[object] = list(declared) if isinstance(declared, list) else []
    return {
        str(step["id"]) for step in steps if isinstance(step, dict) and "id" in step
    }


def outputs(job: dict[str, object]) -> dict[str, str]:
    """Return a job's declared ``outputs`` mapping, empty when it has none.

    Parameters
    ----------
    job
        A parsed job mapping.

    Returns
    -------
    dict[str, str]
        Each output's name and the expression producing it.

    Raises
    ------
    ReadingError
        If ``outputs`` is present and is not a mapping.
    """
    declared = job.get("outputs")
    if declared is None:
        return {}
    if not isinstance(declared, dict):
        msg = f"a job's outputs must be a mapping, not {type(declared).__name__}"
        raise ReadingError(msg, reader=READER, path=RELEASE_WORKFLOW)
    return typ.cast("dict[str, str]", declared)


def link_scripts(root: pathlib.Path, destination: pathlib.Path) -> None:
    """Link this repository's release scripts into ``destination``.

    The publishing jobs check out ``scripts/`` with a sparse checkout and
    run ``PYTHONPATH=scripts python3 -m release_assets_cli`` from the
    workspace root, so a test that executes a step must give it the same
    layout. Linking rather than copying keeps the executed code the code
    under test.

    Parameters
    ----------
    root
        The repository root holding ``scripts/``.
    destination
        The directory to link ``destination/scripts`` into.
    """
    source = root / "scripts"
    target = destination / "scripts"
    target.mkdir(parents=True, exist_ok=True)
    for module in sorted(source.glob("*.py")):
        (target / module.name).symlink_to(module)


def github_output(path: pathlib.Path) -> dict[str, str]:
    """Return the step outputs written to a ``GITHUB_OUTPUT`` file.

    Parameters
    ----------
    path
        The file the step appended to.

    Returns
    -------
    dict[str, str]
        Each ``name=value`` line, last value winning, as GitHub reads it.
    """
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        name, separator, value = line.partition("=")
        if separator:
            values[name] = value
    return values
