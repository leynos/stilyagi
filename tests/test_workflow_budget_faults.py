"""What the coverage-lane reading does with a budget it cannot read.

Both numeric fields come out of YAML as whatever was written, and a
`${{ }}` expression is the case that matters: GitHub substitutes it at
run time and this contract cannot. Reading such a value as absent would
credit the job with the shared action's default watchdog, or with
GitHub's six-hour ceiling, and every ordering assertion would then pass
over a budget nobody has checked.

Converting it raw is the other wrong answer, which is why the fault
carries the workflow, the job, the field and the value rather than
leaving a reader to search the tree for a number.

Separate from `test_coverage_workflow_reading` so neither module
outgrows the 400-line limit ``AGENTS.md`` sets.
"""

import pytest

from tests.support.coverage_workflows import WATCHDOG_VARIABLE, coverage_jobs_in
from tests.support.workflow_shapes import WorkflowConfigurationError, WorkflowError
from tests.test_coverage_workflow_reading import workflow


@pytest.mark.parametrize(
    ("scopes", "field"),
    [
        pytest.param(
            {"workflow_env": "${{ env.WAIT }}"},
            WATCHDOG_VARIABLE,
            id="a-watchdog-expression-at-workflow-level",
        ),
        pytest.param(
            {"job_env": "${{ env.WAIT }}"},
            WATCHDOG_VARIABLE,
            id="a-watchdog-expression-at-job-level",
        ),
        pytest.param(
            {"step_env": "${{ env.WAIT }}"},
            WATCHDOG_VARIABLE,
            id="a-watchdog-expression-at-step-level",
        ),
        pytest.param(
            {"workflow_env": "ten minutes"},
            WATCHDOG_VARIABLE,
            id="a-watchdog-written-in-words",
        ),
        pytest.param(
            {"ceiling": "${{ env.CEILING }}"},
            "timeout-minutes",
            id="a-ceiling-expression",
        ),
    ],
)
def test_a_budget_that_is_not_a_number_is_reported_where_it_is_declared(
    scopes: dict[str, str], field: str
) -> None:
    """A budget the reading cannot evaluate is named, not swallowed.

    Both numeric fields come out of YAML as whatever was written, and a
    `${{ }}` expression is the case that matters: GitHub substitutes it
    at run time and this contract cannot. Reading such a value as absent
    would credit the job with the action's default watchdog, or with
    GitHub's six-hour ceiling, and every ordering assertion would then
    pass over a budget nobody has checked.

    Converting it raw is the other wrong answer. `float` reports the
    text and nothing else, so a failure in a tree of workflows would
    name neither the file, nor the job, nor which of the two fields it
    came from. Each is asserted here.
    """
    with pytest.raises(WorkflowConfigurationError) as raised:
        coverage_jobs_in({"controlled.yml": workflow(scopes)})
    assert raised.value.workflow == "controlled.yml", raised.value
    assert raised.value.job == "coverage", raised.value
    assert raised.value.field == field, raised.value
    assert str(raised.value.value) in str(raised.value), raised.value
    assert isinstance(raised.value, WorkflowError), (
        "the fault must join the workflow family, so a caller catching that "
        "family keeps catching this one"
    )


def test_a_ceiling_that_is_not_a_scalar_is_reported_too() -> None:
    """The conversion fails by type as well as by value.

    `float` raises `TypeError` for a list and `ValueError` for text, and
    a reading that caught only the second would let a `timeout-minutes`
    written as a YAML list escape as an unhandled `TypeError` naming
    nothing. Both are caught, and this is the case that says so.
    """
    document_with_list = workflow()
    document_with_list["jobs"]["coverage"]["timeout-minutes"] = [90]
    with pytest.raises(WorkflowConfigurationError) as raised:
        coverage_jobs_in({"controlled.yml": document_with_list})
    assert raised.value.field == "timeout-minutes", raised.value
    assert raised.value.value == [90], raised.value


@pytest.mark.parametrize(
    "value",
    [pytest.param("true", id="true"), pytest.param("false", id="false")],
)
def test_a_boolean_ceiling_is_refused_rather_than_converted(value: str) -> None:
    """YAML's bare `true` and `false` are Booleans, and `float` takes them.

    `bool` subclasses `int` in Python and does not in YAML, so a match
    arm written as `int()` catches them and `float()` turns them into a
    one-minute and a zero-minute ceiling. Either reads as a ceiling that
    is present and correctly ordered below everything above it, and
    either would cancel the lane before it had begun. A Boolean is not a
    budget, so it is refused where it is declared.
    """
    with pytest.raises(WorkflowConfigurationError) as raised:
        coverage_jobs_in({"controlled.yml": workflow({"ceiling": value})})
    assert raised.value.field == "timeout-minutes", raised.value
    assert raised.value.value is (value == "true"), (
        f"the fault must carry the Boolean it refused, not its text: "
        f"{raised.value.value!r}"
    )
