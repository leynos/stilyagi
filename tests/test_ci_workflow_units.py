"""Unit tests for the CI smoke workflow contract.

These tests parse `.github/workflows/smoke.yml` and assert that CI keeps
calling the canonical Makefile targets instead of duplicating build logic,
and that tool installation stays pinned and Makefile-resolved.
"""

import pathlib
import re
import typing as typ

import pytest

from tests.support.assertions import assert_with_context
from tests.support.workflows import load_workflow

if typ.TYPE_CHECKING:
    from syrupy.assertion import SnapshotAssertion

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[1]
WorkflowStep = typ.TypedDict(
    "WorkflowStep",
    {"name": str, "uses": str, "run": str, "with": dict[str, str]},
    total=False,
)
WorkflowJob = typ.TypedDict(
    "WorkflowJob",
    {
        "runs-on": str,
        "strategy": dict[str, dict[str, list[str]]],
        "steps": list[WorkflowStep],
    },
    total=False,
)
type SmokeWorkflow = tuple[dict[str, WorkflowJob], list[WorkflowStep], set[str]]


def _workflow_jobs(parsed_workflow: dict[str, object]) -> dict[str, WorkflowJob]:
    """Return the parsed workflow jobs with a narrow test-local shape."""
    jobs = parsed_workflow["jobs"]
    assert isinstance(jobs, dict), "expected isinstance(jobs, dict)"
    return typ.cast("dict[str, WorkflowJob]", jobs)


def _job_steps(job: WorkflowJob) -> list[WorkflowStep]:
    """Return a workflow job's steps with a narrow test-local shape."""
    return typ.cast("list[WorkflowStep]", job["steps"])


def _workflow_steps(jobs: dict[str, WorkflowJob]) -> list[WorkflowStep]:
    """Return every step from every parsed workflow job."""
    return [step for job in jobs.values() for step in _job_steps(job)]


def _workflow_step_named(job: WorkflowJob, name: str) -> WorkflowStep:
    """Return a named step from a parsed workflow job."""
    for step in _job_steps(job):
        if step.get("name") == name:
            return step
    available_names = [step.get("name", "<unnamed>") for step in _job_steps(job)]
    msg = (
        f"workflow step {name!r} not found in job {job!r}; "
        f"available steps: {available_names!r}"
    )
    raise AssertionError(msg)


def _smoke_workflow_document() -> dict[str, object]:
    """Parse the smoke workflow file into its document mapping."""
    return load_workflow(
        (REPOSITORY_ROOT / ".github" / "workflows" / "smoke.yml").read_text(
            encoding="utf-8"
        )
    )


def _workflow_environment(parsed_workflow: dict[str, object]) -> dict[str, str]:
    """Return the workflow-level environment variables."""
    environment = parsed_workflow["env"]
    assert isinstance(environment, dict), "expected isinstance(environment, dict)"
    return typ.cast("dict[str, str]", environment)


def _makefile_tool_version(makefile: str, tool: str) -> str:
    """Return one version pin declared in the Makefile."""
    match = re.search(rf"^{tool}_VERSION \?= (?P<version>\S+)$", makefile, re.MULTILINE)
    assert match is not None, f"expected {tool}_VERSION pin in Makefile"
    return match["version"]


@pytest.fixture(name="smoke_workflow", scope="module")
def smoke_workflow_fixture() -> SmokeWorkflow:
    """Parse the smoke workflow once for the per-concern CI assertions."""
    jobs = _workflow_jobs(_smoke_workflow_document())
    workflow_steps = _workflow_steps(jobs)
    run_commands = {
        command.strip()
        for step in workflow_steps
        for command in str(step.get("run", "")).splitlines()
        if command.strip()
    }
    return jobs, workflow_steps, run_commands


def test_ci_workflow_calls_the_canonical_makefile_targets(
    smoke_workflow: SmokeWorkflow,
) -> None:
    """Make CI exercise Makefile targets instead of duplicating build logic."""
    _jobs, _workflow_steps, run_commands = smoke_workflow
    assert_with_context(
        {
            "make check-fmt",
            "make markdownlint",
            "make nixie",
            "make typecheck",
            "make lint",
            "make test",
        }.issubset(run_commands),
        "expected <'make check-fmt', 'make markdownlint', 'ma...",
    )


@pytest.mark.parametrize("tool", ["RUFF", "TY"])
def test_ci_tool_versions_match_makefile(tool: str) -> None:
    """Keep each CI tool pin aligned with its canonical Makefile pin."""
    workflow_environment = _workflow_environment(_smoke_workflow_document())
    makefile = (REPOSITORY_ROOT / "Makefile").read_text(encoding="utf-8")

    assert_with_context(
        workflow_environment[f"{tool}_VERSION"]
        == _makefile_tool_version(makefile, tool),
        f"expected CI {tool} version to match the Makefile pin",
    )


def test_ci_workflow_job_topology(smoke_workflow: SmokeWorkflow) -> None:
    """CI must keep the lint-test job and the release-smoke OS matrix."""
    jobs, _workflow_steps, _run_commands = smoke_workflow
    assert "lint-test" in jobs, "expected 'lint-test' in jobs"
    assert_with_context(
        jobs["lint-test"]["runs-on"] == "ubuntu-latest",
        "expected jobs['lint-test']['runs-on'] == 'ubuntu-lat...",
    )
    assert "release-smoke" in jobs, "expected 'release-smoke' in jobs"
    assert_with_context(
        jobs["release-smoke"]["runs-on"] == "${{ matrix.os }}",
        "expected jobs['release-smoke']['runs-on'] == '$<< ma...",
    )
    assert_with_context(
        jobs["release-smoke"]["strategy"]["matrix"]["os"]
        == [
            "ubuntu-latest",
            "macos-latest",
            "windows-latest",
        ],
        "expected jobs['release-smoke']['strategy']['matrix']...",
    )


def test_ci_workflow_triggers_on_pull_request_and_main_push() -> None:
    """CI must run for pull requests and pushes to the main branch."""
    parsed_workflow = _smoke_workflow_document()
    triggers = typ.cast("dict[str, object]", parsed_workflow.get("on", {}))
    assert "pull_request" in triggers, "expected 'pull_request' in triggers"
    assert_with_context(
        "main"
        in typ.cast("dict[str, list[str]]", triggers.get("push", {})).get(
            "branches", []
        ),
        "expected 'main' in typ.cast('dict[str, list[str]]', ...",
    )


def test_ci_workflow_pins_python_setup_action(smoke_workflow: SmokeWorkflow) -> None:
    """Every setup-python step must pin the action hash and Python version."""
    _jobs, workflow_steps, _run_commands = smoke_workflow
    python_steps = [
        step
        for step in workflow_steps
        if str(step.get("uses", "")).startswith("actions/setup-python@")
    ]
    assert python_steps, "expected python_steps"
    assert_with_context(
        all(
            step["uses"]
            == "actions/setup-python@a309ff8b426b58ec0e2a45f0f869d46889d02405"
            for step in python_steps
        ),
        "expected all((step['uses'] == 'actions/setup-python@...",
    )
    assert_with_context(
        all(step["with"]["python-version"] == "3.14" for step in python_steps),
        "expected all((step['with']['python-version'] == '3.1...",
    )


def test_ci_workflow_resolves_interrogate_and_formatting_from_makefile(
    smoke_workflow: SmokeWorkflow,
) -> None:
    """Resolve Interrogate and mdformat-all through the Makefile only.

    Interrogate resolves from the locked dev dependency group through the
    Makefile, so CI must not install it separately, and CI must not invoke
    `mdformat-all` outside the Makefile either.
    """
    _jobs, workflow_steps, run_commands = smoke_workflow
    assert_with_context(
        all("interrogate" not in command for command in run_commands),
        "expected all(('interrogate' not in command for comma...",
    )
    assert_with_context(
        all("mdformat-all" not in str(step) for step in workflow_steps),
        "expected all(('mdformat-all' not in str(step) for st...",
    )


def test_ci_workflow_installs_nixie_cli(smoke_workflow: SmokeWorkflow) -> None:
    """CI must install the pinned nixie-cli release for the Mermaid gate."""
    _jobs, workflow_steps, _run_commands = smoke_workflow
    assert_with_context(
        any(
            "uv tool install nixie-cli==1.0.0" in str(step.get("run", ""))
            for step in workflow_steps
        ),
        "expected any(('uv tool install nixie-cli==1.0.0' in ...",
    )


def test_ci_workflow_installs_test_runner_and_whitaker(
    smoke_workflow: SmokeWorkflow,
    snapshot: SnapshotAssertion,
) -> None:
    """CI must install cargo-nextest and the pinned Whitaker toolchain."""
    jobs, _workflow_steps, _run_commands = smoke_workflow
    test_runner_step = _workflow_step_named(jobs["lint-test"], "Install test runner")
    assert_with_context(
        "cargo binstall --no-confirm cargo-nextest" in test_runner_step["run"],
        "expected 'cargo binstall --no-confirm cargo-nextest'...",
    )
    whitaker_step = _workflow_step_named(jobs["lint-test"], "Install Whitaker")
    whitaker_run = str(whitaker_step["run"]).rstrip()
    # The installer is pinned via the workflow-level env var and expanded by
    # the shell (never inlined with ``${{ env … }}``, which zizmor flags as
    # template injection), fetched with ``--locked``, and falls back to a
    # crates.io build when cargo-binstall is unavailable.
    assert_with_context(
        whitaker_run == snapshot,
        "expected the Whitaker installation recipe to match i...",
    )


def test_ci_workflow_runs_release_smoke(smoke_workflow: SmokeWorkflow) -> None:
    """The release-smoke job must build and smoke-test through make release."""
    jobs, _workflow_steps, _run_commands = smoke_workflow
    release_smoke_step = _workflow_step_named(jobs["release-smoke"], "Release smoke")
    assert_with_context(
        "make release" in release_smoke_step["run"],
        "expected 'make release' in release_smoke_step['run']",
    )
