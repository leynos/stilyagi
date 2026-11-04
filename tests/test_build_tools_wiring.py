"""Hold every Linux job that reaches the suite to installing the pinned tools first.

The coverage publisher excludes mold from its compiler flags yet still executes
tests that drive Make targets, and those reach the build-tools preflight. The
installation therefore has to live in the job that runs the suite: not in a
different job, not behind an `if:`, not allowed to fail softly, and not after
the step that needs it. The job set is derived from workflow and Make
reachability, never from job names, so a newly added Linux suite job is held to
the rule without anyone remembering to list it.

The reading is driven over constructed workflows in both directions before the
real files are asserted, because a check over this repository's own correct
workflows passes whether or not it discriminates anything.
"""

import typing as typ

import pytest

from tests.support.build_standard import make_available_tools
from tests.support.build_tools_wiring import (
    MakeReach,
    external_workflow_calls,
    is_linux_capable,
    make_goals,
    runner_labels,
    suite_job_readings,
)
from tests.support.workflow_documents import WORKFLOWS_DIRECTORY
from tests.support.workflow_files import WorkflowReadingError, read_workflows
from tests.support.workflows import load_workflow, workflow_jobs

if typ.TYPE_CHECKING:
    from tests.support.workflows import WorkflowDocument

#: Reusable-workflow calls whose steps live outside this repository, each with
#: why no install is needed. A new call fails until it is classified here.
CLASSIFIED_EXTERNAL_CALLS: typ.Final = {
    "dependabot-automerge.yml:automerge": (
        "approves and merges Dependabot pull requests; it builds nothing"
    ),
    "mutation-testing.yml:mutation-rust": (
        "cargo-mutants runs `cargo test` only and no Make goal: the shared "
        "workflow's setup-rust exports -D warnings, which displaces mold, and "
        "the Cranelift component comes from rust-toolchain.toml"
    ),
    "smoke.yml:release-smoke": (
        "delegates to build-wheels.yml in this repository; that file's own "
        "jobs run maturin and `uv build`, and reach neither the suite nor a "
        "Make goal, which is why no reading here needs an install step"
    ),
    "release.yml:build-wheels": (
        "delegates to build-wheels.yml in this repository; that file's own "
        "jobs run maturin and `uv build`, and reach neither the suite nor a "
        "Make goal, which is why no reading here needs an install step"
    ),
}


@pytest.fixture(scope="module")
def reach(tmp_path_factory: pytest.TempPathFactory) -> MakeReach:
    """Return Make's reachability reading, over probe executables."""
    return MakeReach(make_available_tools(tmp_path_factory.mktemp("wiring-probes")))


def _workflow(jobs: str) -> WorkflowDocument:
    """Return a parsed workflow document holding `jobs`."""
    return load_workflow(f"on: push\njobs:\n{jobs}")


def _install(extra: str = "") -> str:
    """Return a YAML install step, with `extra` lines in the step."""
    return f"      - run: make install-build-tools\n{extra}"


SELECTION_EXPRESSION = (
    "${{ github.event.pull_request.head.repo.fork"
    " && 'ubuntu-latest' || 'ubicloud-standard-4' }}"
)
LINT_STEP = "      - run: make lint\n"
COVERAGE_STEP = (
    "      - uses: leynos/shared-actions/.github/actions/generate-coverage@abc\n"
)
JOB_HEAD = "  suite:\n    runs-on: {runner}\n    steps:\n"


def _faults(jobs: str, reach: MakeReach) -> list[str]:
    """Return every fault the reading finds in a constructed `jobs` mapping."""
    readings = suite_job_readings({"w.yml": _workflow(jobs)}, reach)
    return [fault for reading in readings for fault in reading.faults]


def test_a_correctly_wired_job_has_no_faults(reach: MakeReach) -> None:
    """The positive control: install first, unconditionally."""
    jobs = JOB_HEAD.format(runner="ubuntu-latest") + _install() + LINT_STEP
    assert not _faults(jobs, reach), "expected not _faults(jobs, reach)"


@pytest.mark.parametrize(
    ("case_id", "steps", "expected"),
    [
        pytest.param("no_install", LINT_STEP, "no step runs", id="no_install"),
        pytest.param(
            "after_suite",
            LINT_STEP + _install(),
            "install runs after",
            id="install_after_suite",
        ),
        pytest.param(
            "conditional",
            _install("        if: github.event_name == 'push'\n") + LINT_STEP,
            "conditional",
            id="install_with_if",
        ),
        pytest.param(
            "soft_failing",
            _install("        continue-on-error: true\n") + LINT_STEP,
            "continue-on-error",
            id="install_continue_on_error",
        ),
        pytest.param(
            "swallowed",
            "      - run: make install-build-tools || true\n" + LINT_STEP,
            "swallows",
            id="install_swallowed",
        ),
        pytest.param(
            "coverage_action",
            COVERAGE_STEP,
            "no step runs",
            id="coverage_action_without_install",
        ),
    ],
)
def test_each_wiring_fault_is_detected(
    case_id: str, steps: str, expected: str, reach: MakeReach
) -> None:
    """Every way the install can fail to precede the suite is a fault."""
    jobs = JOB_HEAD.format(runner="ubuntu-latest") + steps
    faults = _faults(jobs, reach)
    assert any(expected in fault for fault in faults), (case_id, faults)


@pytest.mark.parametrize(
    "run_line",
    [
        pytest.param("cargo nextest run --workspace", id="direct_nextest"),
        pytest.param("uv run pytest -v", id="direct_pytest"),
        pytest.param("make test-doc", id="make_goal_reaching_suite"),
        pytest.param("make typecheck", id="make_goal_reaching_preflight"),
    ],
)
def test_every_way_of_reaching_the_suite_is_derived(
    run_line: str, reach: MakeReach
) -> None:
    """A job is found whichever route reaches the suite, and then needs the install."""
    jobs = JOB_HEAD.format(runner="ubuntu-latest") + f"      - run: {run_line}\n"
    assert _faults(jobs, reach), run_line


def test_a_goal_that_reaches_nothing_makes_the_job_irrelevant(reach: MakeReach) -> None:
    """A job whose goals reach neither suite nor preflight needs no install."""
    jobs = (
        JOB_HEAD.format(runner="ubuntu-latest")
        + "      - run: make check-fmt\n"
        + "  other:\n    runs-on: ubuntu-latest\n    steps:\n"
        + _install()
        + LINT_STEP
    )
    readings = suite_job_readings({"w.yml": _workflow(jobs)}, reach)
    assert [reading.job for reading in readings] == ["other"], (
        "expected [reading.job for reading in readings] == ['other']"
    )


@pytest.mark.parametrize(
    ("runs_on", "expected"),
    [
        pytest.param("ubuntu-latest", {"ubuntu-latest"}, id="scalar"),
        pytest.param("[self-hosted, ubuntu-24.04]", None, id="list_with_self_hosted"),
        pytest.param("[ubuntu-24.04, x64]", None, id="list_with_unknown_label"),
        pytest.param(
            "{labels: [ubuntu-24.04]}", {"ubuntu-24.04"}, id="mapping_labels_list"
        ),
        pytest.param(
            "{labels: ubicloud-standard-4}",
            {"ubicloud-standard-4"},
            id="mapping_labels_scalar",
        ),
        pytest.param(
            SELECTION_EXPRESSION,
            {"ubuntu-latest", "ubicloud-standard-4"},
            id="selection_expression",
        ),
        pytest.param(
            "${{ matrix.os }}", {"ubuntu-latest", "macos-latest"}, id="matrix"
        ),
    ],
)
def test_runner_forms_are_placed_or_refused(
    runs_on: str, expected: set[str] | None
) -> None:
    """Scalar, list, mapping, expression and matrix runners are read."""
    jobs = workflow_jobs(
        _workflow(
            f"  j:\n    runs-on: {runs_on}\n    strategy:\n      matrix:\n"
            "        os: [ubuntu-latest, macos-latest]\n    steps: []\n"
        )
    )
    job = jobs["j"]
    if expected is None:
        with pytest.raises(WorkflowReadingError):
            is_linux_capable(job)
        return
    assert set(runner_labels(job)) == expected, (
        "expected set(runner_labels(job)) == expected"
    )
    assert is_linux_capable(job), "expected is_linux_capable(job)"


def test_a_matrix_with_a_linux_leg_is_a_linux_job(reach: MakeReach) -> None:
    """A matrix job is Linux-capable when any leg is, and the install is shared."""
    jobs = (
        "  suite:\n    runs-on: ${{ matrix.os }}\n    strategy:\n      matrix:\n"
        "        os: [ubuntu-latest, windows-latest]\n    steps:\n" + LINT_STEP
    )
    assert _faults(jobs, reach), "expected _faults(jobs, reach)"


def test_a_workflow_with_no_suite_job_is_a_reader_failure(reach: MakeReach) -> None:
    """An empty set is reported, never passed."""
    jobs = JOB_HEAD.format(runner="ubuntu-latest") + "      - run: echo hello\n"
    with pytest.raises(WorkflowReadingError):
        suite_job_readings({"w.yml": _workflow(jobs)}, reach)


@pytest.mark.parametrize(
    ("run_text", "goals"),
    [
        pytest.param("make lint", ["lint"], id="simple"),
        pytest.param(
            "make -j4 CARGO=x typecheck test", ["typecheck", "test"], id="options"
        ),
        pytest.param(
            "set -e\nmake install-build-tools && make lint",
            ["install-build-tools", "lint"],
            id="chained",
        ),
        pytest.param("makeutil parse Makefile", [], id="not_make"),
    ],
)
def test_make_goals_are_read_from_run_scripts(run_text: str, goals: list[str]) -> None:
    """Goals are found through options, assignments and chaining."""
    assert make_goals(run_text) == goals, "expected make_goals(run_text) == goals"


REAL_WORKFLOWS: typ.Final = read_workflows(WORKFLOWS_DIRECTORY)


def test_the_real_suite_jobs_are_found_and_wired(reach: MakeReach) -> None:
    """Every Linux job reaching the suite installs the tools first."""
    readings = suite_job_readings(REAL_WORKFLOWS, reach)
    found = {(reading.workflow, reading.job) for reading in readings}
    assert {
        ("smoke.yml", "lint-test"),
        ("coverage-main.yml", "coverage-upload"),
    } <= found, "expected {('smoke.yml', 'lint-test'), ('coverage-main.yml', 'cover..."
    faults = {f"{r.workflow}:{r.job}": r.faults for r in readings if r.faults}
    assert not faults, faults


def test_release_artefact_skips_the_preflight_but_release_reaches_it(
    reach: MakeReach,
) -> None:
    """The wheel build needs no tools; `make release` reaches them through `.venv`."""
    assert not reach.reaches_preflight("release-artefact"), (
        "expected not reach.reaches_preflight('release-artefact')"
    )
    assert reach.reaches_preflight("release"), (
        "expected reach.reaches_preflight('release')"
    )
    assert reach.reaches_preflight("build"), "expected reach.reaches_preflight('build')"
    assert reach.reaches_preflight("test"), "expected reach.reaches_preflight('test')"


def test_every_reusable_workflow_call_is_classified() -> None:
    """A reusable call's steps are unreadable, so a person classifies each."""
    assert set(external_workflow_calls(REAL_WORKFLOWS)) <= set(
        CLASSIFIED_EXTERNAL_CALLS
    ), "expected set(external_workflow_calls(REAL_WORKFLOWS)) <= set(CLASS..."
