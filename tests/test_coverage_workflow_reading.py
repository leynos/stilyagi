"""What the coverage-lane reading makes of workflows this repository lacks.

`coverage_workflows.coverage_jobs_in` decides which jobs the timeout
ordering contract asserts over, and what each job's budgets are. The two
coverage lanes in this repository are both well formed and both set the
watchdog at workflow level, so the real files cannot tell a correct
reading from several wrong ones: one that read only the job's
environment, one that counted a non-coverage step, one that raised on a
malformed document, or one that reported a missing ceiling as zero.

Each case here is a workflow this repository does not have, supplied to
the reading directly, so the behaviour is asserted rather than inferred
from a green contract.
"""

import typing as typ

import pytest
import yaml

from tests.support.coverage_workflows import (
    COVERAGE_ACTION,
    WATCHDOG_VARIABLE,
    CoverageJob,
    coverage_jobs,
    coverage_jobs_in,
    workflow_documents,
)
from tests.support.workflow_shapes import WorkflowError, WorkflowReadingError

if typ.TYPE_CHECKING:
    import pathlib

    from tests.support.coverage_workflows import WorkflowDocument


def document(text: str) -> WorkflowDocument:
    """Return one workflow document, parsed.

    Parameters
    ----------
    text : str
        A workflow file's text.

    Returns
    -------
    WorkflowDocument
        The parsed document.
    """
    return typ.cast("WorkflowDocument", yaml.safe_load(text))


def workflow(
    scopes: dict[str, str] | None = None,
    *,
    step_uses: str = COVERAGE_ACTION + "@abc123",
) -> WorkflowDocument:
    """Return a one-job workflow with the named scopes populated.

    Parameters
    ----------
    scopes : dict[str, str] or None
        Any of ``workflow_env``, ``job_env`` and ``step_env`` holding a
        watchdog value, and ``ceiling`` holding a ``timeout-minutes``.
        A scope not named here is left unset.
    step_uses : str
        What the single step invokes.

    Returns
    -------
    WorkflowDocument
        The parsed document.
    """
    # Membership, not truthiness. An empty string is a declaration GitHub
    # honours, and a builder testing `if given.get(...)` cannot express
    # it: the scope is simply omitted and the case silently becomes the
    # absent one. The contract could not have caught a blank-skipping
    # reader while its own fixture could not construct a blank.
    given = scopes or {}
    lines = ["name: controlled", "on: push"]
    if "workflow_env" in given:
        lines += ["env:", f'  {WATCHDOG_VARIABLE}: "{given["workflow_env"]}"']
    lines += ["jobs:", "  coverage:", "    runs-on: ubuntu-latest"]
    if "ceiling" in given:
        # Membership here too, and for the same reason the comment above
        # gives. Written as `if ceiling := given.get(...)` this arm
        # dropped a blank ceiling, so `timeout-minutes:` with nothing
        # after it could not be built at all and the case it represents
        # could not be tested. That is the shape a reader keyed on
        # `get(...) is None` confuses with an absent key.
        lines.append(f"    timeout-minutes: {given['ceiling']}")
    if "job_env" in given:
        lines += ["    env:", f'      {WATCHDOG_VARIABLE}: "{given["job_env"]}"']
    lines += ["    steps:", f"      - uses: {step_uses}"]
    if "step_env" in given:
        lines += [
            "        env:",
            f'          {WATCHDOG_VARIABLE}: "{given["step_env"]}"',
        ]
    return document("\n".join(lines) + "\n")


def only_job(documents: dict[str, WorkflowDocument]) -> CoverageJob:
    """Return the single coverage job the reading finds.

    Parameters
    ----------
    documents : dict[str, WorkflowDocument]
        Workflow file name to parsed document.

    Returns
    -------
    CoverageJob
        The one job found.
    """
    found = coverage_jobs_in(documents)
    assert len(found) == 1, found
    return found[0]


@pytest.mark.parametrize(
    ("scopes", "expected"),
    [
        pytest.param(
            {"workflow_env": "900", "job_env": "600", "step_env": "300"},
            300.0,
            id="the-step-wins-over-both",
        ),
        pytest.param(
            {"workflow_env": "900", "job_env": "600"},
            600.0,
            id="the-job-wins-over-the-workflow",
        ),
        pytest.param({"workflow_env": "900"}, 900.0, id="the-workflow-alone"),
        pytest.param({}, None, id="no-scope-sets-one"),
        pytest.param(
            {"workflow_env": "900", "job_env": "600", "step_env": ""},
            None,
            id="a-step-declaring-it-empty-beats-both",
        ),
        pytest.param(
            {"workflow_env": "900", "job_env": ""},
            None,
            id="a-job-declaring-it-empty-beats-the-workflow",
        ),
    ],
)
def test_the_watchdog_is_read_innermost_first(
    scopes: dict[str, str], expected: float | None
) -> None:
    """GitHub resolves step over job over workflow, and so must this.

    Both lanes here set the value at workflow level only, so a reading
    confined to the job would report every lane as inheriting the
    action's undocumented default while a budget is in force, which is
    exactly the inversion the ordering contract exists to catch.

    A blank is a declaration, not an absence. GitHub takes the most
    specific declaration, so a step setting the variable to "" hands
    that step's process an empty value rather than the job's number. It
    reads as None here, the same as undeclared, because neither bounds
    the cargo invocation; what must not happen is the reading passing a
    blank and crediting the lane with an outer scope's budget.
    """
    job = only_job({"controlled.yml": workflow(scopes)})
    assert job.watchdogs == (expected,), job


def test_a_missing_ceiling_reads_as_absent_rather_than_zero() -> None:
    """A job with no ``timeout-minutes`` inherits GitHub's six hours.

    Reading it as zero would make every ordering comparison against it
    fail for the wrong reason, and reading it as some default would
    certify a lane nobody had bounded.
    """
    assert only_job({"controlled.yml": workflow()}).job_timeout is None, (
        "a job declaring no ceiling must read as absent"
    )


def test_a_ceiling_is_read_as_seconds() -> None:
    """The tiers are compared in seconds, and minutes are what GitHub takes."""
    job = only_job({"controlled.yml": workflow({"ceiling": "45"})})
    assert job.job_timeout == pytest.approx(2700.0), (
        "45 minutes must read as 2,700 seconds"
    )


def test_a_job_invoking_no_coverage_step_is_not_a_lane() -> None:
    """The contract is about lanes that run the action, not every job.

    A job counted here would be held to budgets that say nothing about
    it, and the failure would name a job whose change would fix nothing.
    """
    documents = {"controlled.yml": workflow(step_uses="actions/checkout@v5")}
    assert not coverage_jobs_in(documents), (
        "a job invoking no coverage step is not a coverage lane"
    )


@pytest.mark.parametrize(
    "text",
    [
        pytest.param("- not a mapping\n", id="a-document-that-is-a-list"),
        pytest.param("just a string\n", id="a-document-that-is-a-scalar"),
        pytest.param("name: controlled\njobs: []\n", id="jobs-that-are-not-a-mapping"),
        pytest.param(
            "name: controlled\njobs:\n  coverage: 3\n", id="a-job-that-is-not-a-mapping"
        ),
        pytest.param(
            "name: controlled\njobs:\n  coverage:\n    steps: 3\n",
            id="steps-that-are-not-a-list",
        ),
        pytest.param(
            "name: controlled\njobs:\n  coverage:\n    steps:\n      - 3\n",
            id="a-step-that-is-not-a-mapping",
        ),
    ],
)
def test_a_malformed_document_yields_no_lane_rather_than_raising(text: str) -> None:
    """A file that declares no job declares no coverage lane.

    Raising here would fail the whole contract on a workflow that has
    nothing to do with coverage, so the shape that cannot be read
    contributes nothing instead.
    """
    assert not coverage_jobs_in({"controlled.yml": document(text)}), (
        "a shape that cannot be read must contribute no lane"
    )


def test_both_workflow_extensions_are_read(tmp_path: pathlib.Path) -> None:
    """GitHub accepts ``.yaml`` as readily as ``.yml``.

    Scanning one extension would let a coverage lane in the other escape
    every assertion the ordering contract makes, without failing
    anything.
    """
    for name in ("first.yml", "second.yaml", "notes.txt"):
        (tmp_path / name).write_text(
            "name: controlled\non: push\njobs:\n  coverage:\n"
            "    runs-on: ubuntu-latest\n    steps:\n"
            f"      - uses: {COVERAGE_ACTION}@abc123\n",
            encoding="utf-8",
        )
    assert sorted(workflow_documents(tmp_path)) == ["first.yml", "second.yaml"], (
        "both workflow extensions must be read, and nothing else"
    )
    assert [job.workflow for job in coverage_jobs(tmp_path)] == [
        "first.yml",
        "second.yaml",
    ], "a lane in either extension must reach the assertions"


def test_every_coverage_step_in_a_job_is_counted() -> None:
    """The ceiling has to contain every watchdog the job arms.

    Counting one step would leave a job running the action twice
    certified against half the work it does.
    """
    job = only_job({
        "controlled.yml": document(
            "name: controlled\non: push\njobs:\n  coverage:\n"
            "    runs-on: ubuntu-latest\n"
            "    env:\n"
            f"      {WATCHDOG_VARIABLE}: 600\n"
            "    steps:\n"
            f"      - uses: {COVERAGE_ACTION}@abc123\n"
            "      - uses: actions/checkout@v5\n"
            f"      - uses: {COVERAGE_ACTION}@abc123\n"
        )
    })
    assert job.steps == 2, "both coverage steps must be counted"
    assert job.watchdogs == (600.0, 600.0), (
        "each counted step must carry the budget in force for it"
    )


def test_a_workflow_that_is_not_yaml_is_reported_against_its_path(
    tmp_path: pathlib.Path,
) -> None:
    """Acquisition fails loudly, and says which file failed.

    Letting the parser's own error escape reports a scanner message
    naming a line and column with no file, and nothing saying the
    failure was in acquisition rather than in the budgets below it. A
    reader of the failure then looks for a timeout that is wrong when
    the workflow never parsed.
    """
    (tmp_path / "broken.yml").write_text("name: [unclosed\n", encoding="utf-8")
    with pytest.raises(WorkflowReadingError) as reported:
        workflow_documents(tmp_path)
    assert reported.value.path == tmp_path / "broken.yml", (
        "the fault names the workflow it is about"
    )
    assert isinstance(reported.value.__cause__, yaml.YAMLError), (
        "the parser's own error is the cause, not a detail to drop"
    )


def test_a_workflow_that_cannot_be_read_is_reported_rather_than_skipped(
    tmp_path: pathlib.Path,
) -> None:
    """An unreadable workflow is not an absent one.

    Skipping it would leave the contract certifying the lanes it could
    read while the lane it exists to bound sat in the file it could
    not.
    """
    # A directory, not a mode. `chmod(0o000)` does not stop a process
    # running as root, and Windows does not enforce POSIX modes at all,
    # so on either the read would succeed and this test would pass over
    # nothing. `glob` yields directories, and reading one raises
    # `IsADirectoryError` on POSIX and `PermissionError` on Windows;
    # both are `OSError`, which is the boundary under test.
    unreadable = tmp_path / "locked.yml"
    unreadable.mkdir()
    with pytest.raises(WorkflowReadingError) as reported:
        workflow_documents(tmp_path)
    assert reported.value.path == unreadable, "the fault names the workflow it is about"
    assert isinstance(reported.value.__cause__, OSError), (
        "the operating system's own error is the cause"
    )


def test_a_workflow_that_is_not_utf8_is_reported_rather_than_escaping(
    tmp_path: pathlib.Path,
) -> None:
    """Bytes that are not UTF-8 are an acquisition fault like any other.

    `UnicodeDecodeError` descends from `ValueError`, not `OSError`, so
    it is the one read failure that would slip past a boundary catching
    `OSError` alone. It would then surface as a decoding error naming a
    byte offset, with nothing saying which workflow it came from, which
    is the reporting this boundary exists to prevent.
    """
    invalid = tmp_path / "latin1.yml"
    invalid.write_bytes(b"name: caf\xe9\n")
    with pytest.raises(WorkflowReadingError) as reported:
        workflow_documents(tmp_path)
    assert reported.value.path == invalid, "the fault names the workflow it is about"
    assert isinstance(reported.value.__cause__, UnicodeDecodeError), (
        "the decoding failure itself is the cause"
    )


def test_every_workflow_fault_is_catchable_as_the_domain_base(
    tmp_path: pathlib.Path,
) -> None:
    """The domain base is what a caller catches to catch them all.

    `WorkflowReadingError` is the only concrete member today, so the
    base earns its place by being the thing callers name rather than by
    grouping siblings. Asserting it here means a later member that
    forgot to inherit it would fail rather than quietly escape a caller
    that catches the family.
    """
    invalid = tmp_path / "broken.yml"
    invalid.write_text("name: [unclosed\n", encoding="utf-8")
    with pytest.raises(WorkflowError):
        workflow_documents(tmp_path)
