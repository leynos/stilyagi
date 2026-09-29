"""Hold the workflows' Ubicloud placement to the files: expression and ceiling.

Ubicloud's cache proxy is scoped by ref, and a pull request from a fork cannot
obtain an Ubicloud runner at all. A lane that names an Ubicloud runner
therefore selects it by a runner-selection expression that falls back to the
hosted pool for a fork, and states its own ceiling, because an Ubicloud runner
is a self-hosted just-in-time runner that GitHub's six-hour cap for hosted jobs
does not bound.

The judgement is driven over constructed expressions in both directions before
the real files are asserted, because a check over this repository's own
correct workflows passes whether or not it discriminates anything.
"""

import re
import typing as typ

import pytest

from tests.support.workflows import WorkflowDocument, load_workflow

HOSTED_LABEL: typ.Final = "ubuntu-latest"
FORK_CONDITION: typ.Final = "github.event.pull_request.head.repo.fork"

#: Every job that can land on Ubicloud: workflow, job, runner class and the
#: ceiling it states in minutes. The inventory is exact, so a new Ubicloud lane
#: without a ceiling, or a class or ceiling changed, fails until reviewed.
PLACEMENTS: typ.Final = (
    ("coverage-main.yml", "coverage-upload", "ubicloud-standard-4", "60"),
    ("smoke.yml", "lint-test", "ubicloud-standard-4", "60"),
)

#: The runner-selection shape: a condition, a quoted hosted arm and a quoted
#: other arm.
_SHAPE: typ.Final = re.compile(
    r"\$\{\{\s*(?P<condition>[^&|]+?)\s*&&\s*'(?P<hosted>[^']*)'"
    r"\s*\|\|\s*'(?P<other>[^']*)'\s*\}\}"
)

type Origin = typ.Literal["push", "same-repository", "fork"]
ORIGINS: typ.Final[tuple[Origin, ...]] = ("push", "same-repository", "fork")


def runner_selection_expression(label: str) -> str:
    """Return the runner-selection expression for an Ubicloud `label`.

    Parameters
    ----------
    label
        The Ubicloud runner class a non-fork run selects.

    Returns
    -------
    str
        A `${{ ... }}` expression selecting `label` unless the run is a pull
        request from a fork, which falls back to the hosted pool.
    """
    return f"${{{{ {FORK_CONDITION} && '{HOSTED_LABEL}' || '{label}' }}}}"


def selected_runner(runs_on: object, origin: Origin) -> str | None:
    """Return the label a `runs-on` value selects for a run.

    Parameters
    ----------
    runs_on
        The job's `runs-on` value as parsed.
    origin
        The kind of run: a push or dispatch (no pull request), a pull request
        from this repository, or a pull request from a fork.

    Returns
    -------
    str | None
        The selected label, or None when the value is not the runner-selection
        shape. A literal label is not the shape: a lane that never falls back
        cannot serve a fork.
    """
    shape = _SHAPE.fullmatch(runs_on.strip()) if isinstance(runs_on, str) else None
    if shape is None or shape["condition"] != FORK_CONDITION:
        return None
    return shape["hosted" if origin == "fork" else "other"]


def placement_faults(runs_on: object, label: str) -> list[str]:
    """Return one entry per kind of run the expression places wrongly.

    Parameters
    ----------
    runs_on
        The job's `runs-on` value as parsed.
    label
        The Ubicloud runner class every non-fork run must select.

    Returns
    -------
    list[str]
        Empty when a fork falls back to hosted and every other run is on
        `label`.
    """
    wanted = {"push": label, "same-repository": label, "fork": HOSTED_LABEL}
    return [
        f"{origin} selects {selected_runner(runs_on, origin)}, wanted {wanted[origin]}"
        for origin in ORIGINS
        if selected_runner(runs_on, origin) != wanted[origin]
    ]


def _job_mappings(document: WorkflowDocument) -> list[tuple[str, dict[object, object]]]:
    """Return a workflow's jobs that are mappings, with their identifiers.

    Parameters
    ----------
    document
        A parsed workflow.

    Returns
    -------
    list[tuple[str, dict[object, object]]]
        Job identifier and job mapping, in file order; empty when the
        workflow has no `jobs` mapping.
    """
    jobs = document.get("jobs")
    if not isinstance(jobs, dict):
        return []
    return [(str(job_id), job) for job_id, job in jobs.items() if isinstance(job, dict)]


def placed_jobs(
    documents: dict[str, WorkflowDocument],
) -> list[tuple[str, str, object, object]]:
    """Return every job whose `runs-on` names Ubicloud.

    Parameters
    ----------
    documents
        Parsed workflows keyed by file name.

    Returns
    -------
    list[tuple[str, str, object, object]]
        Workflow, job, `runs-on` value and the `timeout-minutes` it states
        (None when it states none), in file and job order.
    """
    return [
        (name, job_id, job.get("runs-on"), job.get("timeout-minutes"))
        for name, document in sorted(documents.items())
        for job_id, job in _job_mappings(document)
        if "ubicloud" in str(job.get("runs-on", ""))
    ]


@pytest.mark.parametrize(
    ("origin", "wanted"),
    [
        ("push", "ubicloud-standard-2"),
        ("same-repository", "ubicloud-standard-2"),
        ("fork", "ubuntu-latest"),
    ],
)
def test_the_expression_places_each_run(origin: Origin, wanted: str) -> None:
    """Place a push, a dispatch and a same-repository pull request on Ubicloud.

    Parameters
    ----------
    origin
        The kind of run.
    wanted
        The label the run must select; only a fork's pull request is hosted.
    """
    selected = selected_runner(
        runner_selection_expression("ubicloud-standard-2"), origin
    )
    assert selected == wanted, f"{origin} selected {selected}, wanted {wanted}"


@pytest.mark.parametrize(
    ("runs_on", "expected"),
    [
        (runner_selection_expression("ubicloud-standard-2"), 0),
        ("ubuntu-latest", 3),
        ("ubicloud-standard-2", 3),
        (
            f"${{{{ {FORK_CONDITION} && 'ubicloud-standard-2' || 'ubuntu-latest' }}}}",
            3,
        ),
        (runner_selection_expression("ubicloud-standard-4"), 2),
        (
            (
                "${{ github.event_name == 'pull_request' && 'ubuntu-latest' "
                "|| 'ubicloud-standard-2' }}"
            ),
            3,
        ),
        (
            (
                f"${{{{ {FORK_CONDITION} && 'ubicloud-standard-2' "
                "|| 'ubicloud-standard-2' }}"
            ),
            1,
        ),
        (["ubicloud-standard-2"], 3),
        (None, 3),
    ],
    ids=[
        "runner-selection",
        "always-hosted",
        "always-ubicloud",
        "inverted-arms",
        "another-label",
        "another-condition",
        "fork-kept-on-ubicloud",
        "sequence",
        "not-a-string",
    ],
)
def test_a_misplaced_lane_is_reported(runs_on: object, expected: int) -> None:
    """Report each careless edit, and not the runner-selection expression.

    Parameters
    ----------
    runs_on
        A `runs-on` value to judge.
    expected
        How many kinds of run it places wrongly.
    """
    faults = placement_faults(runs_on, "ubicloud-standard-2")
    assert len(faults) == expected, f"expected {expected}, saw {faults}"


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("    timeout-minutes: 30\n", "30"),
        ("", None),
        ("    timeout-minutes: thirty\n", "thirty"),
    ],
    ids=["stated", "missing", "a-string"],
)
def test_a_ceiling_is_read_as_the_file_states_it(key: str, expected: object) -> None:
    """Read the ceiling verbatim, so a wrong one cannot pass the inventory.

    Parameters
    ----------
    key
        The `timeout-minutes` line a constructed job carries, or nothing.
    expected
        What the inventory must report for it.
    """
    expression = runner_selection_expression("ubicloud-standard-2")
    text = f"jobs:\n  lane:\n    runs-on: {expression}\n{key}"
    placed = placed_jobs({"x.yml": load_workflow(text)})
    assert placed == [("x.yml", "lane", expression, expected)], f"read {placed}"


def test_a_hosted_job_is_not_inventoried() -> None:
    """Leave a hosted lane outside the inventory, since it needs no ceiling."""
    document = load_workflow("jobs:\n  lane:\n    runs-on: ubuntu-latest\n")
    placed = placed_jobs({"x.yml": document})
    assert not placed, f"a hosted job was inventoried: {placed}"


def test_every_ubicloud_lane_is_placed_by_the_expression_and_states_a_ceiling(
    documents: dict[str, WorkflowDocument],
) -> None:
    """Find exactly the inventoried jobs, each placed and each with a ceiling.

    The reader loads every scalar as a string, so a ceiling is compared as the
    text the file states.

    Parameters
    ----------
    documents
        This repository's workflows, parsed once for the session.
    """
    placed = placed_jobs(documents)
    found = [(name, job, ceiling) for name, job, _, ceiling in placed]
    expected = [(name, job, ceiling) for name, job, _, ceiling in PLACEMENTS]
    assert found == expected, f"found {found}, expected {expected}"
    for (name, job, runs_on, _), (_, _, label, _) in zip(
        placed, PLACEMENTS, strict=True
    ):
        assert not placement_faults(runs_on, label), f"{name}: {job} is misplaced"
